"""

加载 .env 文件，读取环境变量，统一管理项目配置。
这个模块不依赖任何其他项目模块，可以被所有文件安全导入。

设计意图：
- 所有配置项集中在 .env 文件中，不散落在代码各处
- 提供默认值，本地开发开箱即用
- LLM API 密钥在这里读取一次，其他地方从 Config 拿
- 默认使用 DeepSeek API（兼容 OpenAI 格式），适合国内环境

"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """集中管理所有配置项"""

    # --- LLM 配置 ---
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "deepseek-chat")

    # --- 搜索 API 配置 ---
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

    # --- 项目路径 ---
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "outputs")

    # --- 审核阈值 ---
    AUDIT_PASS_THRESHOLD: float = 0.8
    AUDIT_MINOR_THRESHOLD: float = 0.5

    @classmethod
    def validate(cls) -> list[str]:
        """启动前检查必要配置是否缺失，返回缺失项列表"""
        missing = []
        if not cls.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        if not cls.TAVILY_API_KEY:
            missing.append("TAVILY_API_KEY")
        return missing

    LLM_CONFIG = {
      "analysis": {"model": "deepseek-chat", "max_tokens": 3000},
      "write":    {"model": "deepseek-chat", "max_tokens": 3000},
      "audit":    {"model": "deepseek-chat", "max_tokens": 4000},
    }

config = Config()
