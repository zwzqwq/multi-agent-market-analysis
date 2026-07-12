from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END, START
from src.models.contracts import SearchResult, AnalysisReport, DraftReport, AuditResult
from src.tools.search_api import tavily_search_tool

class AgentState(TypedDict):
    """工作流共享状态 —— 所有 Agent 节点读写同一份 State

    topic:            用户输入主题，全程不变
    search_result:    搜索节点填写，其他节点读取
    analysis:         分析节点填写
    draft:            撰写节点填写，审核节点读取
    audit:            审核节点填写，路由节点读取
    iteration_count:  回退计数器，防止死循环
    final_report_path: 最终报告文件路径
    """
    topic: str
    search_result: Optional[SearchResult]
    analysis: Optional[AnalysisReport]
    draft: Optional[DraftReport]
    audit: Optional[AuditResult]
    iteration_count: int
    final_report_path: Optional[str]

def search_node(state: AgentState)-> dict:
    topic=state["topic"]
    sources = tavily_search_tool.search(topic)
    search_result = SearchResult(
        sources=sources,
        query=topic
    )
    return {
        "search_result": search_result
        }

def build_workflow():
    """构建 LangGraph 工作流（骨架阶段，节点后续添加）"""
    workflow = StateGraph(AgentState)
    workflow.add_node("search",search_node)

    workflow.add_edge(START, "search")

    return workflow.compile()