from .graph.workflow import build_workflow
from src.utils.logger import logger
def main(topic:str):
    app = build_workflow()
    initial_state = {
        "topic": topic,
        "search_result": None,
        "analysis": None,
        "draft": None,
        "audit": None,
        "iteration_count": 0,      # 必须提供初始值
        "final_report_path": None
    }
    logger.info(f"开始生成关于 '{topic}' 的报告...")
    result = app.invoke(initial_state)
    logger.info("报告生成完成！")

    if result["final_report_path"]:
        logger.info(f"报告文件路径: {result['final_report_path']}")

    if result["draft"]:
        logger.info(f"报告章节数: {len(result['draft'].sections)}")
    return result

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        logger.error("用法: python -m src.main <主题>")
        sys.exit(1)
    main(sys.argv[1])
