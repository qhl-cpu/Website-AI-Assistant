from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    ChatRequest,
    ChatResponse,
    SearchRequest,
    SearchResponse,
)
from app.services.rag_service import answer_question, debug_search, load_chunks


app = FastAPI(
    title="Vancouver Laser RAG Assistant API",
    version="0.1.0",
)


allowed_origins = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "https://www.vancouverlaser.com",
    "https://vancouverlaser.com",
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/stats")
def stats():
    """
    Check how many embedded chunks are loaded.
    """
    chunks = load_chunks()

    return {
        "embedded_chunks_loaded": len(chunks)
    }


@app.post("/search", response_model=SearchResponse)
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

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


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

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        )
    
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)
