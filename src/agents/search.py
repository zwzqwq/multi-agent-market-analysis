from src.agents.state import AgentState
from src.models.contracts import SearchResult
from src.tools.search_api import tavily_search_tool

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
