"""Gradio Web 界面 — 调 FastAPI 端点"""

import asyncio
import os

import gradio as gr
import httpx

# 可通过环境变量覆盖，默认连本地 FastAPI
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


async def generate_report(topic: str):
    """点击"生成报告"时触发：POST 任务 → 轮询状态 → 返回内容和 markdown"""
    topic = topic.strip()
    if not topic:
        yield "请输入分析主题", ""
        return

    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=30)) as client:
        # Step 1: 提交任务
        try:
            resp = await client.post(
                f"{API_BASE_URL}/api/v1/reports",
                json={"topic": topic},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            yield f"API 连接失败: {e}", ""
            return

        data = resp.json()
        report_id = data["report_id"]
        yield f"任务已提交 (ID: {report_id[:8]}...)\n正在搜索和分析...", ""

        # Step 2: 轮询直到完成
        max_wait = 300
        poll_interval = 3

        for _ in range(max_wait // poll_interval):
            await asyncio.sleep(poll_interval)

            try:
                status_resp = await client.get(
                    f"{API_BASE_URL}/api/v1/reports/{report_id}"
                )
                status_resp.raise_for_status()
            except httpx.HTTPError:
                continue

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

                # 获取报告内容
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
                yield f"任务 ID: {report_id[:8]}...\n状态: {record['status']}\n请耐心等待约 2 分钟...", ""

        yield "超时（5 分钟），请稍后在历史记录中查看", ""


def create_ui() -> gr.Blocks:
    with gr.Blocks(title="多Agent市场分析报告生成系统") as demo:
        gr.Markdown("""
        # 多Agent市场分析报告生成系统

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
                    interactive=False,
                    max_lines=10,
                )

            with gr.Column(scale=2):
                report_md = gr.Markdown(
                    value="*输入主题后点击「生成报告」开始...*",
                )

        generate_btn.click(
            fn=generate_report,
            inputs=[topic_input],
            outputs=[status_output, report_md],
        )

        gr.Markdown("""
        ---
        ### 使用说明

        1. 输入你想分析的市场/行业主题
        2. 点击「生成报告」
        3. 系统自动搜索、分析、撰写并审核（约 2 分钟）
        4. 审核不通过会自动退回到分析或撰写节点修正
        5. 最多迭代 3 轮，确保输出质量
        6. 报告以 Markdown 格式保存到 `outputs/` 目录

        > 提示：需要先在另一个终端启动 API 服务：`python -m src.main api`
        """)

    return demo
