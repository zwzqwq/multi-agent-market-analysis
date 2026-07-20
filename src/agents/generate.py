from src.agents.state import AgentState,MAX_ITERATIONS
from src.utils.config import config
from src.utils.report_saver import save_report
from src.models.contracts import Section
from datetime import datetime



def generate_report(state:AgentState):
    """生成最终报告（审核通过 OR 达到最大迭代次数时调用）"""
    draft = state["draft"]
    output_path = config.OUTPUT_DIR

    # 达到上限仍未通过 → 在报告前插入质量声明
    if state["iteration_count"] >= MAX_ITERATIONS:
        disclaimer = Section(
            title="[质量声明]",
            content=f"本报告经 {MAX_ITERATIONS} 轮审核迭代仍未完全达到质量标准。以下内容仅供参考，建议人工复核关键数据和结论。",
            claims=[]
        )
        draft.sections.insert(0, disclaimer)

    report_path = save_report(draft, output_path)
    return {"final_report_path": report_path}