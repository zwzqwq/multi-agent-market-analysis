"""多Agent市场分析报告生成系统 — 统一入口

三种运行模式:
  python -m src.main cli "主题"       命令行模式（原有）
  python -m src.main api              FastAPI 服务
  python -m src.main ui              Gradio Web 界面

argparse 是 Python 标准库里的命令行参数解析器。
类比 Java 的 picocli —— 把命令行参数映射到函数调用。

argparse 核心概念:
  parser = ArgumentParser()        → 创建解析器
  sub = parser.add_subparsers()    → 子命令（cli / api / ui）
  每个 sub.add_parser()            → 注册一个子命令 + 它的参数
  parser.parse_args()              → 解析用户输入，"cli" → args.command="cli"
"""

import argparse
import sys

from src.utils.logger import logger


def main(topic: str):
    """CLI 模式：一口吃完整条管线，阻塞等待报告生成"""
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
    """启动 FastAPI 服务

    uvicorn: Python 的 ASGI 服务器（类似 Java 的 Tomcat / Netty）
    它的作用是把 FastAPI 应用挂到 HTTP 端口上监听请求。
    """
    import uvicorn
    from src.api.app import create_app

    app = create_app()
    logger.info(f"FastAPI 服务启动: http://{host}:{port}")
    logger.info(f"API 文档: http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port, log_level="info")


def serve_ui(host: str = "127.0.0.1", port: int = 7860):
    """启动 Gradio Web 界面

    demo.launch() 会启动一个本地 HTTP 服务器，
    浏览器访问 http://127.0.0.1:7860 就能看到界面。
    share=False: 不对外暴露公网链接。
    """
    from src.ui.app import create_ui

    demo = create_ui()
    logger.info(f"Gradio 界面启动: http://{host}:{port}")
    demo.launch(server_name=host, server_port=port, share=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="多Agent市场分析报告生成系统")
    sub = parser.add_subparsers(dest="command", help="运行模式")

    # CLI 子命令: python -m src.main cli "主题"
    cli_parser = sub.add_parser("cli", help="命令行模式")
    cli_parser.add_argument("topic", help="分析主题")

    # API 子命令: python -m src.main api --host 0.0.0.0 --port 8080
    api_parser = sub.add_parser("api", help="启动 FastAPI 服务")
    api_parser.add_argument("--host", default="127.0.0.1", help="绑定 IP")
    api_parser.add_argument("--port", type=int, default=8000, help="绑定端口")

    # UI 子命令: python -m src.main ui
    ui_parser = sub.add_parser("ui", help="启动 Gradio Web 界面")
    ui_parser.add_argument("--host", default="127.0.0.1", help="绑定 IP")
    ui_parser.add_argument("--port", type=int, default=7860, help="绑定端口")

    args = parser.parse_args()

    if args.command == "cli":
        main(args.topic)
    elif args.command == "api":
        serve_api(args.host, args.port)
    elif args.command == "ui":
        serve_ui(args.host, args.port)
    else:
        # 向后兼容：无子命令时，如果只有一个参数就当 CLI 处理
        # python -m src.main "AI芯片" 等价于 python -m src.main cli "AI芯片"
        if len(sys.argv) == 2 and not sys.argv[1].startswith("-"):
            main(sys.argv[1])
        else:
            parser.print_help()
