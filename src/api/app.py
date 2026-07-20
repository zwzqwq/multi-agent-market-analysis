"""FastAPI 应用工厂"""

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
    init_report_store()
    logger.info("FastAPI 启动完成，报告存储已初始化")
    yield
    logger.info("FastAPI 正在关闭...")


def create_app() -> FastAPI:
    app = FastAPI(
        title="多Agent市场分析报告生成系统",
        description="基于 LangGraph 的多 Agent 协作市场分析报告生成 API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(reports.router)

    # 静态文件：生成的报告可直接通过 /outputs/ 访问
    outputs_dir = Path(config.OUTPUT_DIR)
    outputs_dir.mkdir(exist_ok=True)
    app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")

    return app
