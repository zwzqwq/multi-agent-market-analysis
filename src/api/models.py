"""FastAPI 请求/响应数据模型

这里定义的所有类都继承 Pydantic 的 BaseModel —— 跟 contracts.py 用的是同一个基类。
FastAPI 看到函数参数是 BaseModel 子类时，会自动：
  1. 从 HTTP 请求体读取 JSON
  2. 调用 Pydantic 校验每个字段（类型、长度、是否为空）
  3. 校验不通过 → 自动返回 HTTP 422，你的函数根本不会被执行
  4. 校验通过 → 把干净的 Python 对象传给你的函数

所以你不需要写任何 if topic == "" 之类的校验代码。
"""

from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    """POST /api/v1/reports 的请求体

    用户提交报告生成任务时，HTTP Body 就是这个结构:
      {"topic": "2026年AI芯片市场"}
    """
    topic: str = Field(
        ...,                          # ... 表示必填，不能省略
        min_length=1,                 # 不能是空字符串
        max_length=500,               # 防止恶意超长输入
        description="分析主题",
        examples=["2026年AI编程助手市场竞争格局"],
    )


class ReportResponse(BaseModel):
    """POST /api/v1/reports 的响应体 —— 任务提交成功后秒回

    此时任务还没跑完，只是"已受理"。客户端拿着 report_id 去轮询状态。
    """
    report_id: str                    # 任务编号，如 "f847ddb41b6f"
    topic: str                         # 回显用户输入的主题
    status: str                        # 永远是 "pending"
    message: str                       # 给用户的提示信息


class ReportStatusResponse(BaseModel):
    """GET /api/v1/reports/{id} 的响应体 —— 查询任务状态

    同一个接口，不同时刻返回的 status 不同:
      pending   → 排队中，还没开始
      running   → 正在跑 workflow
      completed → 跑完了，final_report_path 有值
      failed    → 跑炸了，error 有值
    """
    report_id: str
    topic: str
    status: str                       # pending | running | completed | failed
    created_at: str
    completed_at: str | None = None   # 没完成时是 null
    final_report_path: str | None = None
    iteration_count: int | None = None
    audit_verdict: str | None = None
    error: str | None = None


class ReportListResponse(BaseModel):
    """GET /api/v1/reports 的响应体 —— 历史报告列表"""
    reports: list[ReportStatusResponse]
    total: int
