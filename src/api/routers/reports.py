"""报告相关 API 端点"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from src.api.models import ReportRequest, ReportResponse, ReportStatusResponse, ReportListResponse
from src.api.store import ReportStore, ReportRecord
from src.api.dependencies import get_report_store
from src.api.tasks import run_report_generation

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _to_status_response(r: ReportRecord) -> ReportStatusResponse:
    return ReportStatusResponse(
        report_id=r.report_id,
        topic=r.topic,
        status=r.status,
        created_at=r.created_at,
        completed_at=r.completed_at,
        final_report_path=r.final_report_path,
        iteration_count=r.iteration_count,
        audit_verdict=r.audit_verdict,
        error=r.error,
    )


@router.post("", response_model=ReportResponse, status_code=202)
async def create_report(
    request: ReportRequest,
    store: ReportStore = Depends(get_report_store),
):
    """提交报告生成任务（后台执行，立即返回）"""
    report_id = store.create(request.topic)

    # 用 asyncio.create_task 保证不随请求结束而取消
    asyncio.create_task(
        run_report_generation(report_id, request.topic, store)
    )

    return ReportResponse(
        report_id=report_id,
        topic=request.topic,
        status="pending",
        message="报告生成任务已提交，请轮询 GET /api/v1/reports/{report_id} 获取结果",
    )


@router.get("/{report_id}", response_model=ReportStatusResponse)
async def get_report_status(
    report_id: str,
    store: ReportStore = Depends(get_report_store),
):
    """查询报告生成状态"""
    record = store.get(report_id)
    if not record:
        raise HTTPException(status_code=404, detail="报告不存在")
    return _to_status_response(record)


@router.get("/{report_id}/content")
async def get_report_content(
    report_id: str,
    store: ReportStore = Depends(get_report_store),
):
    """获取报告 Markdown 原文"""
    record = store.get(report_id)
    if not record:
        raise HTTPException(status_code=404, detail="报告不存在")
    if record.status != "completed":
        raise HTTPException(status_code=400, detail="报告尚未生成完成")
    return FileResponse(
        record.final_report_path,
        media_type="text/markdown; charset=utf-8",
        filename=f"{record.topic}.md",
    )


@router.get("", response_model=ReportListResponse)
async def list_reports(
    limit: int = Query(default=20, le=100),
    store: ReportStore = Depends(get_report_store),
):
    """最近生成的报告列表"""
    records = store.list_recent(limit)
    return ReportListResponse(
        reports=[_to_status_response(r) for r in records],
        total=len(records),
    )
