from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.schemas import QueryRequest, QueryResponse
from api.services import query_service

router = APIRouter()


@router.post("")
async def query(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        return StreamingResponse(
            query_service.stream_query(request.question),
            media_type="text/event-stream",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
