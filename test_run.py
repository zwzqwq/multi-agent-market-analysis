"""端到端测试：搜索 → 分析"""
from src.graph.workflow import build_workflow
from src.utils.config import config

# 启动前校验
missing = config.validate()
if missing:
    raise RuntimeError(f"缺少配置: {missing}")

# 构建工作流
app = build_workflow()

# 运行
print("=" * 60)
print("  测试工作流: search → analysis → write → audit")
print("=" * 60)

initial_state = {
    "topic": "2026年AI编程助手市场竞争格局",
    "search_result": None,
    "analysis": None,
    "draft": None,
    "audit": None,
    "iteration_count": 0,
    "final_report_path": None,
}

result = app.invoke(initial_state)

# 输出结果
print("\n[搜索结果]")
sr = result["search_result"]
print(f"  查询: {sr.query}")
print(f"  来源数: {len(sr.sources)}")
for i, s in enumerate(sr.sources):
    print(f"  [{i+1}] {s.title[:80] if s.title else 'N/A'}")

print("\n[分析结果]")
ar = result["analysis"]
print(f"  主题: {ar.topic}")
print(f"  关键发现: {len(ar.key_findings)} 条")
for i, f in enumerate(ar.key_findings):
    print(f"  [{i+1}] {f.claim[:80]}...")
    print(f"       置信度: {f.confidence}")
    print(f"       证据: {f.evidence}")
    if f.counter_evidence:
        print(f"       反证: {f.counter_evidence}")
print(f"  矛盾: {len(ar.contradictions)} 个")
for c in ar.contradictions:
    print(f"  - {c.claim_a[:50]}... vs {c.claim_b[:50]}...")
    print(f"    裁决: {c.resolution[:80]}...")
print(f"  信息缺口: {len(ar.gaps)} 个")
for g in ar.gaps:
    print(f"  - {g}")

print("\n[撰写结果]")
wr=result["draft"]
print(f"章节数: {len(wr.sections)}")
for i, s in enumerate(wr.sections):
    print(f"第[{i+1}]章： {s.title[:80]}")
    print(f"\n{s.content[:200]}...")
print(f"\n[OK] 撰写完成")

print("\n[校对结果]")
cr=result["audit"]
print(f"  整体裁决: {cr.overall_verdict}")
print(f"  对齐分数: {cr.alignment_score}")
print(f"  问题数: {len(cr.issues)}")
for i, iss in enumerate(cr.issues):
    print(f"  [{i+1}] {iss.severity.upper()} | {iss.location}")
    print(f"      描述: {iss.description}")
    print(f"      建议: {iss.suggestion}")


print("\n[OK] 端到端测试完成")
