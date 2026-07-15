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
- LLM 调用: LangChain + OpenAI-compatible API（默认 DeepSeek）
- 搜索工具: Tavily Search API（需科学上网）
- 数据结构: Pydantic v2
- 输出格式: Markdown 文件
- 项目管理: uv + venv + git

---

## 数据流全链路（具体示例）

以用户输入 "2026年AI编程助手市场竞争格局" 为例，展示 4 个契约如何在实际运行中串联。

### 节点1: 搜索Agent → 产出 SearchResult

```
输入: "2026年AI编程助手市场竞争格局"
动作: 拆成 3-5 个子查询 → 调 Tavily → 取每页 top5 → 去重

SearchResult(
    query="2026年AI编程助手市场竞争格局",
    sources=[
        Source(title="GitHub Copilot 市场份额...", url="https://...",
               snippet="占据约60%市场份额...", full_text="...(全文)..."),
        Source(title="Cursor 融资..."),
        Source(title="国内AI编程工具..."),
        ...共12条
    ],
    timestamp=2026-07-11 10:30:00
)
```

### 节点2: 分析Agent → 产出 AnalysisReport

```
输入: SearchResult (12条 source)
动作: 逐条阅读 → 提取关键声明 + 标注证据 → 交叉比对矛盾 → 标记信息缺口

AnalysisReport(
    topic="2026年AI编程助手市场竞争格局",
    key_findings=[
        Finding(
            claim="GitHub Copilot 占据约60%市场份额",
            evidence=["sources[0]", "sources[5]"],
            confidence=0.85,
            counter_evidence=["sources[3]称Cursor增速更快，但绝对值仍小于Copilot"]
        ),
        Finding(
            claim="国内工具(通义灵码/CodeBuddy)主打免费+中文生态",
            evidence=["sources[4]", "sources[9]"],
            confidence=0.70,
        ),
        ...共5条
    ],
    contradictions=[
        Contradiction(
            claim_a="source[0]称Copilot 60%",
            claim_b="source[7]称Copilot 52%",
            resolution="采信source[0]，数据更新(2026.06 vs 2025.12)"
        )
    ],
    gaps=["缺少中国以外亚洲市场数据", "企业版定价信息不完整"]
)
```

### 节点3: 撰写Agent → 产出 DraftReport

```
输入: AnalysisReport
动作: 按章节组织 → 转可读文字 → 每个断言打 Claim 标注

DraftReport(
    topic="2026年AI编程助手市场竞争格局",
    sections=[
        Section(
            title="一、市场概述",
            content="2026年，AI编程助手市场持续高速增长...",
            claims=[
                Claim(text="Copilot占据约60%市场份额",
                      evidence_ref="sources[0]",
                      inference_type="direct_quote"),
                Claim(text="新兴工具增速远超老牌产品",
                      evidence_ref="sources[1],sources[5]",
                      inference_type="generalization"),
                Claim(text="中国市场将在两年内爆发",
                      evidence_ref=None,              ← 无证据！
                      inference_type="speculation"),
            ]
        ),
        ...共4个Section
    ]
)
```

### 节点4: 审核Agent → 产出 AuditResult

```
输入: DraftReport
动作: 遍历每个Claim → 比对原文 → 检查推理类型 → 标记无证据声明

AuditResult(
    overall_verdict="minor_issues",
    alignment_score=0.72,
    issues=[
        Issue(
            severity="critical",
            location="Section 1, Claim 3",
            description="'中国市场两年内爆发'无任何证据支持",
            suggestion="删除此句，或标注为'作者推测'"
        ),
        Issue(
            severity="warning",
            location="Section 1, Claim 1",
            description="声称'60%'但source[0]原文为'about three-fifths'",
            suggestion="改为'约60%'或'接近五分之三'"
        )
    ]
)
```

### 路由决策

```
alignment_score=0.72 → 0.5 ≤ 0.72 < 0.8 → minor_issues
→ 携带 issues 回到撰写Agent局部修改
→ 修改后再次审核 → alignment_score=0.85 → pass → 输出最终报告
```

---

## Agent 节点设计实录（初始设计 · v0.1）

> 记录每个 Agent 节点的设计过程、关键决策和实现细节。
> 后续功能迭代时，在对应节点下追加变更记录。

---

### 搜索 Agent（search_node）

**状态**: 已实现 · 已测试

**文件**: `src/graph/workflow.py` (内联), `src/tools/search_api.py`

**设计过程**:

搜索是工作流的起点。最初在 Tavily 和 DuckDuckGo 之间选择——DuckDuckGo 免费且不需要科学上网，但搜索结果质量不稳定（返回的是摘要而非全文，且中文搜索效果差）。最终选择 Tavily：AI 优化的搜索结果 + 每月 1000 次免费额度，代价是需要科学上网。

搜索工具封装成独立类 `TavilySearchTool`，原因：
- 搜索逻辑可能后续扩展（换 API、加缓存、加重试）
- 与 Agent 节点解耦，方便单独测试

**实现要点**:
- `TavilySearchTool.search(query, max_results=5)` → `list[Source]`
- 去重逻辑：用 `url` 做唯一键，检查再添加（而非添加后再检查）
- 模块级单例 `tavily_search_tool`，避免重复初始化

**已解决问题**:
- API Key 读取失败 → 在模块顶层加 `load_dotenv()`（config.py 和 search_api.py 各调用一次，暂无害但需后续统一）
- 去重逻辑反写 → 先检查 `if url in urlsets: continue`，再 `urlsets.add(url)`
- 缺少 `return sources` → 补充返回语句

---

### 分析 Agent（analysis_node）

**状态**: 已实现 · 已测试

**文件**: `src/graph/workflow.py` (内联), Prompt 常量 `ANALYSIS_PROMPT`

**设计起点**:

问题：分析 Agent 和第一个项目的 KnowledgeExtractor 技术模式相同（LLM + SystemPrompt → JSON → Pydantic），那它们的本质区别在哪？

```
项目1 KnowledgeExtractor:
  输入: 文本段落
  输出: (实体, 关系, 实体) 三元组
  逻辑: "文本里有什么" → 拆散信息，方便检索
  
项目2 Analysis Agent:
  输入: 多条搜索结果
  输出: 发现 + 置信度 + 矛盾裁决 + 缺口
  逻辑: "文本里说的对不对" → 评估信息，判断可信度
```

同样的技术模式，完全不同的设计意图。**技术在变，但"把意图翻译成约束条件"的能力不变。**

**核心设计原则**:

把主观判断翻译成 LLM 可以执行的客观检查清单。不说"判断可信度"（LLM 不知道怎么做），而是说"检查是否有两个以上独立来源、来源是不是官方数据"（LLM 能在文本中找到答案）。

**Prompt 设计**:

分析 Agent 的 Prompt 是四个节点中最复杂的，因为需要同时规范"输出格式"和"判断标准"。

两个关键设计手段：

1. **置信度锚点** — 把 0-1 的连续值拆成 5 个有具体条件的区间：

| 区间 | 条件 | LLM 检查项 |
|---|---|---|
| 0.9-1.0 | 至少2个独立来源交叉印证，或来源为官方数据 | 数来源数量 + 判断来源类型 |
| 0.7-0.9 | 单一但权威来源，或多个普通来源一致 | 判断来源权威性 |
| 0.5-0.7 | 来源有偏差（官方自述），或信息超过1年 | 判断偏差 + 检查时效 |
| 0.3-0.5 | 低权威来源，或大量推测 | 判断来源质量 |
| <0.3 | 与高置信发现矛盾，或来源失效/过时3年+ | 比对矛盾 + 检查链接有效性 |

2. **矛盾决策树** — 三种情况按优先级处理：

```
规则1: 同指标不同数字 → 比较时效性（数据更新者优先）
规则2: 同话题相反结论 → 比较权威性（官方 > 媒体 > 公司 > 个人）
规则3: 无法判断 → 标记"未解决"（这本身就是有价值的分析结论）
```

3. **字段区分**: `counter_evidence`（单个 Finding 内部的反对证据）vs `Contradiction`（两个不同 Finding 之间的冲突）——不同层面，不同处理。

**实现要点**:
- `sources_text` 用 `【来源1】【来源2】` 格式编码，证据引用统一用来源编号
- `topic` 字段不从 LLM 返回中取，而从 `state["topic"]` 注入（避免 LLM 改写 + 节省 token）
- JSON 解析：`response.content → json.loads() → AnalysisReport(...)`

**测试结果** (2026-07-12):

搜索主题: "2026年AI编程助手市场竞争格局"

| 指标 | 结果 |
|---|---|
| 搜索来源数 | 5 |
| 关键发现 | 7 条，置信度范围 0.3-0.9 |
| 矛盾 | 2 组，均给出裁决理由 |
| 信息缺口 | 4 个（市场份额统一标准、国内工具数据、行业预测、x86关联性） |

置信度分布验证了 Prompt 锚点生效：
- IDC 评测数据 9.8/10 → 置信度 **0.9**（多来源交叉印证 → 正确触发 0.9-1.0 区间）
- Cursor 评分 9.4/10 → 置信度 **0.8**（单一权威来源 → 正确触发 0.7-0.9 区间）
- AI 编程渗透率 17.3% → 置信度 **0.3**（单一低权威来源 → 正确触发 0.3-0.5 区间）

矛盾裁决逻辑生效：第一条 contradiction 的 resolution 写道"行业无统一排名标准"——这是规则 3 的效果。

---

### 撰写 Agent（writer_node）

**状态**: 未实现

**文件**: 待定（`src/graph/workflow.py` 内联 或 `src/agents/writer.py`）

**设计方向**: 消费 AnalysisReport → 按章节组织 → 转可读文字 → 每个断言打 Claim 标注（标注溯源和推理类型）

---

### 审核 Agent（auditor_node）

**状态**: 未实现

**文件**: 待定（`src/graph/workflow.py` 内联 或 `src/agents/auditor.py`）

**设计方向**: 遍历每个 Claim → 比对原文 → 检查推理类型 → 标记无证据声明 → 输出 verdict + alignment_score

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
