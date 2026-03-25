# AGENTS.md — API Module

FastAPI 后端：RESTful endpoints, SSE 流式响应, 服务层模式。

## Structure

```
api/
├── main.py              # FastAPI 应用工厂，生命周期管理
├── config.py            # API 配置（host, port, upload dir）
├── schemas.py           # Pydantic v2 请求/响应模型
├── models.py            # SQLAlchemy 数据库模型
├── database.py          # 数据库连接管理
├── routes/
│   ├── papers.py        # 论文上传/删除/列表
│   ├── query.py         # 查询端点（SSE 流式）
│   └── conversations.py # 对话历史管理
└── services/
    ├── paper_service.py   # 论文业务逻辑
    ├── query_service.py   # 查询业务逻辑
    └── conversation_service.py
```

## Key Patterns

### Route Handler Pattern
- Routes 保持 thin，业务逻辑在 services/
- 使用 Pydantic v2 models 进行验证
- 客户端错误用 `HTTPException(status_code=400, detail="...")`
- 对外错误响应只返回安全、简短信息；不要泄露内部异常细节

### SSE Streaming
```python
from fastapi.responses import StreamingResponse

@router.post("/stream")
async def stream_query(request: QueryRequest):
    return StreamingResponse(
        generate_events(request.question),
        media_type="text/event-stream"
    )
```

### Service Layer
```python
class PaperService:
    def _get_vector_store(self):  # 延迟导入
        from src.rag.vector_store import get_vector_store
        return get_vector_store()
```

## Critical Constraints

1. **Lazy Imports**: 在 service 方法内部导入 `get_vector_store()`，不要在模块级别
2. **Temp Files**: PDF 上传到临时目录，处理后清理
3. **CORS**: 配置为 `localhost:5173`（前端开发服务器）
4. **Errors**: API routes 只返回 sanitized messages，不要透出 traceback / exception repr

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/papers/upload` | 上传 PDF |
| GET | `/api/papers` | 列出论文 |
| DELETE | `/api/papers/{name}` | 删除论文 |
| POST | `/api/query/stream` | SSE 流式查询 |
| GET | `/api/conversations` | 获取对话 |
| DELETE | `/api/conversations/{id}` | 删除对话 |
