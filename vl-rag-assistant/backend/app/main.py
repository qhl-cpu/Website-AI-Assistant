import logging

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import (
    ALLOWED_ORIGINS,
    ENABLE_DIAGNOSTIC_ENDPOINTS,
    IS_PRODUCTION,
)
from app.schemas import (
    ChatRequest,
    ChatResponse,
    SearchRequest,
    SearchResponse,
)
from app.services.rag_service import answer_question, debug_search
from app.services.vector_store import get_collection_point_count


logger = logging.getLogger(__name__)


app = FastAPI(
    title="Vancouver Laser RAG Assistant API",
    version="0.1.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def require_diagnostic_endpoints() -> None:
    if not ENABLE_DIAGNOSTIC_ENDPOINTS:
        raise HTTPException(status_code=404, detail="Not found.")


@app.get("/")
def root():
    return {
        "message": "Vancouver Laser RAG Assistant API is running."
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }


@app.get("/ready")
def readiness_check():
    """
    Confirm that the API can reach its Qdrant collection.
    """
    try:
        get_collection_point_count()

    except Exception:
        logger.exception("Readiness check failed")

        raise HTTPException(
            status_code=503,
            detail="Service is not ready.",
        ) from None

    return {
        "status": "ready"
    }


@app.get(
    "/stats",
    dependencies=[Depends(require_diagnostic_endpoints)],
    include_in_schema=ENABLE_DIAGNOSTIC_ENDPOINTS,
)
def stats():
    """
    Check how many embedded chunks are stored in Qdrant.
    """
    return {
        "embedded_chunks_loaded": get_collection_point_count()
    }


@app.post(
    "/search",
    response_model=SearchResponse,
    dependencies=[Depends(require_diagnostic_endpoints)],
    include_in_schema=ENABLE_DIAGNOSTIC_ENDPOINTS,
)
def search(request: SearchRequest):
    """
    Debug endpoint for retrieval only.
    This does not call the chat model.
    """
    try:
        results = debug_search(
            query=request.query,
            top_k=request.top_k,
        )

        return {
            "results": results
        }

    except Exception:
        logger.exception("Search request failed")

        raise HTTPException(
            status_code=500,
            detail="Search is temporarily unavailable.",
        ) from None


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Main endpoint used by the website chat widget.
    """
    try:
        result = answer_question(request.message)

        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
        )

    except Exception:
        logger.exception("Chat request failed")

        raise HTTPException(
            status_code=500,
            detail="The assistant is temporarily unavailable.",
        ) from None
    
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)
