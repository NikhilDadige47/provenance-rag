"""Chat, usage, and demo examples endpoints.

Implements roadmap P5-T4, P5-T5, P5-T6 & architecture §5, §9:

Endpoints:
  POST /chat      - Full RAG pipeline: validate → rewrite → search → rerank → expand → generate
  GET  /usage     - Return remaining session allowance (powers the frontend meter)
  GET  /examples  - Return clickable example questions for the demo corpus (Tier A)

Security & cost controls (all enforced BEFORE any paid API call):
  1. Rate limit check   (per-IP, enforced by caps.enforce_rate_limits dependency)
  2. Kill switch check  (per-request, owner can disable owner-LLM without redeploy)
  3. Prompt injection screen  (via validate_question)
  4. Session question cap    (per-session atomic increment)
  5. Daily global cap        (daily usage_daily check)
  6. Not-found gate before LLM  (saves tokens when retrieval fails)

Privacy: question text, document text, and API keys are NEVER written to logs.
Only metadata (request_id, tier, timings, counts) is logged.
"""

import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.api.caps import (
    check_and_increment_daily_llm_tokens,
    check_and_increment_daily_rerank,
    check_and_increment_session_byok_llm,
    check_and_increment_session_owner_llm,
    check_ip_daily_question_limit,
    check_kill_switch_owner_llm,
    enforce_rate_limits,
    increment_ip_daily_questions,
)
from src.api.logging import (
    generate_request_id,
    log_chat_request,
    log_chat_response,
)
from src.api.sessions import CurrentSession, VisitorLLMKeys
from src.generation.citations import audit_citations, normalize_citation_markers
from src.generation.llm import get_llm_adapter
from src.generation.prompt import build_generation_prompt, validate_question
from src.generation.rewrite import rewrite_query_if_needed
from src.retrieval.expansion import ContextExpander
from src.retrieval.search import HybridSearchPipeline
from src.security.config import OwnerConfig
from src.security.errors import InvalidKeyError, QuotaExhaustedError
from src.security.secret import Secret
from src.storage.db import DatabaseManager

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Example questions for the demo corpus (Tier A / GET /examples)
# Prefer eval/golden_set.jsonl so UI chips match the live eval set.
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_SET_PATH = _ROOT / "eval" / "golden_set.jsonl"
_DEMO_QUESTIONS_PATH = _ROOT / "demo_corpus" / "example_questions.json"

_FALLBACK_DEMO_EXAMPLES: list[dict[str, str]] = [
    {
        "id": "q1",
        "question": "What was Apple's total net sales in fiscal year 2023?",
        "category": "fy2023",
    },
    {
        "id": "q2",
        "question": "What was Apple's total net sales in fiscal year 2024?",
        "category": "fy2024",
    },
    {
        "id": "q3",
        "question": "What was Apple's total net sales in fiscal year 2025?",
        "category": "fy2025",
    },
    {
        "id": "q9",
        "question": "What was Apple's total copper mining revenue on Mars?",
        "category": "not_found",
    },
    {
        "id": "q10",
        "question": "How many supersonic passenger jets did Apple deliver in 2023?",
        "category": "not_found",
    },
]


def _category_from_example(item: dict) -> str:
    doc = str(item.get("document") or "")
    digits = "".join(ch for ch in doc if ch.isdigit())
    if len(digits) >= 4:
        return f"fy{digits[-4:]}"
    if not doc:
        return "not_found"
    return "finance"


def _load_golden_examples() -> list[dict[str, str]]:
    try:
        lines = _GOLDEN_SET_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    examples: list[dict[str, str]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        examples.append(
            {
                "id": str(item.get("id") or f"ex_{len(examples) + 1}"),
                "question": question,
                "category": str(item.get("category") or "demo"),
            }
        )
    return examples


def _load_demo_examples() -> list[dict[str, str]]:
    golden = _load_golden_examples()
    if golden:
        return golden
    try:
        raw = json.loads(_DEMO_QUESTIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return list(_FALLBACK_DEMO_EXAMPLES)
    if not isinstance(raw, list):
        return list(_FALLBACK_DEMO_EXAMPLES)
    examples: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        chip = str(item.get("chip") or item.get("question") or "").strip()
        if not chip:
            continue
        examples.append(
            {
                "id": str(item.get("id") or f"ex_{len(examples) + 1}"),
                "question": chip,
                "category": _category_from_example(item),
            }
        )
    return examples or list(_FALLBACK_DEMO_EXAMPLES)


DEMO_EXAMPLES: list[dict[str, str]] = _load_demo_examples()

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ChatTurn(BaseModel):
    """A single conversation turn."""

    role: str = Field(pattern="^(user|assistant)$", description="'user' or 'assistant'")
    content: str = Field(max_length=2000, description="Text content of the turn")


class ChatRequest(BaseModel):
    """Request body for POST /chat."""

    question: str = Field(
        min_length=1,
        max_length=1000,
        description="The user's question (max 1000 chars)",
    )
    history: list[ChatTurn] = Field(
        default_factory=list,
        max_length=10,
        description="Up to 10 prior conversation turns for follow-up rewrites",
    )


class SourceCard(BaseModel):
    """Provenance metadata for a single cited source."""

    citation: str
    title: str
    page: int
    breadcrumb: str
    snippet: str


class ChatResponse(BaseModel):
    """Response body for POST /chat."""

    request_id: str
    question: str
    answer: str
    sources: list[SourceCard]
    is_found: bool
    is_grounded: bool
    used_visitor_key: bool
    timings_ms: dict[str, float]
    model_used: str | None = None
    # Never included: session_id, scope, API keys, full document text


class UsageResponse(BaseModel):
    """Response body for GET /usage — powers the frontend allowance meter."""

    tier: str
    questions_owner_llm_used: int
    questions_owner_llm_max: int
    questions_owner_llm_remaining: int
    questions_own_llm_used: int
    questions_own_llm_max: int
    questions_own_llm_remaining: int
    rerank_calls_used: int
    rerank_calls_max: int
    at_capacity: bool
    session_expires_at: str
    owner_llm_provider: str
    owner_llm_model: str


class ExamplesResponse(BaseModel):
    """Response body for GET /examples."""

    examples: list[dict[str, str]]
    corpus: str = "provenance_rag_demo"


def _dedupe_source_cards(cards: list[SourceCard]) -> list[SourceCard]:
    """Drop source chips that repeat the same document snippet."""
    unique: list[SourceCard] = []
    seen: set[tuple[str, int, str]] = set()
    for card in cards:
        snippet_key = " ".join(card.snippet.lower().split())[:120]
        key = (card.title.strip().lower(), card.page, snippet_key)
        if key in seen:
            continue
        seen.add(key)
        unique.append(card)
    return unique


# ---------------------------------------------------------------------------
# GET /examples  (Tier A demo: clickable question chips, no auth required)
# ---------------------------------------------------------------------------


@router.get(
    "/examples",
    response_model=ExamplesResponse,
    summary="Get demo example questions",
    description=(
        "Returns a curated list of example questions for the demo corpus. "
        "No session token required — anyone can fetch these."
    ),
)
async def get_examples() -> ExamplesResponse:
    """Return example questions for the Tier-A demo corpus."""
    return ExamplesResponse(examples=DEMO_EXAMPLES)


# ---------------------------------------------------------------------------
# GET /usage  (returns session's remaining allowance)
# ---------------------------------------------------------------------------


@router.get(
    "/usage",
    response_model=UsageResponse,
    summary="Get remaining session allowance",
)
async def get_usage(
    request: Request,
    session: CurrentSession,
) -> UsageResponse:
    """Return the current session's usage counters and remaining allowances.

    Powers the frontend usage meter — no question/document content is returned.
    """
    cfg: OwnerConfig = request.app.state.cfg
    db: DatabaseManager = request.app.state.db

    # Reload fresh counters from DB
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session.session_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    row_dict = dict(row)
    q_owner_used = row_dict.get("questions_owner_llm", 0)
    q_own_used = row_dict.get("questions_own_llm", 0)
    rerank_used = row_dict.get("rerank_calls", 0)
    q_owner_max = cfg.session_max_questions_owner_llm
    q_own_max = cfg.session_max_questions_own_llm
    rerank_max = cfg.session_max_rerank_calls

    at_capacity = q_owner_used >= q_owner_max and q_own_used >= q_own_max

    return UsageResponse(
        tier=session.tier.value,
        questions_owner_llm_used=q_owner_used,
        questions_owner_llm_max=q_owner_max,
        questions_owner_llm_remaining=max(0, q_owner_max - q_owner_used),
        questions_own_llm_used=q_own_used,
        questions_own_llm_max=q_own_max,
        questions_own_llm_remaining=max(0, q_own_max - q_own_used),
        rerank_calls_used=rerank_used,
        rerank_calls_max=rerank_max,
        at_capacity=at_capacity,
        session_expires_at=session.expires_at,
        owner_llm_provider=cfg.default_llm_provider,
        owner_llm_model=cfg.default_llm_model,
    )


# ---------------------------------------------------------------------------
# POST /chat  (the full RAG pipeline)
# ---------------------------------------------------------------------------


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask a question over the RAG corpus",
    dependencies=[Depends(enforce_rate_limits)],
)
async def chat(
    request: Request,
    body: ChatRequest,
    session: CurrentSession,
    visitor_keys: VisitorLLMKeys,
) -> ChatResponse:
    """Execute the full Provenance RAG pipeline.

    Security gates run in cost-ascending order:
      1. Injection screen (free)
      2. Kill switch (free)
      3. IP daily question cap (free)
      4. Session question cap (atomic DB update)
      5. Daily global rerank cap (atomic DB update)
      6. Not-found gate (before any LLM call)
      7. Session LLM cap + daily LLM token cap (after retrieval succeeds)

    The server always enforces scope = session.scope + "demo".
    Clients cannot supply or override scope/filters.
    """
    request_id = generate_request_id()
    start_time = time.time()
    timings: dict[str, float] = {}

    cfg: OwnerConfig = request.app.state.cfg
    db: DatabaseManager = request.app.state.db

    # Scope is always derived server-side from the validated session token
    scope = session.scope

    # Privacy log: question LENGTH only, not content
    log_chat_request(
        request_id=request_id,
        tier=session.tier.value,
        scope_prefix=scope[:8],
        has_visitor_key=visitor_keys.llm_key is not None,
        question_length=len(body.question),
        history_turns=len(body.history),
    )

    # ── Gate 1: Prompt injection screen ────────────────────────────────────
    is_valid, err_msg = validate_question(body.question)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid question: {err_msg}",
        )

    # ── Gate 2: Kill switch (owner LLM disabled + no visitor key) ──────────
    using_visitor_key = visitor_keys.llm_key is not None and bool(visitor_keys.llm_key.reveal())
    if not using_visitor_key:
        check_kill_switch_owner_llm(cfg)

    # ── Gate 3: Per-IP daily question cap ──────────────────────────────────
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (
        request.client.host if request.client else "unknown"
    )
    check_ip_daily_question_limit(client_ip)

    # ── Gate 4: Per-session question cap (increment BEFORE the pipeline) ───
    if using_visitor_key:
        check_and_increment_session_byok_llm(db, session.session_id, cfg)
    else:
        check_and_increment_session_owner_llm(db, session.session_id, cfg)

    # ── Resolve LLM adapter ────────────────────────────────────────────────
    llm_secret: Secret | None = None
    if using_visitor_key:
        llm_secret = visitor_keys.llm_key

    history_dicts = [turn.model_dump() for turn in body.history]

    try:
        llm = get_llm_adapter(
            provider=visitor_keys.llm_provider if using_visitor_key else None,
            api_key=llm_secret,
            model=visitor_keys.llm_model if using_visitor_key else None,
        )
        model_used = f"{llm.provider_name}/{getattr(llm, '_model', '')}".rstrip("/")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported LLM provider: {exc}",
        ) from exc

    # ── Step 1: Conditional query rewrite (follow-ups only) ────────────────
    t0 = time.time()
    try:
        effective_query = await rewrite_query_if_needed(
            query=body.question,
            history=history_dicts,
            llm=llm,
            api_key=llm_secret,
        )
    except Exception:
        effective_query = body.question  # safe fallback
    timings["rewrite_ms"] = round((time.time() - t0) * 1000, 1)

    # ── Step 2: Hybrid search (dense + sparse, scope-filtered) ─────────────
    t0 = time.time()
    search_pipeline = HybridSearchPipeline()
    try:
        search_result = await search_pipeline.search(
            query=effective_query,
            scope=scope,
        )
    except Exception as exc:
        logger.error(f"Search failed [{request_id}]: {type(exc).__name__}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search is temporarily unavailable. Please try again.",
        ) from exc
    timings["retrieval_ms"] = round((time.time() - t0) * 1000, 1)

    # ── Gate 5: Daily rerank cap ────────────────────────────────────────────
    check_and_increment_daily_rerank(db, cfg)

    # ── Gate 6: Not-found gate (before any LLM call → saves tokens) ────────
    if not search_result.is_found:
        total_ms = round((time.time() - start_time) * 1000, 1)
        timings["total_ms"] = total_ms
        log_chat_response(
            request_id=request_id,
            tier=session.tier.value,
            is_found=False,
            is_grounded=False,
            used_visitor_key=using_visitor_key,
            answer_length=0,
            source_count=0,
            timings=timings,
            tokens_used=0,
        )
        return ChatResponse(
            request_id=request_id,
            question=body.question,
            answer="I could not find the answer in the provided documents.",
            sources=[],
            is_found=False,
            is_grounded=False,
            used_visitor_key=using_visitor_key,
            timings_ms=timings,
            model_used=model_used,
        )

    # ── Step 3: Parent / window context expansion ───────────────────────────
    t0 = time.time()
    expander = ContextExpander(db=db)
    expansion_res = expander.expand(chunks=search_result.chunks, scope=scope)
    timings["expansion_ms"] = round((time.time() - t0) * 1000, 1)

    # ── Step 4: Build prompt ────────────────────────────────────────────────
    _, user_prompt = build_generation_prompt(
        question=body.question,
        passages=expansion_res.passages,
    )

    # ── Step 5: Stream generation ───────────────────────────────────────────
    t0 = time.time()
    answer_tokens: list[str] = []
    generation_failed = False

    try:
        async for token in llm.generate_stream(user_prompt, api_key=llm_secret):
            answer_tokens.append(token)
    except (InvalidKeyError, QuotaExhaustedError) as exc:
        generation_failed = True
        logger.warning(f"Visitor key error [{request_id}]: {exc.message}")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Your LLM key was rejected or quota exceeded: {exc.message} "
                "Check your provider account, or remove the X-LLM-Key header to use "
                "the owner's default LLM (subject to session caps)."
            ),
        ) from exc
    except Exception as exc:
        generation_failed = True
        logger.error(f"Generation error [{request_id}]: {type(exc).__name__}")
        answer_tokens = [
            "Generation is temporarily unavailable. Please refer to the verified sources below."
        ]

    timings["generation_ms"] = round((time.time() - t0) * 1000, 1)
    full_answer = normalize_citation_markers("".join(answer_tokens).strip())

    # Rough token estimate: ~1 token per 4 characters
    estimated_tokens = max(1, len(full_answer) // 4)

    # ── Gate 7: Daily LLM token cap (only for owner-funded calls) ──────────
    if not using_visitor_key and not generation_failed:
        check_and_increment_daily_llm_tokens(db, estimated_tokens, cfg)

    # ── Step 6: Citation audit ──────────────────────────────────────────────
    t0 = time.time()
    audit_res = audit_citations(full_answer, passages=expansion_res.passages)
    timings["citation_ms"] = round((time.time() - t0) * 1000, 1)

    timings["total_ms"] = round((time.time() - start_time) * 1000, 1)

    # ── Build source cards ──────────────────────────────────────────────────
    if audit_res.sources:
        raw_sources = [
            SourceCard(
                citation=f"[{s.citation_index}]",
                title=s.title,
                page=s.page,
                breadcrumb=s.breadcrumb,
                snippet=s.text_snippet,
            )
            for s in audit_res.sources
        ]
    else:
        raw_sources = [
            SourceCard(
                citation=f"[{idx}]",
                title=p.title,
                page=p.page,
                breadcrumb=p.breadcrumb,
                snippet=p.text,
            )
            for idx, p in enumerate(expansion_res.passages, start=1)
        ]
    sources = _dedupe_source_cards(raw_sources)

    # ── Increment IP daily counter (only after successful generation) ───────
    increment_ip_daily_questions(client_ip)

    # ── Privacy log: metadata only ──────────────────────────────────────────
    log_chat_response(
        request_id=request_id,
        tier=session.tier.value,
        is_found=True,
        is_grounded=audit_res.is_grounded,
        used_visitor_key=using_visitor_key,
        answer_length=len(full_answer),
        source_count=len(sources),
        timings=timings,
        tokens_used=estimated_tokens,
    )

    return ChatResponse(
        request_id=request_id,
        question=body.question,
        answer=full_answer,
        sources=sources,
        is_found=True,
        is_grounded=audit_res.is_grounded,
        used_visitor_key=using_visitor_key,
        timings_ms=timings,
        model_used=model_used,
    )
