from .graph.workflow import build_workflow

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
    print(f"开始生成关于 '{topic}' 的报告...", flush=True)
    result = app.invoke(initial_state)
    print("报告生成完成！", flush=True)
    
    # 打印关键信息
    if result["final_report_path"]:
        print(f"报告文件路径: {result['final_report_path']}", flush=True)

    if result["draft"]:
        print(f"报告章节数: {len(result['draft'].sections)}", flush=True)
    return result

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python -m src.main <主题>", flush=True)
        sys.exit(1)
    main(sys.argv[1])
