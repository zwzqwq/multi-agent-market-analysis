"""parse_llm_json() 单元测试

被测函数的完整签名:
    parse_llm_json(raw: str, finish_reason: str, node_name: str = "unknown") -> dict

三层防御：
    1. 空内容检测 → RuntimeError
    2. markdown 代码块剥离（```json 或 ``` 包裹）
    3. json.loads() + 错误详情
"""

import pytest
from src.utils.json_parser import parse_llm_json


# ============================================================
# 第一类：正常输入（Happy Path）
# ============================================================

def test_clean_json():
    """最普通的合法 JSON，不包含任何 markdown 包裹"""
    result = parse_llm_json(
        '{"key": "value", "num": 42}',
        finish_reason="stop",
        node_name="测试",
    )
    assert result == {"key": "value", "num": 42}


def test_json_with_chinese():
    """JSON 中包含中文字符 — 项目实际场景"""
    result = parse_llm_json(
        '{"claim": "AI芯片市场增长迅速", "confidence": 0.9}',
        finish_reason="stop",
        node_name="分析",
    )
    assert result["claim"] == "AI芯片市场增长迅速"
    assert result["confidence"] == 0.9


def test_nested_dict():
    """嵌套结构的 JSON（类似 analysis 节点返回的 findings 数组）"""
    raw = '''{
        "findings": [
            {"claim": "市场第一", "confidence": 0.95},
            {"claim": "增长趋势", "confidence": 0.8}
        ],
        "gaps": ["缺少竞品数据"]
    }'''
    result = parse_llm_json(raw, finish_reason="stop", node_name="分析")
    assert len(result["findings"]) == 2
    assert result["findings"][0]["claim"] == "市场第一"
    assert result["gaps"] == ["缺少竞品数据"]


# ============================================================
# 第二类：Markdown 代码块剥离（LLM 最常见的行为）
# ============================================================

def test_markdown_json_block():
    """LLM 输出包在 ```json ... ``` 里 — 最常见的情况"""
    raw = '''```json
{"key": "value"}
```'''
    result = parse_llm_json(raw, finish_reason="stop", node_name="测试")
    assert result == {"key": "value"}


def test_markdown_block_no_language():
    """LLM 输出包在 ``` ... ``` 里，但没有写 json 语言标识"""
    raw = '''```
{"items": [1, 2, 3]}
```'''
    result = parse_llm_json(raw, finish_reason="stop", node_name="测试")
    assert result == {"items": [1, 2, 3]}


def test_markdown_block_with_chinese():
    """markdown 包裹 + 中文内容 — 项目实际场景"""
    raw = '''```json
{
    "overall_verdict": "pass",
    "issues": [],
    "alignment_score": 1.0
}
```'''
    result = parse_llm_json(raw, finish_reason="stop", node_name="审核")
    assert result["overall_verdict"] == "pass"
    assert result["alignment_score"] == 1.0


def test_markdown_block_with_extra_text():
    """LLM 有时候在代码块外还会加说明文字"""
    raw = '''好的，以下是分析结果：

```json
{"findings": [], "gaps": ["数据不足"]}
```

请审阅。'''
    result = parse_llm_json(raw, finish_reason="stop", node_name="分析")
    assert result["gaps"] == ["数据不足"]


# ============================================================
# 第三类：错误输入 — 应抛出 RuntimeError
# ============================================================

def test_empty_string_raises():
    """空字符串 → RuntimeError（空内容检测是第一层防御）"""
    with pytest.raises(RuntimeError, match="空内容"):
        parse_llm_json("", finish_reason="stop", node_name="测试")


def test_none_raises():
    """None 传入 — 当前实现 not '' = True，not None = True 都会被拦截"""
    # 注意：not None 为 True，所以和空字符串走同一个分支
    with pytest.raises(RuntimeError):
        parse_llm_json(None, finish_reason="stop", node_name="测试")


def test_invalid_json_raises():
    """非 JSON 字符串 → RuntimeError（json.loads 抛 JSONDecodeError）"""
    with pytest.raises(RuntimeError, match="非法 JSON"):
        parse_llm_json(
            "这不是JSON，是LLM的自由发挥文本",
            finish_reason="stop",
            node_name="分析",
        )


def test_partial_json_raises():
    """看起来像 JSON 但格式不对 — 少了一个引号"""
    with pytest.raises(RuntimeError, match="非法 JSON"):
        parse_llm_json(
            '{"key": "unclosed string}',
            finish_reason="stop",
            node_name="测试",
        )


def test_markdown_block_but_no_json_inside():
    """代码块包裹但内部不是 JSON — 剥离后 json.loads 会报错"""
    raw = '''```json
这不是 JSON 内容
```'''
    with pytest.raises(RuntimeError, match="非法 JSON"):
        parse_llm_json(raw, finish_reason="stop", node_name="测试")


# ============================================================
# 第四类：边界情况
# ============================================================

def test_triple_backtick_in_json_value():
    """JSON 值的字符串里包含 ``` — 不应该被误剥离"""
    # 构造: 一个 JSON 字符串值里包含了三个反引号
    raw = '{"code_example": "print(```hello```)"}'
    result = parse_llm_json(raw, finish_reason="stop", node_name="测试")
    assert result["code_example"] == "print(```hello```)"


def test_only_backticks_no_json():
    """只有 ``` 没有 JSON — 不会被剥离，但 json.loads 失败"""
    # 注意: parse_llm_json 发现 ``` 后会找 start 和 end，
    # 如果 start==end（就一个 ```），不剥离，原样给 json.loads
    raw = "```"
    with pytest.raises(RuntimeError, match="非法 JSON"):
        parse_llm_json(raw, finish_reason="stop", node_name="测试")


def test_array_root():
    """JSON 根元素是数组而非对象 — json.loads 可以解析"""
    result = parse_llm_json(
        '[{"a": 1}, {"b": 2}]',
        finish_reason="stop",
        node_name="测试",
    )
    assert len(result) == 2
    assert result[0]["a"] == 1


def test_single_backtick_pair():
    """只在开头和结尾各有一个 ``` 才算代码块，中间有三个才算"""
    # 输入开头有 ```，结尾有 ``` → start != end → 剥离
    raw = '```\n{"key": "value"}\n```'
    result = parse_llm_json(raw, finish_reason="stop", node_name="测试")
    assert result == {"key": "value"}


def test_finish_reason_in_error_message():
    """finish_reason 出现在空内容错误信息中 — 排查问题时需要"""
    with pytest.raises(RuntimeError, match="length"):
        parse_llm_json("", finish_reason="length", node_name="分析")
