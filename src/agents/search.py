from src.agents.state import AgentState
from src.models.contracts import SearchResult
from src.tools.search_api import tavily_search_tool
from src.utils.logger import logger

def search_node(state: AgentState)-> dict:
    logger.info(f"开始搜索关于 '{state['topic']}' 的内容...")
    topic=state["topic"]
    sources = tavily_search_tool.search(topic)
    search_result = SearchResult(
        sources=sources,
        query=topic
    )
    logger.info(f"搜索关于 '{state['topic']}' 的内容完成，共找到 {len(search_result.sources)} 条结果")
    return {
        "search_result": search_result
        }
