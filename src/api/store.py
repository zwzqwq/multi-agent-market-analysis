"""线程安全的内存报告状态存储

这个模块是"餐厅的号码牌系统"——每个报告生成任务拿到一个号，按号查状态。

数据结构:
  ReportRecord  = 一张号码牌（任务ID + 状态 + 结果）
  ReportStore   = 号码牌盒子（所有牌的 dict + 读写锁）

为什么用 dataclass 而不是 Pydantic:
  dataclass 不校验 —— ReportRecord 是内部创建、内部使用的，
  不接收外部输入，不存在信任问题。Pydantic 用于"信不过的外部数据"。

为什么需要 threading.Lock:
  FastAPI 内部异步处理请求，多个请求可能同时读写 self._reports。
  不加锁 → 并发修改 dict → 数据损坏。
  Lock = 互斥开关 = "我正在改，你等一下"。
  每次操作耗时微秒级，锁几乎不造成等待。
  Java 等价物: ReentrantLock（Python 版不可重入，但你的场景不嵌套，够用）。
"""

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class ReportRecord:
    """单条报告任务记录 —— 一张号码牌

    状态流转: pending → running → completed / failed
    """
    report_id: str
    topic: str
    status: str          # "pending" | "running" | "completed" | "failed"
    created_at: str
    completed_at: str | None = None
    final_report_path: str | None = None
    iteration_count: int | None = None
    audit_verdict: str | None = None
    error: str | None = None


class ReportStore:
    """线程安全的任务状态存储器

    本质就是一个用 Lock 保护的 dict，增/查/改三个操作。
    服务启动时创建一次（单例），整个进程共享。
    """

    def __init__(self):
        self._lock = threading.Lock()            # 互斥锁
        self._reports: dict[str, ReportRecord] = {}

    def create(self, topic: str) -> str:
        """新建任务记录，返回 12 位随机 ID"""
        report_id = uuid4().hex[:12]
        record = ReportRecord(
            report_id=report_id,
            topic=topic,
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:                         # 加锁保护写操作
            self._reports[report_id] = record
        return report_id

    def update_running(self, report_id: str) -> None:
        """状态改为 running（后台任务开始执行）"""
        with self._lock:
            if report_id in self._reports:
                self._reports[report_id].status = "running"

    def update_completed(
        self, report_id: str, path: str,
        iteration_count: int, audit_verdict: str | None,
    ) -> None:
        """状态改为 completed（workflow 跑完，报告已保存）"""
        with self._lock:
            if report_id in self._reports:
                r = self._reports[report_id]
                r.status = "completed"
                r.completed_at = datetime.now(timezone.utc).isoformat()
                r.final_report_path = path
                r.iteration_count = iteration_count
                r.audit_verdict = audit_verdict

    def update_failed(self, report_id: str, error: str) -> None:
        """状态改为 failed（workflow 抛异常了）"""
        with self._lock:
            if report_id in self._reports:
                r = self._reports[report_id]
                r.status = "failed"
                r.completed_at = datetime.now(timezone.utc).isoformat()
                r.error = error

    def get(self, report_id: str) -> ReportRecord | None:
        """查一张牌的状态，不存在返回 None"""
        with self._lock:
            return self._reports.get(report_id)

    def list_recent(self, limit: int = 20) -> list[ReportRecord]:
        """最近 N 条历史记录，按创建时间倒序"""
        with self._lock:
            records = list(self._reports.values())
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]
