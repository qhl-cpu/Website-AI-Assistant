from typing import List, Optional

from pydantic import BaseModel, Field


# Request body for the /chat endpoint.
# The frontend sends this when a user asks the assistant a question.
class ChatRequest(BaseModel):
    # User's message/question.
    # Required and cannot be an empty string.
    message: str = Field(..., min_length=1)

    # Optional ID for tracking one conversation session.
    # Useful later if we add chat history/memory.
    session_id: Optional[str] = None


# One source document/chunk used to support the generated answer.
class Source(BaseModel):
    # Unique source ID, usually the chunk_id from our processed data.
    source_id: str

    # Page title, such as "Botox" or "Sofwave".
    title: str

    # Original WordPress page URL.
    url: str

    # Optional section label, such as "overview", "procedure", or "faq".
    section_type: Optional[str] = None

    # Optional retrieval similarity score.
    score: Optional[float] = None


# Response body for the /chat endpoint.
# The backend returns this after generating an answer.
class ChatResponse(BaseModel):
    # Final answer shown to the user.
    answer: str

    # List of sources used to support the answer.
    sources: List[Source]


# Request body for the /search endpoint.
# Used to test vector search directly without generating an AI answer.
class SearchRequest(BaseModel):
    # Search query. Required and cannot be empty.
    query: str = Field(..., min_length=1)

    # Number of search results to return.
    # Defaults to 8.
    # Must be between 1 and 20.
    top_k: int = Field(default=8, ge=1, le=20)


# One result returned by vector search.
class SearchResult(BaseModel):
    # Similarity score from vector search.
    score: float

    # Unique chunk ID from the processed chunk file/vector database.
    chunk_id: str

    # Source page title.
    title: str

    # Source page URL.
    url: str

    # Optional section label for the chunk.
    section_type: Optional[str] = None

    # Short text preview for debugging/search display.
    text_preview: str


# Response body for the /search endpoint.
class SearchResponse(BaseModel):
    # List of retrieved search results.
    results: List[SearchResult]