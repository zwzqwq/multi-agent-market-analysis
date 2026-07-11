"""
Agent 间通信的 Pydantic 数据契约。

每一个模型定义了工作流中一个阶段的输入/输出格式。
Agent 不直接传 dict 或字符串，而是传这些结构化的对象。
编译期即可检查格式是否正确，避免运行时的 "KeyError"。
"""

from datetime import datetime
from pydantic import BaseModel, Field


# =============================================================================
# 节点 1 → 节点 2: 搜索Agent 产出，分析Agent 消费
# =============================================================================

class Source(BaseModel):
    """一条搜索结果"""
    title: str
    url: str
    snippet: str
    full_text: str | None = None  # 需要时才抓取全文，节省token


class SearchResult(BaseModel):
    """搜索阶段的总产出"""
    query: str
    sources: list[Source]
    timestamp: datetime = Field(default_factory=datetime.now)


# =============================================================================
# 节点 2 → 节点 3: 分析Agent 产出，撰写Agent 消费
# =============================================================================

class Finding(BaseModel):
    """一个分析发现：声明 + 证据 + 置信度"""
    claim: str
    evidence: list[str] = []        # 指向 source 的索引，如 "sources[0]"
    confidence: float = Field(ge=0, le=1)
    counter_evidence: list[str] = []


class Contradiction(BaseModel):
    """两条相互矛盾的声明"""
    claim_a: str
    claim_b: str
    resolution: str  # 分析后的处理方式："采信A，因为时间更新" / "无法调和，两说并陈"


class AnalysisReport(BaseModel):
    """分析阶段的总产出"""
    topic: str
    key_findings: list[Finding]
    contradictions: list[Contradiction] = []
    gaps: list[str] = []  # 信息缺口


# =============================================================================
# 节点 3 → 节点 4: 撰写Agent 产出，审核Agent 消费
# =============================================================================

class Claim(BaseModel):
    """报告中的一条断言，附带溯源信息——这是审核Agent能干活的关键"""
    text: str
    evidence_ref: str | None = None  # 指向哪个 source，如 "source_3"
    inference_type: str = "speculation"  # direct_quote | generalization | speculation


class Section(BaseModel):
    """报告的一个章节"""
    title: str
    content: str
    claims: list[Claim] = []


class DraftReport(BaseModel):
    """报告草稿"""
    topic: str
    sections: list[Section]
    metadata: dict = {}


# =============================================================================
# 节点 4 → 路由: 审核Agent 产出，LangGraph 路由消费
# =============================================================================

class Issue(BaseModel):
    """审核发现的一个问题"""
    severity: str  # "critical" | "warning"
    location: str  # 如 "Section 2, Claim 3"
    description: str
    suggestion: str


class AuditResult(BaseModel):
    """审核结果"""
    overall_verdict: str  # "pass" | "minor_issues" | "major_issues"
    issues: list[Issue] = []
    alignment_score: float = Field(ge=0, le=1)
