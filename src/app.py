"""FastAPI 服务入口：一个 /query 端点，自带 Swagger UI。"""
from __future__ import annotations

from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

load_dotenv()

from src.graph import run_agent  # noqa: E402  (需要先 load_dotenv 再导入用到环境变量的模块)

app = FastAPI(
    title="机票比价 Agent",
    description="自然语言机票查询：解析需求 -> 追问缺失信息 -> 调用 mock 工具搜索 -> 计算总价并分档",
    version="0.1.0",
)


class QueryRequest(BaseModel):
    message: str
    known_fields: Optional[dict[str, Any]] = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query")
def query(payload: QueryRequest) -> dict[str, Any]:
    return run_agent(payload.message, payload.known_fields)
