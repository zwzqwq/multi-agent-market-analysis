# Multi-Agent Market Analysis Report System

基于 **LangGraph** 的多 Agent 协作市场分析报告生成系统。用户输入一个分析主题，四个 Agent（搜索、分析、撰写、审核）自动搜索互联网信息、提取关键发现、撰写结构化报告、审核质量，最终输出 Markdown 报告。

**核心设计**：审核回退闭环 —— 审核节点发现质量问题后，小问题（措辞偏差）回撰写节点局部修改，大问题（推理链断裂）回分析节点重新推理。最多迭代 3 轮，超限强制输出并加上质量声明。一份不完美的报告比没有报告好。

**技术栈**：`Python 3.11+` `LangGraph` `LangChain` `DeepSeek` `Tavily` `FastAPI` `Gradio` `Pydantic` `pytest`

---

## 架构

```
用户输入主题
  → Search Agent (Tavily 搜索)
    → Analysis Agent (LLM 提取关键发现 + 置信度评级 + 裁决矛盾)
      → Draft Agent (LLM 撰写结构化报告，断言溯源)
        → Audit Agent (5 项检查：引用完整性/来源存在性/主题相关性/逻辑推导/inference_type)
          → pass → 生成报告 ✅
          → minor_issues → 回 Draft 局部修改
          → major_issues → 回 Analysis 重新推理
```

**四个 Agent 通过 Pydantic 类型契约传递数据**：
`SearchResult` → `AnalysisReport` → `DraftReport` → `AuditResult`

---

## 快速开始

### 1. 安装依赖

```bash
pip install -e .
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```env
OPENAI_API_KEY=your_deepseek_api_key
OPENAI_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-chat
TAVILY_API_KEY=your_tavily_api_key
```

### 3. 启动

**命令行模式**（一次性生成报告）：

```bash
python -m src.main cli "2026年AI芯片市场竞争格局"
```

**Web 模式**（需两个终端）：

```bash
# 终端 1 — FastAPI 后端
python -m src.main api

# 终端 2 — Gradio 前端
python -m src.main ui
```

浏览器访问 `http://127.0.0.1:7860`，输入主题，等待约 2 分钟即可看到报告。

API 文档：`http://127.0.0.1:8000/docs`

### 4. 运行测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

---

## 项目结构

```
├── src
│   ├── agents/                 # LangGraph 工作流节点
│   │   ├── state.py            # AgentState 类型定义 + MAX_ITERATIONS
│   │   ├── search.py           # 搜索节点（Tavily API）
│   │   ├── analysis.py         # 分析节点（LLM — 关键发现 + 置信度 + 矛盾裁决）
│   │   ├── draft.py            # 撰写节点（LLM — 结构化报告，断言溯源）
│   │   ├── audit.py            # 审核节点（LLM — 5 项质量检查 + 路由裁决）
│   │   └── generate.py         # 报告生成节点（文件保存 + 质量声明兜底）
│   ├── graph/
│   │   └── workflow.py         # build_workflow() — 组装状态图、注册路由
│   ├── models/
│   │   └── contracts.py        # Pydantic 数据契约（SearchResult/AnalysisReport/…）
│   ├── tools/
│   │   └── search_api.py       # Tavily 搜索工具封装
│   ├── api/                    # FastAPI 后端
│   │   ├── app.py              # 应用工厂 + lifespan + CORS
│   │   ├── dependencies.py     # 依赖注入（ReportStore 单例）
│   │   ├── models.py           # 请求/响应 Pydantic 模型
│   │   ├── store.py            # 线程安全内存存储（Lock 保护）
│   │   ├── tasks.py            # 后台任务执行器（ThreadPoolExecutor）
│   │   └── routers/
│   │       └── reports.py      # POST/GET 报告端点
│   ├── ui/
│   │   └── app.py              # Gradio Web UI（httpx → FastAPI）
│   ├── utils/
│   │   ├── config.py           # 环境变量 + 模型配置管理
│   │   ├── json_parser.py      # LLM JSON 解析（三层防御）
│   │   ├── llm_retry.py        # LLM 调用 + 温度递增重试 + 指数退避
│   │   ├── logger.py           # 日志（按天轮转，保留 7 天）
│   │   └── report_saver.py     # 报告保存到 outputs/
│   └── main.py                 # 统一入口（cli / api / ui 三种模式）
├── tests/                      # 35 个测试用例
│   ├── conftest.py             # 共享工具函数
│   ├── test_json_parser.py     # JSON 解析器（17 用例）
│   ├── test_store.py           # ReportStore（5 用例，含 fixture）
│   ├── test_models.py          # Pydantic 数据模型（5 用例，含 parametrize）
│   ├── test_llm_retry.py       # LLM 重试逻辑（6 用例，含 Mock）
│   └── test_workflow.py        # 工作流集成测试（2 用例，Happy Path + 回退路径）
├── notes/                      # 学习笔记
│   ├── mock_patch_usage.md     # Mock/Patch 使用笔记
│   └── pytest_fixture.md       # pytest fixture 使用笔记
├── outputs/                    # 报告输出目录（自动创建）
├── pyproject.toml
└── README.md
```

| 目录 | 职责 | 关键决策 |
|------|------|---------|
| `agents/` | 工作流节点 | 每个 Agent 一个文件，prompt + 函数放一起 |
| `graph/` | 工作流编排 | `build_workflow()` 每次新建图，保证线程安全 |
| `models/` | Pydantic 契约 | Agent 间不传 dict，编译期检查格式 |
| `api/` | HTTP 接口 | 提交-轮询模式，后台 ThreadPoolExecutor 异步执行 |
| `ui/` | Web 界面 | httpx 调 FastAPI，不和 workflow 直接耦合 |
| `utils/` | 基础设施 | JSON 防御性解析 / LLM 重试 / 日志轮转 |

---

## 工程亮点

- **LLM 输出防御**：不信任 Prompt 约束格式，代码清洗 markdown 包裹 + 字段级 `.get()` 防御 + 温度递增重试（0→0.3→0.6）+ 指数退避（429 限流）
- **置信度设计**：不要求 LLM 区分 0.83 vs 0.84，用客观 checklist 分类（官方数据 + 2+ 来源 → 0.9-1.0），inference_type 约束措辞风格
- **线程安全**：`build_workflow()` 每次编译新图 + `max_workers=3`，支持并发请求
- **审核反馈回流**：审核发现问题注入分析节点上下文，同样数据 + 不同上下文 = 不同分析结果