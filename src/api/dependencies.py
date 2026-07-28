"""FastAPI 依赖注入

本模块实现全局单例模式的依赖注入系统，确保整个应用共享同一个 ReportStore 实例。

在 FastAPI 中，依赖注入通过 Depends() 实现：

    @app.get("/reports/{report_id}")
    def get_report(report_id: str, store: ReportStore = Depends(get_report_store)):
        report = store.get(report_id)
        return report

工作流程：
1. 应用启动时 → 调用 init_report_store() 创建实例
2. 路由请求时 → FastAPI 通过 Depends 自动调用 get_report_store() 注入实例
"""

from .store import ReportStore

# 模块级全局变量：存储唯一的 ReportStore 实例
# 类型注解 `ReportStore | None` 表示初始值为 None，初始化后变为 ReportStore
# 生命周期：整个应用运行期间只创建一次
_report_store: ReportStore | None = None


def get_report_store() -> ReportStore:
    """获取已初始化的 ReportStore 实例

    作为 FastAPI 依赖注入的工厂函数使用。
    FastAPI 检测到 Depends(get_report_store) 时会自动调用此函数。

    Raises:
        AssertionError: 如果 ReportStore 未初始化就被调用
    """
    # assert 确保在使用前已初始化，防止空指针错误
    assert _report_store is not None, "ReportStore 未初始化"
    return _report_store


def init_report_store() -> ReportStore:
    """初始化全局 ReportStore 实例

    必须在应用启动时（lifespan 中）调用一次，才能使用 get_report_store()。

    Returns:
        初始化后的 ReportStore 实例
    """
    # global 关键字：声明 _report_store 是全局变量，而非函数内的局部变量
    # 如果不加 global，下面的赋值会创建一个新的局部变量
    global _report_store
    _report_store = ReportStore()
    return _report_store
