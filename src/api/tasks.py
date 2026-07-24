"""后台任务执行器：把同步阻塞的 workflow 丢到独立线程里跑

核心问题:
  app.invoke() 是同步函数，一次跑 128 秒。
  如果在 FastAPI 请求线程里直接调 → 整个服务卡 128 秒 → 其他请求进不来。

解决方案:
  用 ThreadPoolExecutor（线程池）把 workflow 扔到独立线程执行。
  主线程秒回 HTTP 202 + report_id，不阻塞。

  这等价于 Java 的 FutureTask + ThreadPoolExecutor：
    ExecutorService executor = Executors.newFixedThreadPool(1);
    Future<Result> future = executor.submit(() -> invokeWorkflow(topic));
    Result result = future.get(timeout, SECONDS);

线程安全设计:
  StateGraph.invoke() 不保证线程安全 —— 两个请求同时调会互相踩内存。
  两层防护:
    1. max_workers=1 → 同一时间只有一个 workflow 在跑，后来的排队
    2. 每次调用 build_workflow() 新建图对象 → 即使多 worker 也互不干扰
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.api.store import ReportStore
from src.utils.logger import logger

# 全局线程池：整个进程生命周期只创建一次，所有请求共用
# max_workers=1 = "我只有一个工人在处理报告生成"
# 升级路径: 如果未来需要并发 → 改 max_workers + 每次 build_workflow() 编译新图即可
_workflow_executor = ThreadPoolExecutor(max_workers=1)


def _invoke_workflow(topic: str) -> dict:
    """在线程池中执行的同步函数

    _ 前缀 = Python 约定：这是内部函数，外部别直接调。

    每次调用都 build_workflow() 编译新图 —— 不是复用旧图。
    原因: 编译后的 StateGraph 对象第二次 invoke() 时
          内部 Pregel channel 可能残留上一轮的状态，造成数据污染。
          编译新图成本极低（纯连线，不调 LLM），零风险。
    """
    from src.graph.workflow import build_workflow

    app = build_workflow()
    initial_state = {
        "topic": topic,
        "search_result": None,
        "analysis": None,
        "draft": None,
        "audit": None,
        "iteration_count": 0,
        "final_report_path": None,
    }
    logger.info(f"开始生成关于 '{topic}' 的报告...")
    result = app.invoke(initial_state)
    logger.info(f"报告生成完成: {result.get('final_report_path', 'N/A')}")
    return result


async def run_report_generation(
    report_id: str,
    topic: str,
    store: ReportStore,
) -> None:
    """FastAPI 后台任务入口

    执行流程:
      1. 改状态 → running
      2. 把 _invoke_workflow 丢到线程池执行 (run_in_executor)
      3. 等线程跑完 (await)
      4. 改状态 → completed 或 failed

    run_in_executor 拆解:
      loop = asyncio.get_running_loop()     → 拿到当前事件循环
      await loop.run_in_executor(
          executor,  func,     arg
      )                                     → "把 func(arg) 扔到线程池，我在这等"
      主线程在 await 期间不阻塞 —— 可以处理其他请求。
    """
    store.update_running(report_id)

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _workflow_executor,
            _invoke_workflow,
            topic,
        )

        audit_verdict = None
        if result.get("audit") is not None:
            audit_verdict = result["audit"].overall_verdict

        store.update_completed(
            report_id,
            path=result.get("final_report_path", ""),
            iteration_count=result.get("iteration_count", 0),
            audit_verdict=audit_verdict,
        )
    except Exception as e:
        logger.error(f"报告 {report_id} 生成失败: {e}")
        store.update_failed(report_id, str(e))
