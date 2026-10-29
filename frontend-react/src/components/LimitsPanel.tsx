import React from 'react';
import { Gauge, Zap, Clock, Shield, Database } from 'lucide-react';
import { UsageInfo } from '../types';
import { formatTtl, readUsage, useLiveTtl } from '../lib/quota';

interface LimitsPanelProps {
  usage: UsageInfo | null;
  scope: string;
  hasVisitorKey?: boolean;
  onAddKey?: () => void;
}

function Meter({
  label,
  remaining,
  max,
  usedLabel,
  hint,
  warn,
}: {
  label: string;
  remaining: number;
  max: number;
  usedLabel: string;
  hint: string;
  warn?: boolean;
}) {
  const used = Math.max(0, max - remaining);
  const pct = Math.min(100, Math.round((used / Math.max(1, max)) * 100));
  return (
    <div className="p-3.5 rounded-lg border border-border bg-muted/30 space-y-2">
      <div className="flex items-center justify-between text-xs font-semibold gap-2">
        <span>{label}</span>
        <span className={`font-mono ${warn ? 'text-amber-600' : 'text-primary'}`}>
          {remaining} left / {max}
        </span>
      </div>
      <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
        <div
          className={`h-full transition-all duration-500 ${pct > 80 ? 'bg-amber-500' : 'bg-primary'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex justify-between text-[11px] text-muted-foreground gap-2">
        <span>{usedLabel}</span>
        <span>{hint}</span>
      </div>
    </div>
  );
}

export const LimitsPanel: React.FC<LimitsPanelProps> = ({
  usage,
  scope,
  hasVisitorKey = false,
  onAddKey,
}) => {
  const q = readUsage(usage);
  const ttl = useLiveTtl(usage);
  const ownerWarn = q.ownerRemaining === 0 && !hasVisitorKey;

  return (
    <div className="space-y-5">
      <div className="border border-border rounded-lg p-5 surface-inset shadow-sm space-y-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Gauge className="size-5 text-primary shrink-0" />
            <h3 className="font-semibold text-base">Session limits</h3>
          </div>
          <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 shrink-0">
            {scope === 'demo' ? 'Demo corpus' : 'Private session'}
          </span>
        </div>

        <p className="text-xs text-muted-foreground leading-relaxed">
          You see questions left. Behind that, the server reserves real LLM tokens before each
          answer and spends parser credits only when a document needs a paid parse. Repeats of the
          same file are free. If a premium parser is out of budget, extraction falls back to local
          text instead of failing.
        </p>

        {ownerWarn && (
          <div className="flex items-start justify-between gap-3 p-3 rounded-lg border border-amber-500/30 bg-amber-500/10">
            <div className="min-w-0">
              <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">
                Owner-funded questions are used up
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Paste your own LLM key on Upload Documents to keep chatting. Your key is never stored.
              </p>
            </div>
            {onAddKey && (
              <button
                type="button"
                onClick={onAddKey}
                className="shrink-0 text-[11px] font-semibold px-2.5 py-1 rounded-md bg-amber-600 text-white hover:bg-amber-500"
              >
                Add key
              </button>
            )}
          </div>
        )}

        <Meter
          label={hasVisitorKey ? 'Your-key questions' : 'Owner-funded questions'}
          remaining={hasVisitorKey ? Math.max(0, q.ownMax - q.ownUsed) : q.ownerRemaining}
          max={hasVisitorKey ? q.ownMax : q.ownerMax}
          usedLabel={
            hasVisitorKey ? `Used ${q.ownUsed} on your key` : `Used ${q.ownerUsed} owner questions`
          }
          hint="Resets with a new session"
          warn={ownerWarn}
        />

        <Meter
          label="Rerank calls"
          remaining={Math.max(0, q.rerankMax - q.rerankUsed)}
          max={q.rerankMax}
          usedLabel={`Used ${q.rerankUsed}`}
          hint="Falls back to hybrid search if exhausted"
        />

        <Meter
          label="Uploaded documents"
          remaining={Math.max(0, q.docsMax - q.docsUsed)}
          max={q.docsMax}
          usedLabel={`${q.pagesUsed} / ${q.pagesMax} pages used`}
          hint="Owner-paid parse, local floor"
        />

        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <div className="p-3 rounded-lg border border-border bg-muted/20 space-y-1">
            <div className="flex items-center gap-1.5 font-semibold text-foreground">
              <Clock className="size-3.5 text-muted-foreground" />
              Session TTL
            </div>
            <p className="font-mono text-sm">{formatTtl(ttl)}</p>
            <p className="text-muted-foreground">Wipes on tab close or expiry</p>
          </div>
          <div className="p-3 rounded-lg border border-border bg-muted/20 space-y-1">
            <div className="flex items-center gap-1.5 font-semibold text-foreground">
              <Zap className="size-3.5 text-muted-foreground" />
              Answer model
            </div>
            <p className="font-mono text-sm truncate">
              {hasVisitorKey ? 'Your key' : usage?.owner_llm_provider || 'groq'}
            </p>
            <p className="text-muted-foreground truncate">
              {hasVisitorKey ? 'Owner tokens skipped' : usage?.owner_llm_model || 'capped output'}
            </p>
          </div>
        </div>

        <div className="pt-2 border-t border-border space-y-2.5">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            What is enforced
          </h4>
          <ul className="text-xs space-y-1.5 text-muted-foreground">
            <li className="flex items-start gap-2">
              <Shield className="size-3.5 mt-0.5 text-emerald-500 shrink-0" />
              <span>
                <strong>Before paid calls:</strong> injection screen, kill switch, {q.rpmMax}{' '}
                requests/min/IP, {q.ipDailyMax} questions/day/IP.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <Zap className="size-3.5 mt-0.5 text-emerald-500 shrink-0" />
              <span>
                <strong>Chat:</strong> reserve prompt + output tokens, then commit the provider’s
                real usage. Not-found retrieval skips generation.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <Database className="size-3.5 mt-0.5 text-emerald-500 shrink-0" />
              <span>
                <strong>Upload:</strong> Landing AI standard jobs → LlamaParse → local PyMuPDF.
                Same file hash is cached globally at 0 credits.
              </span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};
