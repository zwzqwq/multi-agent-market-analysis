"""后台任务执行器：在独立线程中运行 LangGraph 工作流"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.api.store import ReportStore
from src.utils.logger import logger

# 单 worker 保证同一时间只有一个工作流在跑，消除并发问题
_workflow_executor = ThreadPoolExecutor(max_workers=1)


def _invoke_workflow(topic: str) -> dict:
    """在线程池中调用 — 每次编译新图，避免状态污染"""
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
    """FastAPI 后台任务：跑工作流 → 更新 store"""
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
