"""线程安全的内存报告状态存储"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class ReportRecord:
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
    """线程安全的内存报告存储"""

    def __init__(self):
        self._lock = threading.Lock()
        self._reports: dict[str, ReportRecord] = {}

    def create(self, topic: str) -> str:
        report_id = uuid4().hex[:12]
        record = ReportRecord(
            report_id=report_id,
            topic=topic,
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._reports[report_id] = record
        return report_id

    def update_running(self, report_id: str) -> None:
        with self._lock:
            if report_id in self._reports:
                self._reports[report_id].status = "running"

    def update_completed(
        self,
        report_id: str,
        path: str,
        iteration_count: int,
        audit_verdict: str | None,
    ) -> None:
        with self._lock:
            if report_id in self._reports:
                r = self._reports[report_id]
                r.status = "completed"
                r.completed_at = datetime.now(timezone.utc).isoformat()
                r.final_report_path = path
                r.iteration_count = iteration_count
                r.audit_verdict = audit_verdict

    def update_failed(self, report_id: str, error: str) -> None:
        with self._lock:
            if report_id in self._reports:
                r = self._reports[report_id]
                r.status = "failed"
                r.completed_at = datetime.now(timezone.utc).isoformat()
                r.error = error

    def get(self, report_id: str) -> ReportRecord | None:
        with self._lock:
            return self._reports.get(report_id)

    def list_recent(self, limit: int = 20) -> list[ReportRecord]:
        with self._lock:
            records = list(self._reports.values())
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]
