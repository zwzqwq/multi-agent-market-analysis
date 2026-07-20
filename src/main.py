"""多Agent市场分析报告生成系统 — 统一入口

三种运行模式:
  python -m src.main cli "主题"       命令行模式（原有）
  python -m src.main api              FastAPI 服务
  python -m src.main ui              Gradio Web 界面
"""

import argparse
import sys

from src.utils.logger import logger


def main(topic: str):
    """CLI 模式：输入主题，阻塞等待报告生成"""
    from .graph.workflow import build_workflow

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
    logger.info("报告生成完成！")

    if result["final_report_path"]:
        logger.info(f"报告文件路径: {result['final_report_path']}")

    if result["draft"]:
        logger.info(f"报告章节数: {len(result['draft'].sections)}")
    return result


def serve_api(host: str = "127.0.0.1", port: int = 8000):
    """启动 FastAPI 服务"""
    import uvicorn
    from src.api.app import create_app

    app = create_app()
    logger.info(f"FastAPI 服务启动: http://{host}:{port}")
    logger.info(f"API 文档: http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port, log_level="info")


def serve_ui(host: str = "127.0.0.1", port: int = 7860):
    """启动 Gradio Web 界面"""
    from src.ui.app import create_ui

    demo = create_ui()
    logger.info(f"Gradio 界面启动: http://{host}:{port}")
    demo.launch(server_name=host, server_port=port, share=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="多Agent市场分析报告生成系统")
    sub = parser.add_subparsers(dest="command", help="运行模式")

    # CLI 模式
    cli_parser = sub.add_parser("cli", help="命令行模式")
    cli_parser.add_argument("topic", help="分析主题")

    # API 模式
    api_parser = sub.add_parser("api", help="启动 FastAPI 服务")
    api_parser.add_argument("--host", default="127.0.0.1")
    api_parser.add_argument("--port", type=int, default=8000)

    # UI 模式
    ui_parser = sub.add_parser("ui", help="启动 Gradio Web 界面")
    ui_parser.add_argument("--host", default="127.0.0.1")
    ui_parser.add_argument("--port", type=int, default=7860)

    args = parser.parse_args()

    if args.command == "cli":
        main(args.topic)
    elif args.command == "api":
        serve_api(args.host, args.port)
    elif args.command == "ui":
        serve_ui(args.host, args.port)
    else:
        # 无参数时默认 CLI 模式（向后兼容）
        if len(sys.argv) == 2 and not sys.argv[1].startswith("-"):
            main(sys.argv[1])
        else:
            parser.print_help()
