from src.utils.config import config
from src.utils.logger import logger
from langchain_openai import ChatOpenAI
import json
from src.utils.json_parser import parse_llm_json


def call_llm_with_retry(messages, node_name):
    logger.info(f"正在创建 {node_name} 节点的 LLM 调用...")
    cfg = config.LLM_CONFIG.get(node_name, {})
    model = cfg.get("model", config.MODEL_NAME)       # 获取在config中配置的对应节点的模型名称，没有则使用默认模型
    max_tokens = cfg.get("max_tokens", None)
    for attempt in range(3):
        temperature =0.3*attempt
        llm = ChatOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature
        )
        response = llm.invoke(messages)
        raw=response.content.strip()
        finish_reason = response.response_metadata.get('finish_reason', 'N/A')
        try:
            data = parse_llm_json(raw, finish_reason, node_name)
            return data   
        except RuntimeError as e:
            logger.warning(f"[{node_name}] 第{attempt+1}次失败: {e}")
            continue
    logger.error(f"{node_name}节点 LLM 调用失败，尝试次数 {attempt+1}")
    raise RuntimeError(f"[{node_name}] {attempt+1} 次重试全部失败")
    