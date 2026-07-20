from langchain_core.messages import SystemMessage, HumanMessage
from src.agents.state import AgentState,MAX_ITERATIONS
from src.models.contracts import AuditResult, Claim, Section, Finding, Source, Issue
from src.utils.config import config
import json
from src.utils.logger import logger
from src.utils.llm_retry import call_llm_with_retry

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
        "suggestion": "请检查inference_type是否为'speculation'",
    },
    {
        "severity": "critical" | "warning",
        "location": "Section 2, Claim 4",
        "description": "inference_type不是direct_quote",
        "suggestion": "请检查inference_type是否为'direct_quote'",
    }
    ],
    "alignment_score": 0.9
}
"""

def auditor_node(state: AgentState) -> dict:
    """根据撰写节点的报告，进行审核，审核通过则生成最终报告，否则返回修改意见"""
    logger.info(f"开始审核关于 '{state['topic']}' 的报告...")
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
        
    data = call_llm_with_retry(messages, node_name="审核")

    overall_verdict = data["overall_verdict"]
    issues = [
        Issue(
            severity=issue["severity"],
            location=issue["location"],
            description=issue["description"],
            suggestion=issue.get("suggestion", "")
        ) for issue in data["issues"]
    ]
    alignment_score = data["alignment_score"]
    logger.info(f"审核关于 '{state['topic']}' 的报告完成，结果为 {overall_verdict}")
    return {
        "audit": AuditResult(
            overall_verdict=overall_verdict,
            issues=issues,
            alignment_score=alignment_score
        )
    }
    

def route_after_audit(state:AgentState):
    """根据审核结果决定下一步，返回裁决值本身（不是目标节点名）"""
    if state["iteration_count"] >= MAX_ITERATIONS:
        return "force_pass"
    elif state["audit"].overall_verdict == "pass":
        return "pass"
    else:
        return state["audit"].overall_verdict  # 即 "minor_issues" 或 "major_issues"