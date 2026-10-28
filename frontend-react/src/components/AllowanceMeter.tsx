import React from 'react';
import { Gauge, Clock, Sparkles } from 'lucide-react';
import { UsageInfo } from '../types';

interface AllowanceMeterProps {
  usage: UsageInfo | null;
}

export const AllowanceMeter: React.FC<AllowanceMeterProps> = ({ usage }) => {
  if (!usage) {
    return (
      <div className="border border-border rounded-lg p-3 bg-card/60 animate-pulse flex items-center justify-between">
        <div className="h-4 w-40 bg-muted rounded"></div>
        <div className="h-4 w-20 bg-muted rounded"></div>
      </div>
    );
  }

  const ownerUsed = usage.questions_owner_llm_used ?? 0;
  const ownerMax = usage.questions_owner_llm_max ?? 10;
  const ownerRemaining = usage.questions_owner_llm_remaining ?? Math.max(0, ownerMax - ownerUsed);
  const ownerPct = Math.min(100, Math.round((ownerUsed / ownerMax) * 100));

  const rerankUsed = usage.rerank_calls_used ?? 0;
  const rerankMax = usage.rerank_calls_max ?? 20;

  return (
    <div className="border border-border rounded-lg p-4 surface-inset shadow-sm space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Gauge className="size-4 text-primary" />
          <span className="font-semibold text-xs uppercase tracking-wider text-muted-foreground">
            Session Capacity Meter
          </span>
        </div>
        {usage.at_capacity ? (
          <span className="text-[11px] font-semibold text-destructive bg-destructive/10 px-2 py-0.5 rounded-full border border-destructive/20">
            Capacity Reached
          </span>
        ) : (
          <span className="text-[11px] font-semibold text-emerald-600 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            Active Session
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
        {/* Owner LLM questions */}
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground flex items-center gap-1">
              <Sparkles className="size-3 text-primary" />
              Owner LLM Queries
            </span>
            <span className="font-mono font-medium">
              {ownerRemaining} left <span className="text-muted-foreground/60">/ {ownerMax}</span>
            </span>
          </div>
          <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                ownerPct > 80 ? 'bg-amber-500' : 'bg-primary'
              }`}
              style={{ width: `${ownerPct}%` }}
            />
          </div>
        </div>

        {/* Neural Rerank calls */}
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">Cohere Rerank v3.5</span>
            <span className="font-mono font-medium">
              {rerankUsed} used <span className="text-muted-foreground/60">/ {rerankMax}</span>
            </span>
          </div>
          <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-500"
              style={{ width: `${Math.min(100, Math.round((rerankUsed / rerankMax) * 100))}%` }}
            />
          </div>
        </div>

        {/* Session expiry countdown */}
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground flex items-center gap-1">
              <Clock className="size-3" />
              Session TTL
            </span>
            <span className="font-mono font-medium text-xs">30 mins active</span>
          </div>
          <div className="text-[11px] text-muted-foreground/80 truncate">
            Auto-wipes upon tab close or inactivity
          </div>
        </div>
      </div>
    </div>
  );
};
