"""FastAPI 应用工厂

本模块使用工厂模式创建 FastAPI 应用实例，统一管理：
- 应用生命周期（启动/关闭时的初始化与清理）
- 中间件配置（CORS 跨域支持）
- 路由注册（API 端点）
- 静态文件服务（生成的报告文件）

使用方式：
    # 在 main.py 中
    from src.api.app import create_app
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8000)
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.dependencies import init_report_store
from src.api.routers import reports
from src.utils.config import config
from src.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器

    @asynccontextmanager 是 Python 的异步上下文管理器装饰器。
    执行顺序：
        1. yield 之前：应用启动时执行一次（初始化）
        2. yield 暂停：应用运行期间，等待请求处理
        3. yield 之后：应用关闭时执行一次（清理资源）

    这是管理数据库连接、缓存、全局状态等资源的标准方式。
    """
    # 启动阶段：初始化全局依赖（如 ReportStore 单例）
    init_report_store()
    logger.info("FastAPI 启动完成，报告存储已初始化")

    # yield 是分界点：应用运行期间在此处暂停
    # FastAPI 会在此期间持续监听 HTTP 请求
    yield

    # 关闭阶段：释放资源、记录日志
    logger.info("FastAPI 正在关闭...")


def create_app() -> FastAPI:
    """应用工厂函数：创建并配置 FastAPI 实例

    工厂模式的好处：
    - 便于测试：可以创建多个实例进行独立测试
    - 便于配置：不同环境可以传入不同配置
    - 代码解耦：路由、中间件配置与应用创建分离

    Returns:
        配置完成的 FastAPI 应用实例
    """
    # 创建 FastAPI 实例并传入元数据和生命周期管理器
    app = FastAPI(
        title="多Agent市场分析报告生成系统",           # API 文档标题（显示在 /docs 页面）
        description="基于 LangGraph 的多 Agent 协作市场分析报告生成 API",  # API 文档描述
        version="0.1.0",                               # API 版本号
        lifespan=lifespan,                             # 绑定生命周期管理器（启动/关闭时执行）
    )

    # 添加 CORS 中间件（跨源资源共享）
    # 作用：允许浏览器从不同域名（如前端 localhost:3000）访问本 API
    # 没有此中间件，浏览器会阻止跨域请求（CORS 安全策略）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # 允许所有来源（生产环境应改为具体域名）
        allow_credentials=True,       # 允许携带 Cookie、Authorization 等凭证
        allow_methods=["*"],          # 允许所有 HTTP 方法（GET/POST/PUT/DELETE 等）
        allow_headers=["*"],         # 允许所有请求头
    )

    # 注册路由：将 reports 路由模块的所有端点挂载到应用
    # 路由模块定义了 /reports 相关的所有 API 端点
    app.include_router(reports.router)

    # 挂载静态文件服务：让生成的报告文件可以通过 HTTP 直接访问
    # 例如：报告保存到 outputs/ 目录后，可通过 http://host:port/outputs/文件名.md 下载
    outputs_dir = Path(config.OUTPUT_DIR)
    outputs_dir.mkdir(exist_ok=True)  # 确保目录存在，不存在则创建
    # mount() 将本地目录映射为 HTTP 静态文件路径
    # name 参数用于在 OpenAPI 文档中标识此静态资源
    app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")

    return app
