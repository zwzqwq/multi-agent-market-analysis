from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END, START
from langchain_core.messages import SystemMessage, HumanMessage
from src.models.contracts import SearchResult, AnalysisReport, DraftReport, AuditResult
from src.models.contracts import Claim, Section, Issue
from datetime import datetime
from src.tools.search_api import tavily_search_tool
from langchain_openai import ChatOpenAI
from src.utils.config import config
import json

MAX_ITERATIONS=3

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
        key_findings=data["findings"],
        contradictions=data["contradictions"],
        gaps=data["gaps"]
    )
    return {
        "analysis":analysis_result
    }

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

AUDITOR_PROMPT="""
你是一个专业的报告审核员，负责审核撰写节点的报告。
你的任务是根据报告的内容，判断是否符合要求。
你需要检查报告中的每个claim，审查清单如下：(evidence_ref对应的是资源编号，即传入sources列表的下标,source中包含snippet摘要和full_text原文，可以通过摘要进行比对，非必要不用从full_text原文比对)
1、引用完整性：evidence_ref字段是否为空？为空则检查inference_type值
   若inference_type为speculation推断，则可以接受
   若为其他（direct_quote、generalization）则不符合要求
2、来源存在性：evidence_ref指向的资源编号是否在搜索结果中存在？
3、主题相关性：检查claim讨论的话题是否和source来源中的话题一致？完全无关：如claim讨论的是“苹果公司”，而source来源中的话题是“气候变化”，则不符合要求
4、逻辑推导性：检查source来源中的信息能否推导出claim中的结论？
    → 来源说"A增速快"，Claim 说"A已是市场第一" → warning（过度推断）
    → 来源说"约60%"，Claim 说"60%" → 可接受
5、interface_type的准确性：
    → direct_quote：来源里有没有直接对应的原文表述？
    → generalization：是否综合了多个来源或多个数据点？
    → speculation：是否确实是推测而非事实陈述？
 
alignment_score 计算规则：
  基础分 = 1.0

  扣分项：
    - 每条检查1违规（无来源的非推测声明）：-0.3
    - 每条检查2违规（来源不存在）：-0.3
    - 每条检查3违规（主题不相关）：-0.2
    - 每条检查4违规（逻辑过度推断）：-0.1
    - 每条检查5违规（inference_type 标注错误）：-0.05

  最低为 0。
输入格式：
{
    "sections": [
        {
            "title": "1. 问题描述",
            "content": "问题描述",
            "claims": []
        },
        {
            "title": "2. 分析结果",
            "content": "分析结果",
            "claims": []
        },
        {
            "title": "3. 结论与建议",
            "content": "结论与建议",
            "claims": []
        }
    ],
    "sources":[
        {
            "title": "2026年AI编程助手市场竞争格局",
            "url": "https://www.example.com/2026-ai-market-competition",
            "snippet": "2026年AI编程助手市场竞争格局报告"
            "full_text": "来源全文内容,可能为空"
        },
    ]
}

输出格式为严格JSON格式（每个字段的值必须简短，description 不超过30字，suggestion 不超过30字），具体如下：
{
    "overall_verdict": "pass" | "minor_issues" | "major_issues",
    "issues":[
    {
        "severity": "critical" | "warning",
        "location": "Section 2, Claim 3",
        "description": "evidence_ref为空，inference_type不是speculation",
        "suggestion": "请检查inference_type是否为"speculation"",
    },
    {
        "severity": "critical" | "warning",
        "location": "Section 2, Claim 4",
        "description": "inference_type不是direct_quote",
        "suggestion": "请检查inference_type是否为"direct_quote"",
    }
    ],
    "alignment_score": 0.9
}
"""

def auditor_node(state: AgentState) -> dict:
    """根据撰写节点的报告，进行审核，审核通过则生成最终报告，否则返回修改意见"""
    draft=state["draft"]
    search=state["search_result"]

    input_data={
        "sections": [
            {
                "title": s.title,
                "content": s.content,
                "claims": [
                    {"text": c.text, "evidence_ref": c.evidence_ref, "inference_type": c.inference_type}
                    for c in s.claims
                ]
            }
            for s in draft.sections
        ],
        "sources": [
            {"id": f"source_{i+1}", "title": s.title, "url": s.url, "snippet": s.snippet}
            for i, s in enumerate(search.sources)
        ]
    }
    messages=[
        SystemMessage(content=AUDITOR_PROMPT),
        HumanMessage(content=f"请审核关于'{state['topic']}'的报告：\n{json.dumps(input_data, ensure_ascii=False)}")
        ]
        
    auditor_llm=ChatOpenAI(
        model=config.MODEL_NAME,
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_BASE_URL,
        max_tokens=2000,
    )
    response=auditor_llm.invoke(messages)
    raw = response.content.strip()

    if not raw:
        raise RuntimeError(
            f"审核节点 LLM 返回空内容。"
            f"finish_reason={response.response_metadata.get('finish_reason', 'N/A')}"
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
            f"审核节点 LLM 返回非法 JSON。原始内容:\n{raw[:500]}"
        )

    overall_verdict = data["overall_verdict"]
    issues = [
        Issue(
            severity=issue["severity"],
            location=issue["location"],
            description=issue["description"],
            suggestion=issue["suggestion"]
        ) for issue in data["issues"]
    ]
    alignment_score = data["alignment_score"]
    return {
        "audit": AuditResult(
            overall_verdict=overall_verdict,
            issues=issues,
            alignment_score=alignment_score
        )
    }

def route_after_audit(state:AgentState):
    """根据审核结果决定下一步，返回裁决值本身（不是目标节点名）"""
    if state["iteration_count"] >= MAX_ITERATIONS or state["audit"].overall_verdict == "pass":
        return "pass"
    else:
        return state["audit"].overall_verdict  # 即 "minor_issues" 或 "major_issues"

def build_workflow():
    """构建 LangGraph 工作流（骨架阶段，节点后续添加）"""
    workflow = StateGraph(AgentState)
    workflow.add_node("search",search_node)
    workflow.add_node("analysis",analysis_node)
    workflow.add_node("write",draft_node)
    workflow.add_node("audit",auditor_node)

    workflow.add_edge(START, "search")
    workflow.add_edge("search", "analysis")
    workflow.add_edge("analysis", "write")
    workflow.add_edge("write", "audit")

    workflow.add_conditional_edges(
     "audit",           # 从哪个节点出发
     route_after_audit, # 路由函数: 读 state → 返回 "pass" / "minor_issues" / "major_issues"
     {
         "pass": END,
         "minor_issues": "write",    # 回到撰写
         "major_issues": "analysis", # 回到分析
     }
    )

    return workflow.compile()