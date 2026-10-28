import React from 'react';
import { Gauge, ShieldAlert, Zap, Clock, Database, CheckCircle2 } from 'lucide-react';
import { UsageInfo } from '../types';

interface LimitsPanelProps {
  usage: UsageInfo | null;
  scope: string;
}

export const LimitsPanel: React.FC<LimitsPanelProps> = ({ usage, scope }) => {
  const ownerUsed = usage?.questions_owner_llm_used ?? 0;
  const ownerMax = usage?.questions_owner_llm_max ?? 10;
  const ownerRemaining = usage?.questions_owner_llm_remaining ?? Math.max(0, ownerMax - ownerUsed);
  const ownerPct = Math.min(100, Math.round((ownerUsed / ownerMax) * 100));

  const rerankUsed = usage?.rerank_calls_used ?? 0;
  const rerankMax = usage?.rerank_calls_max ?? 20;
  const rerankPct = Math.min(100, Math.round((rerankUsed / rerankMax) * 100));

  const ownUsed = usage?.questions_own_llm_used ?? 0;
  const ownMax = usage?.questions_own_llm_max ?? 50;

  return (
    <div className="space-y-5">
      <div className="border border-border rounded-lg p-5 surface-inset shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Gauge className="size-5 text-primary" />
            <h3 className="font-semibold text-base">Session Limits & Cost Controls</h3>
          </div>
          <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
            Real-time Telemetry
          </span>
        </div>

        <p className="text-xs text-muted-foreground leading-relaxed">
          Provenance RAG enforces strict <strong>Owner Spend Controls</strong> and cost-ascending security gates to prevent runaway API spend while guaranteeing zero cross-tenant leakage.
        </p>

        {/* Meter 1: Owner LLM Questions */}
        <div className="p-3.5 rounded-lg border border-border bg-muted/30 space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold">
            <span className="flex items-center gap-1.5">
              <Zap className="size-4 text-primary" />
              Owner-Funded Questions (Demo & Uploads)
            </span>
            <span className="font-mono text-primary font-bold">
              {ownerRemaining} left / {ownerMax} max
            </span>
          </div>
          <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                ownerPct > 80 ? 'bg-amber-500' : 'bg-primary'
              }`}
              style={{ width: `${ownerPct}%` }}
            />
          </div>
          <div className="flex justify-between text-[11px] text-muted-foreground">
            <span>Used: {ownerUsed} questions</span>
            <span>Refreshes on new session</span>
          </div>
        </div>

        {/* Meter 2: Cohere Rerank v3.5 Calls */}
        <div className="p-3.5 rounded-lg border border-border bg-muted/30 space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold">
            <span className="flex items-center gap-1.5">
              <CheckCircle2 className="size-4 text-blue-500" />
              Cohere Rerank v3.5 Quota
            </span>
            <span className="font-mono text-blue-600 font-bold">
              {rerankMax - rerankUsed} left / {rerankMax} max
            </span>
          </div>
          <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-500"
              style={{ width: `${rerankPct}%` }}
            />
          </div>
          <div className="flex justify-between text-[11px] text-muted-foreground">
            <span>Circuit breaker fallback: BM25/Dense hybrid order</span>
          </div>
        </div>

        {/* Meter 3: BYOK Unlimited Allowance */}
        <div className="p-3.5 rounded-lg border border-border bg-muted/30 space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold">
            <span className="flex items-center gap-1.5">
              <Zap className="size-4 text-amber-500" />
              Visitor BYOK Model Questions
            </span>
            <span className="font-mono text-amber-600 font-bold">
              {ownUsed} used / {ownMax} session cap
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground">
            When supplying your personal API key, owner tokens are bypassed entirely.
          </p>
        </div>

        {/* Architecture Gates */}
        <div className="pt-2 border-t border-border space-y-2.5">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Enforced Security Gates (Cost-Ascending Order)
          </h4>
          <ul className="text-xs space-y-1.5 text-muted-foreground">
            <li className="flex items-start gap-2">
              <span className="size-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" />
              <span><strong>Gate 1: Prompt Injection Screen</strong> — Free regex & semantic boundary validator.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="size-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" />
              <span><strong>Gate 2: Kill Switch Checks</strong> — Owner emergency shutdown flags.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="size-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" />
              <span><strong>Gate 3: IP Daily Limit</strong> — 50 questions/day/IP sliding window.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="size-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" />
              <span><strong>Gate 4: Not-Found Gate</strong> — Saves LLM generation tokens when score &lt; 0.25.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="size-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" />
              <span><strong>Gate 5: Ephemeral TTL Cleanup</strong> — Background loop purges sessions every 300s.</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};
