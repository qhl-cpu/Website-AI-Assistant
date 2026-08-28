import logging
import math

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import (
    ALLOWED_ORIGINS,
    CHAT_IP_DAILY_REQUESTS,
    CHAT_IP_DAILY_WINDOW_SECONDS,
    CHAT_IP_SUSTAINED_REQUESTS,
    CHAT_IP_SUSTAINED_WINDOW_SECONDS,
    CHAT_RATE_LIMIT_ENABLED,
    CHAT_VISITOR_BURST_REQUESTS,
    CHAT_VISITOR_BURST_WINDOW_SECONDS,
    CHAT_VISITOR_DAILY_REQUESTS,
    CHAT_VISITOR_DAILY_WINDOW_SECONDS,
    CHAT_VISITOR_SUSTAINED_REQUESTS,
    CHAT_VISITOR_SUSTAINED_WINDOW_SECONDS,
    ENABLE_DIAGNOSTIC_ENDPOINTS,
    IS_PRODUCTION,
    TRUST_X_FORWARDED_FOR,
)
from app.schemas import (
    ChatRequest,
    ChatResponse,
    SearchRequest,
    SearchResponse,
)
from app.services.rag_service import answer_question, debug_search
from app.services.rate_limiter import (
    InMemorySlidingWindowRateLimiter,
    RateLimitRule,
)
from app.services.vector_store import get_collection_point_count


logger = logging.getLogger(__name__)


chat_rate_limiter = InMemorySlidingWindowRateLimiter(
    visitor_rules=(
        RateLimitRule(
            "burst",
            CHAT_VISITOR_BURST_REQUESTS,
            CHAT_VISITOR_BURST_WINDOW_SECONDS,
        ),
        RateLimitRule(
            "sustained",
            CHAT_VISITOR_SUSTAINED_REQUESTS,
            CHAT_VISITOR_SUSTAINED_WINDOW_SECONDS,
        ),
        RateLimitRule(
            "daily",
            CHAT_VISITOR_DAILY_REQUESTS,
            CHAT_VISITOR_DAILY_WINDOW_SECONDS,
        ),
    ),
    ip_rules=(
        RateLimitRule(
            "sustained",
            CHAT_IP_SUSTAINED_REQUESTS,
            CHAT_IP_SUSTAINED_WINDOW_SECONDS,
        ),
        RateLimitRule(
            "daily",
            CHAT_IP_DAILY_REQUESTS,
            CHAT_IP_DAILY_WINDOW_SECONDS,
        ),
    ),
    enabled=CHAT_RATE_LIMIT_ENABLED,
)


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


@app.post(
    "/chat",
    response_model=ChatResponse,
    responses={429: {"description": "Chat rate limit exceeded."}},
)
def chat(request: ChatRequest, http_request: Request):
    """
    Main endpoint used by the website chat widget.
    """
    client_ip = get_client_ip(http_request)
    visitor_id = f"{client_ip}:{request.session_id or 'anonymous'}"
    rate_limit = chat_rate_limiter.check(visitor_id, client_ip)

    if not rate_limit.allowed:
        retry_after = max(1, math.ceil(rate_limit.retry_after_seconds))
        is_daily_limit = bool(
            rate_limit.rule_name
            and rate_limit.rule_name.endswith("_daily")
        )
        detail = (
            "You've reached the daily chat limit. Please try again later "
            "or contact the clinic directly."
            if is_daily_limit
            else "You're sending messages a little quickly. Please wait "
            "before trying again."
        )

        return JSONResponse(
            status_code=429,
            content={
                "detail": detail,
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    try:
        history = [message.model_dump() for message in request.history]
        result = answer_question(request.message, history=history)

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


def get_client_ip(request: Request) -> str:
    if TRUST_X_FORWARDED_FOR:
        forwarded_for = request.headers.get("x-forwarded-for")

        if forwarded_for:
            # Use the address appended by the trusted ingress rather than a
            # potentially spoofed left-most value supplied by the client.
            candidate = forwarded_for.rsplit(",", maxsplit=1)[-1].strip()

            if candidate:
                return candidate

    if request.client and request.client.host:
        return request.client.host

    return "unknown"
