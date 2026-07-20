"""FastAPI 请求/响应数据模型"""
from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    """提交报告生成任务"""
    topic: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="分析主题",
        examples=["2026年AI编程助手市场竞争格局"],
    )


class ReportResponse(BaseModel):
    """任务提交成功后返回"""
    report_id: str
    topic: str
    status: str
    message: str


class ReportStatusResponse(BaseModel):
    """报告任务状态"""
    report_id: str
    topic: str
    status: str               # pending | running | completed | failed
    created_at: str
    completed_at: str | None = None
    final_report_path: str | None = None
    iteration_count: int | None = None
    audit_verdict: str | None = None
    error: str | None = None


class ReportListResponse(BaseModel):
    """报告列表"""
    reports: list[ReportStatusResponse]
    total: int
