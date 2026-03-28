# pyright: reportMissingImports=false

import os
import warnings

os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
warnings.filterwarnings("ignore", message="Class .* is implemented in both")

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from api import config  # noqa: E402
from api.database import close_db, init_db  # noqa: E402
from api.routes import conversations, papers, query  # noqa: E402
from api.schemas import HealthResponse  # noqa: E402
from src.utils.metrics import attach_metrics_endpoint  # noqa: E402
from src.utils.exceptions import AppError, normalize_http_error  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 应用生命周期管理。

    启动时初始化数据库，关闭时清理连接。
    """
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="ScholarRAG API",
    description="API for ScholarRAG - Multimodal RAG for Academic Papers",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers.router, prefix="/api/papers", tags=["papers"])
app.include_router(query.router, prefix="/api/query", tags=["query"])
app.include_router(
    conversations.router, prefix="/api/conversations", tags=["conversations"]
)
attach_metrics_endpoint(app)


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
    payload = normalize_http_error(exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT)
