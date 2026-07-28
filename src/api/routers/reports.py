"""报告相关 API 端点

本模块定义报告管理的 REST API 路由，相当于 Spring Boot 中的 Controller 层。

API 端点列表：
    POST   /api/v1/reports          创建报告生成任务（异步后台执行）
    GET    /api/v1/reports          查询报告列表
    GET    /api/v1/reports/{id}     查询单个报告状态
    GET    /api/v1/reports/{id}/content  下载报告文件

请求流程：
    1. POST 创建任务 → 立即返回 report_id
    2. 客户端轮询 GET 状态 → 等待生成完成
    3. GET /content 下载最终报告
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from src.api.models import ReportRequest, ReportResponse, ReportStatusResponse, ReportListResponse
from src.api.store import ReportStore, ReportRecord
from src.api.dependencies import get_report_store
from src.api.tasks import run_report_generation

# APIRouter: 路由分组器，相当于 Spring Boot 的 @RestController
# prefix: 统一路由前缀，实现 API 版本化（/api/v1/...）
# tags: Swagger UI 文档中的分组标签
router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _to_status_response(r: ReportRecord) -> ReportStatusResponse:
    """内部数据 → API 响应模型的转换函数

    类似于 Spring Boot 中的 DTO 转换器，将数据库实体转换为前端需要的响应格式。
    单独抽出来是为了复用（多个端点都需要这个转换）。
    """
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
    request: ReportRequest,                              # 请求体：Pydantic 模型自动校验
    store: ReportStore = Depends(get_report_store),     # 依赖注入：相当于 @Autowired
):
    """提交报告生成任务（后台执行，立即返回）

    工作流调用是耗时操作（可能几十秒），所以采用异步模式：
    1. 创建任务记录，状态设为 pending
    2. 用 asyncio.create_task 提交后台执行
    3. 立即返回 report_id，客户端轮询状态

    status_code=202: HTTP 202 Accepted，表示请求已受理但未完成
    """
    report_id = store.create(request.topic)

    # asyncio.create_task: 相当于 Spring 的 @Async，将任务提交到后台
    # 保证即使客户端断开，任务也会继续执行
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
    report_id: str,                                     # 路径参数：相当于 @PathVariable
    store: ReportStore = Depends(get_report_store),
):
    """查询报告生成状态

    客户端通过轮询此接口获取任务进度：
    - status="pending": 等待执行
    - status="running": 正在生成
    - status="completed": 完成
    - status="failed": 失败
    """
    record = store.get(report_id)
    if not record:
        # HTTPException: 相当于 Spring 的 @ResponseStatus + 自定义异常
        # FastAPI 自动捕获并返回 JSON: {"detail": "报告不存在"}
        raise HTTPException(status_code=404, detail="报告不存在")
    return _to_status_response(record)


@router.get("/{report_id}/content")
async def get_report_content(
    report_id: str,
    store: ReportStore = Depends(get_report_store),
):
    """获取报告 Markdown 原文

    FileResponse: 相当于 Spring 的 ResponseEntity<Resource>
    设置响应头 Content-Disposition，浏览器会触发文件下载
    """
    record = store.get(report_id)
    if not record:
        raise HTTPException(status_code=404, detail="报告不存在")
    if record.status != "completed":
        # 业务校验：只有完成的报告才能下载
        raise HTTPException(status_code=400, detail="报告尚未生成完成")
    return FileResponse(
        record.final_report_path,
        media_type="text/markdown; charset=utf-8",   # MIME 类型
        filename=f"{record.topic}.md",               # 下载时的文件名
    )


@router.get("", response_model=ReportListResponse)
async def list_reports(
    limit: int = Query(default=20, le=100),             # 查询参数：相当于 @RequestParam
    store: ReportStore = Depends(get_report_store),
):
    """最近生成的报告列表

    Query 参数说明：
    - default=20: 默认返回 20 条
    - le=100: 限制最大值 100 条，防止一次查询过多数据
    """
    records = store.list_recent(limit)
    return ReportListResponse(
        # 列表推导式：等价于 Java 的 stream().map().toList()
        reports=[_to_status_response(r) for r in records],
        total=len(records),
    )
