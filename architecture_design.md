# 多Agent市场分析报告生成系统 — 架构设计文档

## 系统架构总览

                          ┌─────────────────────────┐
                          │      用户 (CLI)          │
                          │  输入: "2026年AI编程      │
                          │  助手市场竞争格局"        │
                          └───────────┬─────────────┘
                                      │ topic: str
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        LangGraph StateGraph                         │
│                                                                     │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐          │
│   │  节点 1     │     │  节点 2     │     │  节点 3     │          │
│   │  搜索Agent  │────▶│  分析Agent  │────▶│  撰写Agent  │──┐       │
│   │             │     │             │     │             │  │       │
│   │ 职责:       │     │ 职责:       │     │ 职责:       │  │       │
│   │ 收集原始    │     │ 提取关键    │     │ 结构化输出  │  │       │
│   │ 信息源      │     │ 发现+交叉   │     │ 为报告章节  │  │       │
│   │             │     │ 验证        │     │             │  │       │
│   └─────────────┘     └─────────────┘     └─────────────┘  │       │
│                                                             │       │
│                                          ┌──────────────────┘       │
│                                          ▼                          │
│                               ┌─────────────────┐                   │
│                               │  节点 4         │                   │
│                               │  审核Agent      │                   │
│                               │                 │                   │
│                               │  职责:          │                   │
│                               │  逻辑对齐检查   │                   │
│                               │  (证据→推论→    │                   │
│                               │   结论的链条)   │                   │
│                               └────────┬────────┘                   │
│                                        │                            │
│                          ┌─────────────┼─────────────┐              │
│                          ▼             ▼             ▼              │
│                     通过 (✓)     小问题 (⚠)    严重问题 (✗)         │
│                          │             │             │              │
│                          ▼             ▼             ▼              │
│                      输出报告      返回撰写      返回分析            │
│                                    Agent          Agent              │
│                                    (局部修改)     (重新推理)         │
└─────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                          ┌─────────────────────────┐
                          │  输出: report_xxx.md    │
                          │  + sources.json         │
                          │  + audit_log.json       │
                          └─────────────────────────┘

---

## 核心数据契约（Agent 间通信协议）

### SearchResult (搜索Agent → 分析Agent)
- query: str              # 实际搜索的查询词
- sources: list[Source]   # 搜索结果列表
  - title: str
  - url: str
  - snippet: str
  - full_text: str | None
- timestamp: datetime

### AnalysisReport (分析Agent → 撰写Agent)
- topic: str              # 原始主题
- key_findings: list[Finding]
  - claim: str            # 核心声明（如"某公司市场份额第一"）
  - evidence: list[str]   # 支撑该声明的证据索引（指向SearchResult）
  - confidence: float     # 置信度 0~1
  - counter_evidence: list[str]  # 反面证据
- contradictions: list[Contradiction]
  - claim_a: str
  - claim_b: str
  - resolution: str       # "A和B不可调和" / "A时间更近，优先A"
- gaps: list[str]         # 信息缺口（如"缺少中国市场的具体数据"）

### DraftReport (撰写Agent → 审核Agent)
- sections: list[Section]
  - title: str
  - content: str
  - claims: list[Claim]   # 该章节中所有断言
    - text: str
    - evidence_ref: str | None   # 指向哪个source
    - inference_type: str        # "direct_quote" | "generalization" | "speculation"
- metadata: dict

### AuditResult (审核Agent → 路由决策)
- overall_verdict: "pass" | "minor_issues" | "major_issues"
- issues: list[Issue]
  - severity: "critical" | "warning"
  - location: str         # 在哪个section、哪个claim
  - description: str      # 问题描述
  - suggestion: str
- alignment_score: float  # 0~1，衡量 证据→推论→结论 的对齐程度

---

## 状态流转

graph LR
    START --> search
    search --> analyze
    analyze --> write
    write --> audit
    audit -->|pass| END
    audit -->|minor_issues| write    (带着issue列表回去改)
    audit -->|major_issues| analyze  (推理链断了，需要重新分析)

### 路由逻辑
- **pass**: alignment_score ≥ 0.8，直接输出
- **minor_issues**: 0.5 ≤ score < 0.8，局部问题（措辞不准确、引用缺失），回撰写节点修改
- **major_issues**: score < 0.5，存在逻辑断裂（证据链推导不出结论），回分析节点重新推理

---

## 四个核心设计点

| 设计点 | 说明 |
|---|---|
| 类型驱动的通信协议 | 所有 Agent 间通过 Pydantic 模型通信，编译期即可检查数据格式 |
| 有状态回退 | 审核不通过不是"从头再来"，而是回到出问题的节点，保留前面正确的结果 |
| 证据链可追溯 | 每条结论都标注了来源和推理类型，审核 Agent 可以精确指出"从哪一步开始断的" |
| 和第一个项目互补 | 项目1是"检索→回答"（被动响应），项目2是"收集→分析→撰写→审核"（主动生成+多Agent协作） |

---

## 技术栈

- 编排框架: LangGraph
- LLM 调用: LangChain + OpenAI-compatible API
- 搜索工具: Tavily Search API
- 数据结构: Pydantic v2
- 输出格式: Markdown 文件
- 项目管理: uv + venv + git

---

## 目录结构（规划）

```
second-project/
├── src/
│   ├── __init__.py
│   ├── main.py              # 入口
│   ├── graph/
│   │   ├── __init__.py
│   │   └── workflow.py      # StateGraph 定义
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── search.py        # 搜索 Agent
│   │   ├── analyzer.py      # 分析 Agent
│   │   ├── writer.py        # 撰写 Agent
│   │   └── auditor.py       # 审核 Agent
│   ├── models/
│   │   ├── __init__.py
│   │   └── contracts.py     # Pydantic 数据契约
│   ├── tools/
│   │   ├── __init__.py
│   │   └── search_api.py    # 搜索 API 封装
│   └── utils/
│       ├── __init__.py
│       ├── config.py        # 配置管理
│       └── logger.py        # 日志
├── outputs/                  # 生成的报告
├── tests/
├── pyproject.toml
├── dev_issues_log.md
└── interview_qa.md
```
