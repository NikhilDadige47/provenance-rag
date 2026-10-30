import { useEffect, useState } from 'react';
import { UsageInfo } from '../types';

/** Fallbacks match src/security/credit_config.py — never invent a different cap. */
export const ALLOWANCE_DEFAULTS = {
  ownerQuestions: 15,
  ownQuestions: 100,
  rerank: 30,
  docs: 3,
  pages: 30,
  ipDailyQuestions: 15,
  requestsPerMinute: 20,
} as const;

export function readUsage(usage: UsageInfo | null) {
  return {
    ownerUsed: usage?.questions_owner_llm_used ?? 0,
    ownerMax: usage?.questions_owner_llm_max ?? ALLOWANCE_DEFAULTS.ownerQuestions,
    ownerRemaining:
      usage?.questions_owner_llm_remaining ??
      Math.max(
        0,
        (usage?.questions_owner_llm_max ?? ALLOWANCE_DEFAULTS.ownerQuestions) -
          (usage?.questions_owner_llm_used ?? 0)
      ),
    ownUsed: usage?.questions_own_llm_used ?? 0,
    ownMax: usage?.questions_own_llm_max ?? ALLOWANCE_DEFAULTS.ownQuestions,
    rerankUsed: usage?.rerank_calls_used ?? 0,
    rerankMax: usage?.rerank_calls_max ?? ALLOWANCE_DEFAULTS.rerank,
    docsUsed: usage?.session_docs_used ?? 0,
    docsMax: usage?.session_docs_max ?? ALLOWANCE_DEFAULTS.docs,
    pagesUsed: usage?.session_pages_used ?? 0,
    pagesMax: usage?.session_pages_max ?? ALLOWANCE_DEFAULTS.pages,
    ttlSeconds: usage?.session_ttl_seconds ?? 0,
    ipDailyMax: usage?.daily_questions_per_ip_max ?? ALLOWANCE_DEFAULTS.ipDailyQuestions,
    rpmMax: usage?.requests_per_minute_max ?? ALLOWANCE_DEFAULTS.requestsPerMinute,
    ownerExhausted: usage?.owner_questions_exhausted ?? false,
    atCapacity: usage?.at_capacity ?? false,
    expiresAt: usage?.session_expires_at ?? '',
  };
}

export function useLiveTtl(usage: UsageInfo | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 15000);
    return () => window.clearInterval(id);
  }, []);
  if (usage?.session_expires_at) {
    const exp = Date.parse(usage.session_expires_at);
    if (!Number.isNaN(exp)) return Math.max(0, Math.floor((exp - now) / 1000));
  }
  return usage?.session_ttl_seconds ?? 0;
}

export function formatTtl(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  if (seconds <= 0) return 'Expired';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m left`;
  if (minutes > 0) return `${minutes}m left`;
  return `${seconds}s left`;
}

export function parserDisplay(parser: string | undefined | null): {
  label: string;
  detail: string;
  degraded: boolean;
} {
  const raw = (parser || '').toLowerCase();
  if (raw.startsWith('landing')) {
    return {
      label: 'Premium parse',
      detail: 'Landing AI',
      degraded: false,
    };
  }
  if (raw.startsWith('llama')) {
    return {
      label: 'Standard parse',
      detail: 'LlamaParse',
      degraded: false,
    };
  }
  if (raw.includes('pymupdf') || raw.includes('local') || raw.includes('floor')) {
    return {
      label: 'Basic extract',
      detail: 'Local PyMuPDF',
      degraded: true,
    };
  }
  if (!raw || raw === 'auto') {
    return {
      label: 'Auto parse',
      detail: 'Owner waterfall',
      degraded: false,
    };
  }
  return { label: parser || 'Parser', detail: raw, degraded: false };
}
