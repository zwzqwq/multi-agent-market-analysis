import json

def parse_llm_json(raw: str, finish_reason: str, node_name: str = "unknown") -> dict:
    """解析 LLM 返回的 JSON，自动处理 markdown 包裹和常见格式问题。

      三层防御：
      1. 空内容检测 → RuntimeError（含 node_name）
      2. markdown 代码块剥离
      3. json.loads() + 错误详情

      Raises:
          RuntimeError: 内容为空或 JSON 非法
      """
    if not raw:
        raise RuntimeError(
            f"{node_name}节点 LLM 返回空内容。"
            f"{finish_reason}"
        )

    # 尝试从 markdown 代码块中提取 JSON
    if "```" in raw:
        # 找到第一个 ``` 和最后一个 ``` 之间的内容
        start = raw.find("```")
        end = raw.rfind("```")
        if start != end:
            # 提取代码块内容（跳过 ```json 或 ``` 那一行）
            first_newline = raw.find("\n", start)
            if first_newline != -1 and first_newline < end:
                raw = raw[first_newline:end].strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"{node_name}节点 LLM 返回非法 JSON。原始内容:\n{raw[:500]}"
        )
    return data