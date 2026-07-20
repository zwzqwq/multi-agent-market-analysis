from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from src.agents.state import AgentState
from src.models.contracts import DraftReport, Section, Claim, Finding
from src.utils.config import config
import json
from datetime import datetime

WRITE_PROMPT = """
你是一个专业的报告撰写员。请根据以下分析结果撰写一份结构化报告。

一、章节结构规则：
报告必须包含以下章节（按顺序排列）：

1. 引言（必写）
   - 介绍分析主题和目的
   - 说明分析范围和方法
   - 篇幅：1-2段

2. 核心发现（必写）
   - 根据 findings 的内容按主题分组撰写
   - 相似主题的发现合并到同一子章节
   - 每个关键断言必须在 claims 中标记
   - 篇幅：根据发现数量决定

3. 矛盾观点（有则写）
   - 如果 contradictions 不为空，必须包含此章节
   - 呈现对立观点及分析节点的裁决结果
   - 如果分析节点已裁决，按裁决结果撰写；如果无法裁决，将正反观点都呈现
   - 篇幅：1-2段/个矛盾

4. 信息缺口（有则写）
   - 如果 gaps 不为空，必须包含此章节
   - 列出当前分析中缺失的信息
   - 提出获取补充信息的建议
   - 篇幅：1段

5. 结论与建议（必写）
   - 总结核心发现
   - 给出基于分析结果的建议
   - 篇幅：1-2段

二、章节内容规则：
1. 章节标题格式："数字. 标题"（如 "1. 引言"）
2. 章节内容必须基于分析结果，不能凭空捏造
3. 每个关键断言必须在 claims 中标记

三、断言处理规则：
1. 对于每个关键发现（Finding），检查是否存在矛盾观点
2. 如果存在矛盾且分析节点已裁决（resolution包含"采信"），按裁决结果撰写
3. 如果存在矛盾且无法裁决（resolution包含"无法调和"），将正反观点都呈现
4. 根据置信度决定表述方式：
   - 置信度 ≥ 0.9：直接陈述为事实，如"AI市场规模已达100亿美元"
   - 置信度 0.7-0.9：陈述并注明来源，如"据TechCrunch报道，AI市场规模达100亿美元"
   - 置信度 < 0.7：使用谨慎表述，如"有观点认为AI市场规模约为100亿美元"
5. 每条断言必须附带 evidence_ref，指向来源编号，对于传入finding中claim对应的多个证据，取用其中第一条作为evidence_ref即可
6. Claim.inference_type 设置规则：
   - 置信度 ≥ 0.9 且证据数量 ≥ 2 → inference_type = "direct_quote"
   - 置信度 ≥ 0.7 → inference_type = "generalization"
   - 置信度 < 0.7 → inference_type = "speculation"

输入格式：
{
    "findings": [...],
    "contradictions": [...],
    "gaps": [...],
    "sources": [...]
}

输出格式（严格JSON）：
{
    "sections": [
        {
            "title": "1. 引言",
            "content": "章节正文",
            "claims": []
        },
        {
            "title": "2. 核心发现",
            "content": "章节正文",
            "claims": [
                {
                    "text": "断言内容",
                    "evidence_ref": "source_1",
                    "inference_type": "direct_quote"
                }
            ]
        },
        {
            "title": "3. 矛盾观点",
            "content": "章节正文",
            "claims": []
        },
        {
            "title": "4. 信息缺口",
            "content": "章节正文",
            "claims": []
        },
        {
            "title": "5. 结论与建议",
            "content": "章节正文",
            "claims": []
        }
    ]
}

注意：如果 contradictions 或 gaps 为空，对应的章节可以省略。
"""

def draft_node(state: AgentState) -> dict:
    """根据分析节点的分析结果，撰写一份结构化报告。"""
    iteration_count=state["iteration_count"]
    if state["draft"] is not None:
        iteration_count+=1
    

    analysis_result = state["analysis"]
    search_result = state["search_result"]
    
    # 构建矛盾映射
    contradiction_map = {}
    for c in analysis_result.contradictions:
        contradiction_map[c.claim_a] = {"opposing": c.claim_b, "resolution": c.resolution}
        contradiction_map[c.claim_b] = {"opposing": c.claim_a, "resolution": c.resolution}
    
    # 准备输入给 LLM
    input_data = {
        "findings": [
            {
                "claim": f.claim,
                "evidence": f.evidence,
                "confidence": f.confidence,
                "has_contradiction": f.claim in contradiction_map,
                "contradiction_info": contradiction_map.get(f.claim)
            }
            for f in analysis_result.key_findings
        ],
        "contradictions": [
            {
                "claim_a": c.claim_a,
                "claim_b": c.claim_b,
                "resolution": c.resolution
            }
            for c in analysis_result.contradictions
        ],
        "gaps": [
          gap for gap in analysis_result.gaps
        ],
        "sources": [
            {"id": f"source_{i+1}", "title": s.title, "url": s.url, "snippet": s.snippet}
            for i, s in enumerate(search_result.sources)
        ]
    }
    
    messages = [
        SystemMessage(content=WRITE_PROMPT),
        HumanMessage(content=f"请撰写关于'{state['topic']}'的报告：\n{json.dumps(input_data, ensure_ascii=False)}")
    ]
    
    llm = ChatOpenAI(
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_BASE_URL,
        model=config.MODEL_NAME,
    )
    response = llm.invoke(messages)
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
            f"撰写节点 LLM 返回非法 JSON。原始内容:\n{raw[:500]}"
        )
    
    # 构建 DraftReport
    sections = []
    for section_data in data["sections"]:
        claims = [
            Claim(
                text=claim_data["text"],
                evidence_ref=claim_data.get("evidence_ref"),
                inference_type=claim_data.get("inference_type", "speculation")
            )
            for claim_data in section_data.get("claims", [])
        ]
        section = Section(
            title=section_data["title"],
            content=section_data["content"],
            claims=claims
        )
        sections.append(section)
    
    draft = DraftReport(
        topic=state["topic"],
        sections=sections,
        metadata={"generated_at": datetime.now().isoformat()}
    )
    
    return {
        "draft": draft,
        "iteration_count": iteration_count
        }
