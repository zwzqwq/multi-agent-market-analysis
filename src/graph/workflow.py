from src.agents.state import AgentState
from src.agents.search import search_node
from src.agents.analysis import analysis_node
from src.agents.draft import draft_node
from src.agents.audit import auditor_node, route_after_audit
from src.agents.generate import generate_report
from langgraph.graph import StateGraph, END, START


def build_workflow():
    """构建 LangGraph 工作流（骨架阶段，节点后续添加）"""
    workflow = StateGraph(AgentState)
    workflow.add_node("search",search_node)
    workflow.add_node("analysis",analysis_node)
    workflow.add_node("write",draft_node)
    workflow.add_node("audit",auditor_node)
    workflow.add_node("generate",generate_report)

    workflow.add_edge(START, "search")
    workflow.add_edge("search", "analysis")
    workflow.add_edge("analysis", "write")
    workflow.add_edge("write", "audit")


    workflow.add_conditional_edges(
     "audit",           # 从哪个节点出发
     route_after_audit, # 路由函数: 读 state → 返回 "pass" / "minor_issues" / "major_issues"
     {
         "force_pass": "generate",
         "pass": "generate",
         "minor_issues": "write",    # 回到撰写
         "major_issues": "analysis", # 回到分析
     }
    )
    workflow.add_edge("generate", END)

    return workflow.compile()