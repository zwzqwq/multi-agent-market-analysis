"""Gradio Web 界面 —— 在浏览器里画按钮和文本框，调 FastAPI 端点

Gradio 有自己的组件体系，不需要背 —— 用的时候查文档就行。

Gradio 组件 ≈ Android 控件:
  gr.Blocks   → LinearLayout（页面容器）
  gr.Row      → 水平布局
  gr.Column   → 垂直布局
  gr.Textbox  → EditText（输入框）
  gr.Button   → Button（按钮）
  gr.Markdown → TextView（显示 Markdown）

核心写法永远一样:
  btn.click(fn=你的函数, inputs=[输入组件], outputs=[输出组件])

本模块生成的函数是 httpx HTTP 客户端 —— 调 FastAPI，不直接调 workflow。
这保证了"界面层"和"业务层"之间没有耦合：Gradio 不知道 LangGraph 的存在。
"""

import asyncio
import os

import gradio as gr
import httpx

# 当环境变量 API_BASE_URL 存在时用它，否则默认连本地
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


async def generate_report(topic: str):
    """点击「生成报告」按钮时触发

    执行流程（提交-轮询模式）:
      1. POST /api/v1/reports        → 提交任务，拿到 report_id
      2. 每 3 秒 GET /api/v1/reports/{id} → 查状态
      3a. status=completed → GET content → 显示报告 ✅
      3b. status=failed    → 显示错误信息 ❌
      3c. 其他             → 继续等 ⏳

    用 yield 而不是 return 是因为需要渐进式更新页面:
      - "任务已提交..."
      - "正在生成..."
      - "生成完成!" + 报告内容
    每 yield 一次，页面就刷新一次状态显示。

    yield 的格式: (状态文本, Markdown内容)
    这两个值对应 create_ui 中 generate_btn.click 的 outputs 参数。
    """
    topic = topic.strip()
    if not topic:
        yield "请输入分析主题", ""
        return

    # httpx.AsyncClient = 异步 HTTP 客户端，浏览器里 fetch() 的 Python 版
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=30)) as client:
        # ========== Step 1: 提交任务 ==========
        try:
            resp = await client.post(
                f"{API_BASE_URL}/api/v1/reports",
                json={"topic": topic},
            )
            resp.raise_for_status()     # 状态码不是 2xx → 抛 HTTPError
        except httpx.HTTPError as e:
            yield f"API 连接失败: {e}", ""
            return

        data = resp.json()
        report_id = data["report_id"]
        yield f"任务已提交 (ID: {report_id[:8]}...)\n正在搜索和分析...", ""

        # ========== Step 2: 轮询状态 ==========
        max_wait = 300          # 最多等 5 分钟
        poll_interval = 3       # 每 3 秒查一次

        for _ in range(max_wait // poll_interval):   # 最多查 100 次
            await asyncio.sleep(poll_interval)        # 等 3 秒

            try:
                status_resp = await client.get(
                    f"{API_BASE_URL}/api/v1/reports/{report_id}"
                )
                status_resp.raise_for_status()
            except httpx.HTTPError:
                continue                            # 网络抖动 → 跳过这轮

            record = status_resp.json()

            if record["status"] == "completed":
                iteration = record.get("iteration_count", "?")
                verdict = record.get("audit_verdict", "?")
                status_text = (
                    f"生成完成!\n"
                    f"迭代次数: {iteration}\n"
                    f"最终审核: {verdict}\n"
                    f"路径: {record.get('final_report_path', '')}"
                )

                # Step 3: 拿报告内容
                try:
                    content_resp = await client.get(
                        f"{API_BASE_URL}/api/v1/reports/{report_id}/content"
                    )
                    content = content_resp.text
                except httpx.HTTPError:
                    content = "*无法获取报告内容*"

                yield status_text, content
                return

            elif record["status"] == "failed":
                error = record.get("error", "未知错误")
                yield f"生成失败: {error}", ""
                return

            else:
                yield (
                    f"任务 ID: {report_id[:8]}...\n"
                    f"状态: {record['status']}\n"
                    f"请耐心等待约 2 分钟...",
                    "",
                )

        yield "超时（5 分钟），请稍后在历史记录中查看", ""


def create_ui() -> gr.Blocks:
    """搭建 Gradio 界面布局

    gradio 的所有组件都写在 with gr.Blocks() 上下文里。
    布局采用左右分栏: 左边输入+状态，右边显示报告。

    按钮通过 .click() 方法绑定到上面的 generate_report 函数:
      inputs  = [topic_input]            → 取输入框的值
      outputs = [status_output, report_md] → 填到这两个组件里
    """
    with gr.Blocks(title="多Agent市场分析报告生成系统") as demo:
        gr.Markdown("""# 多Agent市场分析报告生成系统

        基于 **LangGraph** 的多 Agent 协作系统，四个 Agent 自动完成：
        **搜索 → 分析 → 撰写 → 审核**，最终输出一份结构化 Markdown 报告。
        """)

        with gr.Row():
            with gr.Column(scale=1):
                topic_input = gr.Textbox(
                    label="分析主题",
                    placeholder="例如: 2026年AI编程助手市场竞争格局",
                    lines=2,
                )
                generate_btn = gr.Button("生成报告", variant="primary", size="lg")
                status_output = gr.Textbox(
                    label="状态",
                    lines=6,
                    interactive=False,          # 只读
                    max_lines=10,
                )

            with gr.Column(scale=2):
                report_md = gr.Markdown(
                    value="*输入主题后点击「生成报告」开始...*",
                )

        # 按钮绑定: 点击 → 调 generate_report → 更新状态区和报告区
        generate_btn.click(
            fn=generate_report,
            inputs=[topic_input],
            outputs=[status_output, report_md],
        )

        gr.Markdown("""---
        ### 使用说明
        1. 输入分析主题
        2. 点击「生成报告」
        3. 系统自动搜索、分析、撰写并审核（约 2 分钟）
        4. 审核不通过会自动回退修正，最多迭代 3 轮
        5. 报告保存到 `outputs/` 目录

        > 提示：需先在另一个终端启动 API 服务：`python -m src.main api`
        """)

    return demo
