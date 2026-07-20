"""FastAPI 依赖注入"""
from .store import ReportStore

_report_store: ReportStore | None = None


def get_report_store() -> ReportStore:
    assert _report_store is not None, "ReportStore 未初始化"
    return _report_store


def init_report_store() -> ReportStore:
    global _report_store
    _report_store = ReportStore()
    return _report_store
