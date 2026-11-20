"""Authenticated endpoints for manual knowledge updates."""

import logging
import secrets
from pathlib import Path
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.config import KNOWLEDGE_ADMIN_TOKEN
from app.knowledge.index import KnowledgeIndexesRequired, require_knowledge_indexes
from app.knowledge.managed_content import ContentError, MAX_UPLOAD_BYTES
from app.services import knowledge_service as knowledge
from app.services.vector_store import get_qdrant_client


router = APIRouter(prefix="/admin/knowledge", include_in_schema=False)
logger = logging.getLogger(__name__)
NO_STORE = {"Cache-Control": "no-store"}
PAGE = Path(__file__).with_name("knowledge.html")


class PageInput(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


def require_enabled() -> None:
    if not KNOWLEDGE_ADMIN_TOKEN:
        raise HTTPException(404, "Not found.")


def require_admin(authorization: str = Header(default="")) -> None:
    require_enabled()
    expected = f"Bearer {KNOWLEDGE_ADMIN_TOKEN}".encode()
    if not secrets.compare_digest(authorization.encode(), expected):
        raise HTTPException(401, "Enter the administrator access token.")


def run_change(operation, *args) -> dict:
    # The backend runs one worker. Serialize mutations so simultaneous updates
    # cannot clean the just-published chunks of another request.
    if not knowledge.mutation_lock.acquire(blocking=False):
        raise HTTPException(409, "Another knowledge change is in progress. Try again shortly.")
    try:
        client = get_qdrant_client()
        require_knowledge_indexes(client)
        warning = operation(client, *args)
        return {"warning": warning}
    except KnowledgeIndexesRequired as error:
        raise HTTPException(
            503,
            f"{error}. Run python -m scripts.ensure_knowledge_indexes from the backend directory to check setup.",
        ) from error
    except ContentError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logger.exception("Knowledge change failed")
        raise HTTPException(502, "The change could not be confirmed. Reload the list before retrying.") from error
    finally:
        knowledge.mutation_lock.release()


@router.get("", dependencies=[Depends(require_enabled)], response_class=HTMLResponse)
def admin_page():
    nonce = secrets.token_urlsafe(24)
    return HTMLResponse(
        PAGE.read_text(encoding="utf-8").replace("__CSP_NONCE__", nonce),
        headers={
            **NO_STORE,
            "Content-Security-Policy": (
                f"default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
                "connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'"
            ),
            "Referrer-Policy": "no-referrer",
        },
    )


@router.get("/sources", dependencies=[Depends(require_admin)])
def sources():
    try:
        return JSONResponse({"sources": knowledge.list_sources(get_qdrant_client())}, headers=NO_STORE)
    except Exception as error:
        logger.exception("Could not list knowledge sources")
        raise HTTPException(502, "Could not load the knowledge list.") from error


@router.post("/pages", dependencies=[Depends(require_admin)])
def add_page(body: PageInput):
    return run_change(knowledge.add_page, body.url)


def update_one_page(client, key: str):
    records, point_ids = knowledge.catalog(client)
    return knowledge.update_page(client, key, records, point_ids)


@router.post("/sources/{key}/refresh", dependencies=[Depends(require_admin)])
def update_page(key: UUID):
    return run_change(update_one_page, str(key))


@router.post("/files", dependencies=[Depends(require_admin)])
async def upload_file(
    request: Request,
    key: UUID | None = None,
    x_knowledge_filename: str = Header(default=""),
    x_knowledge_public: str = Header(default=""),
):
    if x_knowledge_public != "yes":
        raise HTTPException(422, "Confirm the file can be used in public chat answers.")
    if not x_knowledge_filename or len(x_knowledge_filename) > 2048:
        raise HTTPException(422, "A valid filename is required.")
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Files must be 10 MB or smaller.")
        body.extend(part)
    return await run_in_threadpool(
        run_change, knowledge.upload_file, unquote(x_knowledge_filename), bytes(body),
        str(key) if key else None,
    )


def remove_one_source(client, key: str):
    records, point_ids = knowledge.catalog(client)
    return knowledge.remove_source(client, key, records, point_ids)


@router.delete("/sources/{key}", dependencies=[Depends(require_admin)])
def remove_source(key: UUID):
    return run_change(remove_one_source, str(key))
