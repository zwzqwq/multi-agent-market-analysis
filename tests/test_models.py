import pytest
from pydantic import ValidationError
from src.api.models import ReportRequest


@pytest.mark.parametrize(
    "topic",
    [
        "2026年AI芯片市场",
        "一个字符",
        "a" * 500,          # 刚好 500 字符（边界值）
    ]
)
def test_report_request_valid(topic):
    """合法输入：应该成功创建，不抛异常"""
    req = ReportRequest(topic=topic)
    assert req.topic == topic


@pytest.mark.parametrize(
    "topic",
    [
        "",                  # 空字符串
        "a" * 501,           # 超过 500 字符
    ]
)
def test_report_request_invalid(topic):
    """非法输入：应该抛 ValidationError"""
    with pytest.raises(ValidationError):
        ReportRequest(topic=topic)
