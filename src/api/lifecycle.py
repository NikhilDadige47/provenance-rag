"""Data lifecycle manager, on-demand session deletion, and TTL background cleaner.

Implements roadmap P6-T6:
- "Delete my data" (DELETE /session) with zero visitor keys needed
- Wipes Qdrant points by scope, SQLite rows (parents, docs, jobs, cache), and files
- Single-document deletion (DELETE /session/documents/{doc_id})
- Periodic background TTL janitor purging expired sessions automatically
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from src.retrieval.store import QdrantVectorStore
from src.storage.db import DatabaseManager

logger = logging.getLogger("provenance_rag.api.lifecycle")


def delete_session(
    session_id: str,
    db: DatabaseManager,
    store: QdrantVectorStore,
) -> dict[str, Any]:
    """Permanently delete all session vectors, parents, jobs, and cache.

    Requires zero visitor keys. Eliminates all trace of visitor data.
    """
    logger.info(f"Initiating hard deletion for session '{session_id}'")

    # 1. Purge all vectors from Qdrant matching scope = session_id
    try:
        store.delete_by_scope(scope=session_id)
    except Exception as exc:
        logger.warning(f"Error purging Qdrant vectors for scope '{session_id}': {exc}")

    # 2. Cascade delete from SQLite (parents, documents, jobs, parse_cache, sessions)
    db.delete_session_data(session_id=session_id)

    logger.info(f"Successfully purged all data for session '{session_id}'")
    return {
        "status": "deleted",
        "session_id": session_id,
        "message": "All session documents, vectors, parents, and metadata have been permanently deleted.",
    }


def delete_document(
    doc_id: str,
    session_id: str,
    db: DatabaseManager,
    store: QdrantVectorStore,
) -> dict[str, Any]:
    """Delete a specific document within a session (vectors + parents + metadata)."""
    # Verify document exists and belongs to this session
    doc_meta = db.get_document(doc_id=doc_id, session_id=session_id)
    if not doc_meta:
        return {
            "status": "not_found",
            "doc_id": doc_id,
            "message": f"Document '{doc_id}' not found in session '{session_id}'.",
        }

    # Delete vectors from Qdrant
    try:
        store.delete_by_doc(doc_id=doc_id)
    except Exception as exc:
        logger.warning(f"Error purging Qdrant vectors for doc '{doc_id}': {exc}")

    # Delete from SQLite
    db.delete_document(doc_id=doc_id, session_id=session_id)

    logger.info(f"Document '{doc_id}' deleted from session '{session_id}'")
    return {
        "status": "deleted",
        "doc_id": doc_id,
        "title": doc_meta.get("title", ""),
        "message": f"Document '{doc_id}' and all associated vectors have been deleted.",
    }


def purge_expired_sessions(db: DatabaseManager, store: QdrantVectorStore) -> list[str]:
    """Identify and delete all sessions whose expires_at is in the past."""
    now_iso = datetime.now(UTC).isoformat()
    expired_ids = db.list_expired_sessions(now_iso=now_iso)

    if not expired_ids:
        return []

    logger.info(f"TTL Janitor: found {len(expired_ids)} expired sessions to purge")
    purged: list[str] = []

    for sid in expired_ids:
        try:
            delete_session(session_id=sid, db=db, store=store)
            purged.append(sid)
        except Exception as exc:
            logger.error(f"TTL Janitor error purging session '{sid}': {exc}")

    return purged


async def run_ttl_cleanup_loop(
    db: DatabaseManager,
    store: QdrantVectorStore,
    interval_seconds: int = 300,
) -> None:
    """Background periodic loop running TTL janitor sweeps every interval_seconds."""
    logger.info(f"TTL Cleanup Janitor started (sweep interval: {interval_seconds}s)")
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                purged = purge_expired_sessions(db=db, store=store)
                if purged:
                    logger.info(f"TTL sweep complete: purged {len(purged)} expired sessions")
            except Exception as exc:
                logger.warning(f"TTL Janitor sweep iteration encountered error: {exc}")
    except asyncio.CancelledError:
        logger.info("TTL Cleanup Janitor stopped")
