from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


MAX_CHAT_HISTORY_MESSAGES = 60
MAX_CHAT_HISTORY_CHARS = 60000


class ChatMessage(BaseModel):
    # Only user and assistant turns belong in client-provided conversation history.
    role: Literal["user", "assistant"]

    # Keep individual turns bounded so a public request cannot create an
    # unexpectedly large model prompt.
    content: str = Field(..., min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Message content cannot be blank.")

        return value


# Request body for the /chat endpoint.
# The frontend sends this when a user asks the assistant a question.
class ChatRequest(BaseModel):
    # User's message/question.
    # Required and limited to keep public requests within a reasonable size.
    message: str = Field(..., min_length=1, max_length=2000)

    # Optional ID for tracking one conversation session.
    session_id: Optional[str] = Field(default=None, max_length=128)

    # Completed turns from this session, oldest first. The current user message
    # stays in `message` and must not be repeated here.
    history: List[ChatMessage] = Field(
        default_factory=list,
        max_length=MAX_CHAT_HISTORY_MESSAGES,
    )

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Message cannot be blank.")

        return value

    @model_validator(mode="after")
    def limit_total_history_size(self):
        total_chars = sum(len(message.content) for message in self.history)

        if total_chars > MAX_CHAT_HISTORY_CHARS:
            raise ValueError(
                "Conversation history is too large. Start a new conversation."
            )

        return self


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
    # Search query. Required and limited to a reasonable public request size.
    query: str = Field(..., min_length=1, max_length=2000)

    # Number of search results to return.
    # Defaults to 8.
    # Must be between 1 and 20.
    top_k: int = Field(default=8, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Query cannot be blank.")

        return value


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
