export type AccessTier = 'tier_a' | 'tier_b' | 'tier_c';

export interface SourceCard {
  citation: string;
  title: string;
  page: number;
  breadcrumb: string;
  snippet: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  timings_ms?: Record<string, number>;
  sources?: SourceCard[];
  is_found?: boolean;
  is_grounded?: boolean;
  rerank_fallback?: boolean;
  used_visitor_key?: boolean;
  model_used?: string;
  traceStages?: PipelineStageInfo[];
}

export interface PipelineStageInfo {
  id: string;
  label: string;
  status: 'done' | 'active' | 'pending';
  latencyMs?: number;
  items: string[];
}

export interface UsageInfo {
  tier: string;
  questions_owner_llm_used: number;
  questions_owner_llm_max: number;
  questions_owner_llm_remaining: number;
  questions_own_llm_used: number;
  questions_own_llm_max: number;
  questions_own_llm_remaining: number;
  rerank_calls_used: number;
  rerank_calls_max: number;
  at_capacity: boolean;
  session_expires_at: string;
  owner_llm_provider?: string;
  owner_llm_model?: string;
}

export interface ExampleQuestion {
  id: string;
  question: string;
  category?: string;
}

export interface UploadedDoc {
  doc_id: string;
  filename: string;
  chunk_count: number;
  token_count: number;
  parser_tier: string;
  uploaded_at: string;
}

export interface CostEstimate {
  filename?: string;
  page_count: number;
  estimated_chunks: number;
  requires_visitor_key?: boolean;
  parser_name?: string;
  session_docs_count: number;
  session_max_docs: number;
  session_pages_used: number;
  session_max_pages: number;
  session_chunks_embedded?: number;
  session_max_chunks?: number;
  can_proceed: boolean;
  message?: string;
  estimated_pages?: number;
  estimated_cost_usd?: number;
  free_allowance_remaining?: number;
}

export interface LLMConfig {
  provider: 'groq' | 'openai' | 'anthropic' | 'gemini' | 'mistral';
  model: string;
  key: string;
}
