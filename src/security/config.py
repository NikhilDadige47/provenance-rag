"""Configuration models separating Owner infrastructure settings from ephemeral Visitor keys.

Enforces clear separation between secrets loaded from the server's environment
and credentials provided dynamically by visitors in HTTP headers.
"""

from enum import StrEnum

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.security.credit_config import DAILY_GLOBAL, VISITOR_ALLOWANCE
from src.security.secret import Secret


class AccessTier(StrEnum):
    """The three access tiers supported by Provenance RAG."""

    TIER_A_DEMO = "tier_a_demo"  # Zero keys, chat over pre-indexed demo corpus
    TIER_B_UPLOAD = "tier_b_upload"  # Upload PDF; owner-paid auto parse, optional visitor LLM key
    TIER_C_BYOK = "tier_c_byok"  # Visitor supplies both parser (or local) and own LLM key


class OwnerConfig(BaseSettings):
    """Owner configuration loaded strictly from server environment variables (.env).

    Never exposed to visitors.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def from_env(cls) -> "OwnerConfig":
        """Load owner configuration from server environment variables."""
        return cls()

    # General Environment
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    debug: bool = Field(default=False)

    # Cohere (Owner Embeddings & Reranking)
    cohere_api_key: Secret = Field(default=Secret("co_placeholder"))
    cohere_embed_model: str = Field(default="embed-english-v3.0")
    cohere_rerank_model: str = Field(default="rerank-english-v3.0")
    embedding_version: str = Field(default="emb-v1")

    # Qdrant Vector Store
    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: Secret | None = Field(default=None)
    qdrant_collection: str = Field(default="provenance_rag_v1")

    # Default LLM (Owner-Funded)
    default_llm_provider: str = Field(default="groq")
    default_llm_api_key: Secret = Field(default=Secret("gsk_placeholder"))
    default_llm_model: str = Field(default="openai/gpt-oss-120b")

    # Cloud Parser Keys (Owner Free Tier Pools)
    landingai_api_key: Secret | None = Field(default=None)
    llamaparse_api_key: Secret | None = Field(default=None)

    # Demo corpus ingest only (does not change visitor upload parsing)
    demo_parser: str = Field(
        default="local_pymupdf",
        description="Parser for demo_corpus ingest: local_pymupdf | llamaparse | landingai",
    )

    # Spend Controls & Caps (Owner Protection)
    kill_switch_active: bool = Field(default=False)
    kill_switch_disable_uploads: bool = Field(default=False)
    kill_switch_disable_owner_llm: bool = Field(default=False)

    # Per-session caps — defaults live in credit_config.VISITOR_ALLOWANCE
    session_max_chunks_embedded: int = Field(
        default=VISITOR_ALLOWANCE["session_max_chunks_embedded"]
    )
    session_max_rerank_calls: int = Field(default=VISITOR_ALLOWANCE["session_max_rerank_calls"])
    session_max_questions_owner_llm: int = Field(
        default=VISITOR_ALLOWANCE["session_max_questions_owner_llm"]
    )
    session_max_questions_own_llm: int = Field(
        default=VISITOR_ALLOWANCE["session_max_questions_own_llm"]
    )
    session_max_documents: int = Field(default=VISITOR_ALLOWANCE["session_max_documents"])
    session_max_total_pages: int = Field(default=VISITOR_ALLOWANCE["session_max_total_pages"])
    session_ttl_hours: int = Field(default=2)

    # Daily global caps — defaults live in credit_config.DAILY_GLOBAL
    daily_max_chunks_embedded: int = Field(default=DAILY_GLOBAL["max_chunks_embedded"])
    daily_max_rerank_calls: int = Field(default=DAILY_GLOBAL["max_rerank_calls"])
    daily_max_owner_llm_tokens: int = Field(default=DAILY_GLOBAL["max_owner_llm_tokens"])
    daily_max_jobs: int = Field(default=DAILY_GLOBAL["max_jobs"])


class VisitorKeys(BaseModel):
    """Ephemeral credentials supplied by visitors per request or job.

    These are kept in memory only and NEVER persisted.
    """

    parser_provider: str | None = Field(
        default=None, description="e.g., llamaparse, landingai, local_pymupdf"
    )
    parser_key: Secret | None = Field(
        default=None, description="Visitor's parser API key if required"
    )
    llm_provider: str | None = Field(default=None, description="e.g., groq, openai, anthropic")
    llm_key: Secret | None = Field(default=None, description="Visitor's LLM API key")
    llm_model: str | None = Field(
        default=None, description="Specific model requested on the visitor key"
    )


def detect_access_tier(keys: VisitorKeys, upload_requested: bool = False) -> AccessTier:
    """Classify the user's interaction into Tier A, Tier B, or Tier C."""
    if keys.llm_key is not None and bool(keys.llm_key.reveal()):
        return AccessTier.TIER_C_BYOK
    if (
        upload_requested
        or keys.parser_provider
        or (keys.parser_key and bool(keys.parser_key.reveal()))
    ):
        return AccessTier.TIER_B_UPLOAD
    return AccessTier.TIER_A_DEMO
