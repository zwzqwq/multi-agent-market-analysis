from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from src.agents.state import AgentState
from src.models.contracts import AnalysisReport, Finding, Contradiction, Source
from src.utils.config import config
import json

ANALYSIS_PROMPT = """
你是一个专业的信息分析员，请根据以下搜索结果，从搜索结果中提取关键发现、标注证据、发现矛盾，并生成一份分析报告。

规则：
1、关键发现：根据搜索获取的关键信息、核心观点，对应字段为 "claim"
2、证据：搜索结果中用于支持上一个字段（关键信息）的证据，对应字段为 "evidence",没有明确的证据则为空，证据字段填搜索节点搜索到的来源编号，不是原文
  证据按相关性从高到低排序——最能支撑 claim 的来源放第一位。
3、置信度：对于搜索出的每条关键信息，根据其证据以及时效性，基于你的以下规则判断，给出0-1之间的置信度，0表示完全不信，1表示完全信。
    置信度标准（你作为分析师的判断依据）：

  0.9-1.0（可确认事实）：
    → 至少2个独立来源交叉印证
    → 来源为官方数据（公司财报、政府统计、官方公告）
    → 例：两家独立媒体都报道"Copilot用户数突破1亿"

  0.7-0.9（高置信推断）：
    → 单一来源但来源权威（知名科技媒体、学术论文）
    → 或：多个来源一致但来源权威性一般
    → 例：TechCrunch独家报道某公司融资，无其他来源印证

  0.5-0.7（可能性较高）：
    → 来源有潜在偏差（公司自家博客、CEO采访）
    → 或：信息时效性存疑（超过1年）
    → 例：某公司官网声称"市场第一"，无第三方数据支撑

  0.3-0.5（待验证）：
    → 单一来源且来源权威性低（个人博客、论坛帖子）
    → 或：结论依赖大量推测
    → 例：某博主预测"XX市场将在半年内爆发"

  低于0.3（不可采信）：
    → 与其他高置信度发现直接矛盾
    → 来源已失效（404链接）或明显过时（3年以上）
4、矛盾：如果搜索结果中存在多个关键信息，且其中包含矛盾，对应字段为 "counter_evidence"，矛盾字段填搜索节点搜索到的来源编号，不是原文
矛盾处理规则（按优先级执行）：

  规则1 — 同指标不同数字 → 比较时效性
    → 数据更新的来源优先
    → 在 resolution 中写明"采信source[X]，数据更新（2026.06 vs 2025.12）"

  规则2 — 同话题相反结论 → 比较来源权威性
    → 官方数据 > 知名媒体 > 公司自述 > 个人博客
    → 在 resolution 中写明"采信source[A]（官方财报）而非source[B]（匿名论坛）"

  规则3 — 无法判断 → 标记为"未解决"
    → 双方来源权威性相当，时效性相当
    → resolution 写"两方均有可信来源，无法裁决，建议读者注意此争议"
    → 这种情况本身就说明"行业尚无共识"——这也是有价值的分析结论
5、矛盾实体：如果搜索结果中存在多个关键信息，且其中包含矛盾，使用一个Contradiction类来表示矛盾信息。
6、矛盾和矛盾实体：counter_evidence 是单个 Finding 内部的反对证据，Contradiction 是两个不同 Finding
  之间的冲突。 加上这句区分就够了
7、信息缺口：如果搜索结果中存在多个关键信息，且其中包含信息缺口，对应字段为 "gaps"

输出格式规定（严格JSON，不能包含任何非JSON字符）：
{
    "findings":[
    {
        "claim":"XXX",
        "evidence":["source_1","source_2"],
        "confidence":0.9,# 置信度
        "counter_evidence":["source_1","source_2"],
    },
    ],
    "contradictions":[
    {
        "claim_a":"XXX",
        "claim_b":"XXX",
        "resolution":"XXX",
    },
    ],
    "gaps":[
    "XXX",
    ]
}
"""

def analysis_node(state:AgentState)->dict:
    source_result=state["search_result"]
    sources=source_result.sources
    sources_text="\n\n".join(f"【来源{i+1}】{source.title}\n链接：{source.url}\n摘要：{source.snippet}" for i,source in enumerate(sources))
    
    messages=[
        SystemMessage(content=ANALYSIS_PROMPT),
        HumanMessage(content=f"请分析以下文本：{sources_text}")
        ]
    
    analysis_llm= ChatOpenAI(
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_BASE_URL,
        model=config.MODEL_NAME,
    )
    response=analysis_llm.invoke(messages)
    raw = response.content.strip()

    if "```" in raw:
        start = raw.find("```")
        end = raw.rfind("```")
        if start != end:
            first_newline = raw.find("\n", start)
            if first_newline != -1 and first_newline < end:
                raw = raw[first_newline:end].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"分析节点 LLM 返回非法 JSON。原始内容:\n{raw[:500]}"
        )
    analysis_result=AnalysisReport(
        topic=state["topic"],
        key_findings=[
            Finding(
                claim=f["claim"],
                evidence=f.get("evidence", []),
                confidence=f["confidence"],
                counter_evidence=f.get("counter_evidence") or []
            )
            for f in data["findings"]
        ],
        contradictions=data.get("contradictions", []),
        gaps=data.get("gaps", [])
    )
    return {
        "analysis":analysis_result
    }