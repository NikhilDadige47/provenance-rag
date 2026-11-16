import React from 'react';
import { Gauge, Zap, Clock, Shield, Database } from 'lucide-react';
import { UsageInfo } from '../types';
import { formatTtl, readUsage, useLiveTtl } from '../lib/quota';
import { formatModelDisplayName } from '../lib/modelUtils';

interface LimitsPanelProps {
  usage: UsageInfo | null;
  scope: string;
  hasVisitorKey?: boolean;
  onAddKey?: () => void;
  defaultModel?: string;
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
      <div className="flex flex-wrap justify-between gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
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
  defaultModel,
}) => {
  const q = readUsage(usage);
  const ttl = useLiveTtl(usage);
  const ownerWarn = q.ownerRemaining === 0 && !hasVisitorKey;

  return (
    <div className="space-y-5">
      <div className="border border-border rounded-lg p-4 sm:p-5 surface-inset shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Gauge className="size-5 text-primary shrink-0" />
            <h3 className="font-semibold text-base">Session Allowance & Quotas</h3>
          </div>
          <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 shrink-0">
            {scope === 'demo' ? 'Sample Reports' : 'Private Session'}
          </span>
        </div>

        <p className="text-xs text-muted-foreground leading-relaxed">
          Every visitor receives a generous daily question allowance. Every answer links directly to verified source citations. You can connect your own free API key in AI Models anytime for unlimited questions.
        </p>

        {ownerWarn && (
          <div className="flex items-start justify-between gap-3 p-3 rounded-lg border border-amber-500/30 bg-amber-500/10">
            <div className="min-w-0">
              <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">
                Free daily questions reached
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Connect your own API key in AI Models to continue chatting freely. Your key stays in your browser.
              </p>
            </div>
            {onAddKey && (
              <button
                type="button"
                onClick={onAddKey}
                className="shrink-0 text-[11px] font-semibold px-2.5 py-1 rounded-md bg-amber-600 text-white hover:bg-amber-500"
              >
                Connect Key
              </button>
            )}
          </div>
        )}

        <Meter
          label={hasVisitorKey ? 'Your API Key Questions' : 'Free Daily Questions'}
          remaining={hasVisitorKey ? Math.max(0, q.ownMax - q.ownUsed) : q.ownerRemaining}
          max={hasVisitorKey ? q.ownMax : q.ownerMax}
          usedLabel={
            hasVisitorKey ? `Used ${q.ownUsed} on your key` : `Used ${q.ownerUsed} free questions`
          }
          hint="Resets at midnight UTC — not on refresh"
          warn={ownerWarn}
        />

        <Meter
          label="Search Precision Boosts"
          remaining={Math.max(0, q.rerankMax - q.rerankUsed)}
          max={q.rerankMax}
          usedLabel={`Used ${q.rerankUsed}`}
          hint="Reranks search results for highest citation accuracy"
        />

        <Meter
          label="Uploaded Documents"
          remaining={Math.max(0, q.docsMax - q.docsUsed)}
          max={q.docsMax}
          usedLabel={`${q.pagesUsed} / ${q.pagesMax} pages used`}
          hint="High-precision document table & text extraction"
        />

        <div className="grid grid-cols-1 min-[420px]:grid-cols-2 gap-2 text-[11px]">
          <div className="p-3 rounded-lg border border-border bg-muted/20 space-y-1">
            <div className="flex items-center gap-1.5 font-semibold text-foreground">
              <Clock className="size-3.5 text-muted-foreground" />
              Session Time Remaining
            </div>
            <p className="font-mono text-sm">{formatTtl(ttl)}</p>
            <p className="text-muted-foreground">Uploaded files clear automatically on expiry</p>
          </div>
          <div className="p-3 rounded-lg border border-border bg-muted/20 space-y-1">
            <div className="flex items-center gap-1.5 font-semibold text-foreground">
              <Zap className="size-3.5 text-muted-foreground" />
              Active AI Model
            </div>
            <p className="font-mono text-sm truncate">
              {hasVisitorKey ? 'Custom Key' : usage?.owner_llm_provider || 'Groq'}
            </p>
            <p className="text-muted-foreground truncate">
              {hasVisitorKey ? 'Personal key active' : formatModelDisplayName(usage?.owner_llm_model || defaultModel)}
            </p>
          </div>
        </div>

        <div className="pt-2 border-t border-border space-y-2.5">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Privacy & Transparency
          </h4>
          <ul className="text-xs space-y-1.5 text-muted-foreground">
            <li className="flex items-start gap-2">
              <Shield className="size-3.5 mt-0.5 text-emerald-500 shrink-0" />
              <span>
                <strong>Privacy by Design:</strong> Your uploaded documents are isolated to your private session and automatically deleted when your session expires or when you click delete.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <Zap className="size-3.5 mt-0.5 text-emerald-500 shrink-0" />
              <span>
                <strong>Verified Grounding:</strong> Every answer links to real quotes and page numbers from your documents. If an answer is not in the text, the assistant informs you directly.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <Database className="size-3.5 mt-0.5 text-emerald-500 shrink-0" />
              <span>
                <strong>Accurate Extraction:</strong> Advanced multi-column and table parsing ensures complex balance sheets, financial figures, and disclosures are captured cleanly.
              </span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};
