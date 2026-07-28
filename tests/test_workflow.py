"""
build_workflow() 集成测试

Mock 搜索 API + 全部 LLM 调用，验证 LangGraph 状态图从头跑到尾。

Mock 全景图：
  search_node      -> Mock tavily_search_tool.search
  analysis_node    -> Mock call_llm_with_retry（analysis 模块内的引用）
  draft_node       -> Mock call_llm_with_retry（draft 模块内的引用）
  audit_node       -> Mock call_llm_with_retry（audit 模块内的引用）

四个 patch 各有各的模块路径，因为每个 Agent 文件里各自 import 了
call_llm_with_retry，需要分别替换。
"""

import pytest
from unittest.mock import patch

from src.graph.workflow import build_workflow
from src.models.contracts import Source


# ============================================================
# 假数据工厂 — 模拟各节点的 LLM 返回
# ============================================================

def fake_analysis_response():
    """模拟分析节点返回的 JSON"""
    return {
        "findings": [
            {
                "claim": "2026年AI编程助手市场规模约120亿美元",
                "evidence": ["source_1", "source_2"],
                "confidence": 0.9,
                "counter_evidence": [],
            },
            {
                "claim": "GitHub Copilot 仍占据最大市场份额",
                "evidence": ["source_1"],
                "confidence": 0.85,
                "counter_evidence": [],
            },
        ],
        "contradictions": [],
        "gaps": ["缺少中国市场份额数据"],
    }


def fake_draft_response():
    """模拟撰写节点返回的 JSON"""
    return {
        "sections": [
            {
                "title": "1. 引言",
                "content": "本报告分析了2026年AI编程助手市场格局。",
                "claims": [],
            },
            {
                "title": "2. 核心发现",
                "content": "AI编程助手市场规模约120亿美元，Copilot占据最大份额。",
                "claims": [
                    {
                        "text": "AI编程助手市场规模约120亿美元",
                        "evidence_ref": "source_1",
                        "inference_type": "direct_quote",
                    },
                    {
                        "text": "Copilot占据最大市场份额",
                        "evidence_ref": "source_1",
                        "inference_type": "generalization",
                    },
                ],
            },
            {
                "title": "3. 结论与建议",
                "content": "市场增长迅速，建议关注中国厂商。",
                "claims": [],
            },
        ]
    }


def fake_audit_pass_response():
    """模拟审核节点返回的 JSON — pass"""
    return {
        "overall_verdict": "pass",
        "issues": [],
        "alignment_score": 1.0,
    }


def fake_search_sources():
    """模拟 Tavily 搜索返回的 Source 列表"""
    return [
        Source(
            title="2026年AI编程助手市场报告",
            url="https://example.com/ai-market-2026",
            snippet="AI编程助手市场在2026年达到120亿美元规模",
        ),
        Source(
            title="GitHub Copilot 市场份额分析",
            url="https://example.com/copilot-share",
            snippet="GitHub Copilot 在企业市场占据约60%份额",
        ),
    ]


# ============================================================
# 测试 1：Happy Path — 一轮过
# ============================================================

@patch("src.agents.audit.call_llm_with_retry")
@patch("src.agents.draft.call_llm_with_retry")
@patch("src.agents.analysis.call_llm_with_retry")
@patch("src.agents.search.tavily_search_tool")
def test_workflow_happy_path(
    mock_search_tool,
    mock_analysis_llm,
    mock_draft_llm,
    mock_audit_llm,
):
    """完整流程：搜索 -> 分析 -> 撰写 -> 审核(pass) -> 生成报告"""
    # ===== Arrange =====
    mock_search_tool.search.return_value = fake_search_sources()
    mock_analysis_llm.return_value = fake_analysis_response()
    mock_draft_llm.return_value = fake_draft_response()
    mock_audit_llm.return_value = fake_audit_pass_response()

    # ===== Act =====
    app = build_workflow()
    result = app.invoke({
        "topic": "2026年AI编程助手市场",
        "search_result": None,
        "analysis": None,
        "draft": None,
        "audit": None,
        "iteration_count": 0,
        "final_report_path": None,
    })

    # ===== Assert: 状态流转 =====
    assert result["search_result"] is not None
    assert len(result["search_result"].sources) == 2
    assert result["analysis"] is not None
    assert len(result["analysis"].key_findings) == 2
    assert result["draft"] is not None
    assert len(result["draft"].sections) == 3
    assert result["audit"] is not None
    assert result["audit"].overall_verdict == "pass"
    assert result["iteration_count"] == 0   # 一轮过
    assert result["final_report_path"] is not None
    assert result["final_report_path"].endswith(".md")

    # 每个节点都只被调了一次
    mock_search_tool.search.assert_called_once()
    mock_analysis_llm.assert_called_once()
    mock_draft_llm.assert_called_once()
    mock_audit_llm.assert_called_once()


# ============================================================
# 测试 2：回退路径 — major_issues -> 回分析 -> pass
# ============================================================

@patch("src.agents.audit.call_llm_with_retry")
@patch("src.agents.draft.call_llm_with_retry")
@patch("src.agents.analysis.call_llm_with_retry")
@patch("src.agents.search.tavily_search_tool")
def test_workflow_major_issues_then_pass(
    mock_search_tool,
    mock_analysis_llm,
    mock_draft_llm,
    mock_audit_llm,
):
    """审核 major_issues -> 回分析节点 -> 重分析 -> 重撰写 -> 审核 pass"""
    mock_search_tool.search.return_value = fake_search_sources()

    # 分析节点被调两次：第一轮 + 回退后重新分析
    mock_analysis_llm.side_effect = [
        fake_analysis_response(),
        fake_analysis_response(),
    ]

    # 撰写节点两次：第一轮撰写 + 重分析后重新撰写
    mock_draft_llm.side_effect = [
        fake_draft_response(),
        fake_draft_response(),
    ]

    # 审核节点两次：第一次 major_issues -> 回退后 pass
    mock_audit_llm.side_effect = [
        {
            "overall_verdict": "major_issues",
            "issues": [
                {
                    "severity": "critical",
                    "location": "Section 2, Claim 1",
                    "description": "证据不足，推理链断裂",
                    "suggestion": "请重新分析并降置信度",
                }
            ],
            "alignment_score": 0.4,
        },
        fake_audit_pass_response(),
    ]

    # ===== Act =====
    app = build_workflow()
    result = app.invoke({
        "topic": "2026年AI编程助手市场",
        "search_result": None,
        "analysis": None,
        "draft": None,
        "audit": None,
        "iteration_count": 0,
        "final_report_path": None,
    })

    # ===== Assert =====
    assert result["audit"].overall_verdict == "pass"
    assert result["iteration_count"] == 1   # 回退一次
    assert result["final_report_path"] is not None

    # 调用次数验证
    assert mock_search_tool.search.call_count == 1   # 搜索只做一次
    assert mock_analysis_llm.call_count == 2          # 分析两次
    assert mock_draft_llm.call_count == 2             # 撰写两次
    assert mock_audit_llm.call_count == 2             # 审核两次
