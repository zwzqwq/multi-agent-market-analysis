# 面试问答积累

> 随开发推进，持续记录可能被问到的技术问题及回答要点

---

## 项目概述

**一句话描述**：一个基于 LangGraph 的多 Agent 市场分析报告生成系统，四个 Agent（搜索、分析、撰写、审核）协作完成从信息收集到报告输出的完整流程。

**和第一个项目（知识库问答助手）的互补关系**：
- 项目1：检索式，被动响应，单 Agent + RAG
- 项目2：生成式，主动产出，多 Agent 协作 + 状态图编排

**技术栈**：Python / LangGraph / LangChain / Pydantic / FastAPI / Gradio / LangSmith

---

## 必问问题：项目整体架构

**Q: 介绍一下你的第二个项目？**

**答题框架（3 分钟版本）**：

1. **做什么**：用户输入一个市场分析主题 → 系统自动搜索互联网信息 → 分析提取关键发现 → 撰写结构化报告 → 审核质量 → 输出 Markdown 报告

2. **四个 Agent 各司其职**：
   - 搜索 Agent：调 Tavily API 收集原始信息来源
   - 分析 Agent：从搜索结果中提取关键发现、标注置信度（0-1）、裁决矛盾观点、识别信息缺口
   - 撰写 Agent：按 5 章结构（引言/核心发现/矛盾观点/信息缺口/结论建议）生成可读报告，每个断言标注来源和推理类型
   - 审核 Agent：对撰写产出做 5 项检查（引用完整性/来源存在性/主题相关性/逻辑推导性/inference_type 准确性），输出评分和修改意见

3. **回退闭环**：审核不通过时根据问题严重程度走不同路径 —— 小问题回撰写节点局部修改，大问题回分析节点重新推理。最多迭代 3 轮，超限强制输出并加质量声明

4. **工程配套**：FastAPI + Gradio 接口层，后台异步任务执行，LangSmith 全链路追踪，统一日志系统（按天轮转）

---

## 架构设计类问题

### Q: 为什么用四个 Agent 而不是一个大 Prompt 全搞定？

**面试说辞**：
1. **幻觉防线**：单个 LLM 既当运动员又当裁判员，编造了数据没人发现。分析→审核的双 Agent 设计天然形成"第二道防线"
2. **分工降低复杂度**：每个 Agent 的 Prompt 只需关注一个领域的规则。分析 Agent 专注"怎么判断可信度"，审核 Agent 专注"怎么检查事实性错误"。一个 Prompt 管所有事 → 注意力稀释，质量下降
3. **回退粒度可控**：审核发现小问题只需改措辞，回撰写；发现大问题（推理链断裂）必须重分析。如果全塞一个 Prompt，出错了只能"全部重来"

### Q: 为什么用 LangGraph 而不是自己写 if/else 逻辑？

1. **状态管理**：5 个节点共享 State，LangGraph 自动处理 state 的传递和合并，不用手动传参
2. **条件路由**：`add_conditional_edges(audit, route_fn, mapping)` 声明式定义回退逻辑，比嵌套 if/else 清晰
3. **可观测性**：LangGraph 原生集成 LangSmith，每个节点的输入/输出/耗时自动追踪，不用手写埋点
4. **扩展性**：后续想加并行 Agent（如多个搜索源并行搜），改图结构就行，不需要改业务代码

### Q: 回退循环会不会无限跑下去？

用 `MAX_ITERATIONS=3` + `force_pass` 机制兜底。设计思路和网络请求的超时重试一样——"不完美的报告"比"没有报告"好。达到上限后依然输出，但在报告开头插入 `[质量声明]` 章节，告诉读者"本报告经 3 轮审核未完全达标，建议人工复核"。

### Q: 四个 Agent 之间怎么传递数据？

通过 Pydantic 类型契约：
```
SearchResult → AnalysisReport → DraftReport → AuditResult
```
每个 Agent 的输入输出都是固定的 Pydantic 模型，编译期就能检查数据格式是否正确。跟 Microservices 的 Schema Registry 一个道理——保证上下游不会因为"我以为你有这个字段"而炸。

---

## LLM / Prompt 工程类问题

### Q: 怎么处理 LLM 返回格式不稳定的问题？

**三层防御**：
1. **Markdown 剥离**：LLM 几乎总会把 JSON 包在 ` ```json ``` ` 里 → 写代码清洗，不依赖 Prompt 约束
2. **字段级 .get() 防御**：LLM 偶尔省略可选字段 → 所有取值用 `.get("field", default)` 而非方括号
3. **温度递增重试**：空内容或 JSON 非法时重试（最多 3 次），每次温度递增（0→0.3→0.6），打破确定性输出的死循环

核心原则：**永远不要信任 LLM 的输出格式**，用代码防御而非 Prompt 约束。

### Q: 分析 Agent 的置信度（0-1）怎么定的？

把主观判断翻译成 LLM 可以执行的客观检查清单：
- 0.9-1.0：至少 2 个独立来源交叉印证，或官方数据 → 可确认事实
- 0.7-0.9：单一权威来源 → 高置信推断
- 0.5-0.7：来源有潜在偏差 → 可能性较高
- 0.3-0.5：低权威来源或大量推测 → 待验证
- <0.3：与高置信发现矛盾 → 不可采信

不说"判断可信度"（LLM 不知道怎么做），而是说"检查是否有两个以上独立来源、判断来源类型"（LLM 能在文本中找到答案）。

### Q: 怎么检测和裁决矛盾信息？

三条按优先级执行的规则，类比决策树：
1. 同指标不同数字 → 比较时效性，数据更新的优先
2. 同话题相反结论 → 比较权威性，官方 > 媒体 > 公司 > 个人
3. 无法判断 → 标记"未解决"，这本身就是结论（"行业尚无共识"）

不是一个 Prompt 笼统地说"请处理矛盾"，而是给 LLM 一套可执行的规则。

### Q: 撰写 Agent 的 inference_type（direct_quote / generalization / speculation）是干嘛的？

标准化"这个结论有多可靠"：
- direct_quote：置信度≥0.9 且证据≥2 → "直接采信，当事实陈述"
- generalization：置信度≥0.7 → "综合推断，陈述并注明来源"
- speculation：置信度<0.7 → "仅为推测，使用谨慎表述（如'有观点认为'）"

这约束了 LLM 的措辞——不是说"AI 市场规模 100 亿"而是"据 TechCrunch 报道，AI 市场规模约 100 亿"，区分事实和推测。

---

## 工程实践类问题

### Q: 项目里怎么处理 LLM 调用失败？

`call_llm_with_retry()` 统一入口，三个特点：
1. **模型集中管理**：不同节点可以用不同模型，配置在 Config.LLM_CONFIG 集中管理，换模型只改一行
2. **温度递增重试**：最多 3 次，温度 0→0.3→0.6，单次偶然波动不造成管线报废
3. **职责分离**：`parse_llm_json()` 负责内容校验（纯函数），`call_llm_with_retry()` 负责重试策略，独立可测

### Q: 后台任务耗时 2 分钟，HTTP 请求怎么处理？

**提交-轮询模式**：POST 秒回 202 + report_id（异步创建任务到线程池）→ 客户端每 3 秒 GET 查状态 → 完成后 GET content 拿报告。

线程安全方面：单 worker（一次只跑一个 workflow）+ 每次调用 `build_workflow()` 编译新图。跟 Java 的 FutureTask + ThreadPoolExecutor 同一个模式。

### Q: 日志怎么设计的？

控制台 INFO 级别（用户关心）+ 文件 DEBUG 级别（排查问题）+ 按天轮转保留 7 天。`TimedRotatingFileHandler(when="midnight", backupCount=7)`，每天午夜自动切新文件。

### Q: 怎么保证代码质量？

1. **关注点分离**：每个 Agent 一个独立文件，prompt + 函数放一起，改一个不用翻其他文件
2. **公共逻辑抽取**：JSON 解析先散落在 3 个文件，拆开后一眼看出重复 → 抽 `parse_llm_json()` 统一入口
3. **接口层透明包装**：FastAPI/Gradio 是纯新增目录，业务代码（agents/graph/models）一行没改
4. **可观测性**：LangSmith 自动追踪每次 invoke 的完整链路，不用手写 print

---

## 踩坑故事（面试加分项）

### 故事 1："改了 state 但实际没生效"

**问题**：`draft_node` 里 `state["iteration_count"] += 1`，但下一轮值还是旧的。

**原因**：LangGraph node 函数通过 **return dict** 更新 state，原地修改不生效。

**教训**：不熟悉框架的数据流模型时，看起来像"普通 dict"的东西可能有隐式的不可变性约束。后来养成了"先读文档的 state merge 机制再改代码"的习惯。

### 故事 2："LLM 突然开始输出空字符串"

**问题**：分析节点 LLM 返回 `content=""`，但 `finish_reason="stop"`（不是 length 截断）。

**原因**：DeepSeek 在长 prompt + 严格 JSON 约束下偶尔"摆烂"，换模型可彻底解决。

**临时方案**：加重试 + 空内容检测 + 温度递增。**根本方案**：评估切换到支持 Structured Output 的模型。

**教训**：finish_reason=stop 不代表一定有内容。每次 LLM 调用后都应检验 content.strip()。

### 故事 3："审核节点一直说证据不存在"

**问题**：审核反复报 `evidence_ref` 指向不存在的来源。

**排查**：LangSmith 追踪发现实际是分析节点的置信度锚点跑偏了——所有 Finding 的置信度都偏高，导致 inference_type 全标为 direct_quote，审核一看"你说这是直接引用但我找不到原文"。

**教训**：幻觉会跨 Agent 传播——前面的小偏差在后面被放大。多节点系统的调试必须看完整链路，不能只看最终输出。

---

## 对比 Java 后端（转行加分项）

如果你的面试官来自传统后端背景：

| 概念 | Java/Spring | Python/AI Agent 项目 |
|------|------------|-------------------|
| Bean 管理 | `@Autowired` / `@Component` | FastAPI `Depends()` + 模块级单例 |
| 线程池 | `ThreadPoolExecutor` + `FutureTask` | `ThreadPoolExecutor` + `run_in_executor` |
| 请求映射 | `@PostMapping("/api/reports")` | `@router.post("")` |
| 数据校验 | `@Valid` + `@NotNull` | Pydantic `BaseModel` + `Field(...)` |
| HTTP 客户端 | `RestTemplate` / `WebClient` | `httpx.AsyncClient` |
| 日志轮转 | Logback `TimeBasedRollingPolicy` | `TimedRotatingFileHandler` |
| 状态机 | Spring State Machine | LangGraph `StateGraph` |
| API 文档 | Swagger/OpenAPI | FastAPI 自动生成 `/docs` |
