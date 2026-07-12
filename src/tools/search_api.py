from src.utils.config import config
from dotenv import load_dotenv
from tavily import TavilyClient
from src.models.contracts import Source

load_dotenv()

class TavilySearchTool:
    """Tavily 搜索工具"""

    def __init__(self):
        self.api_key = config.TAVILY_API_KEY

    def search(self, query:str,max_results: int=5)-> list[Source]:
        """搜索"""
        client = TavilyClient(self.api_key)
        response = client.search(
            query=query,
            max_results=max_results,
        )
        sources = []
        urlsets = set()
        for result in response["results"]:
            
            if result["url"] in urlsets:
                continue
            urlsets.add(result["url"])
            source = Source(
                title=result["title"],
                url=result["url"],
                snippet=result["content"],
                full_text=result.get("raw_content",""),
            )
            sources.append(source)
        return sources

tavily_search_tool = TavilySearchTool()