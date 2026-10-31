import React from 'react';
import { Gauge, KeyRound } from 'lucide-react';
import { UsageInfo } from '../types';
import { formatTtl, readUsage, useLiveTtl } from '../lib/quota';

interface AllowanceMeterProps {
  usage: UsageInfo | null;
  hasVisitorKey?: boolean;
  onAddKey?: () => void;
  onOpenLimits?: () => void;
  /** Icon-and-count only. Used in the phone app bar. */
  dense?: boolean;
}

export const AllowanceMeter: React.FC<AllowanceMeterProps> = ({
  usage,
  hasVisitorKey = false,
  onAddKey,
  onOpenLimits,
  dense = false,
}) => {
  const ttl = useLiveTtl(usage);
  const { ownerRemaining, ownerMax, ownerExhausted, ownUsed, ownMax } = readUsage(usage);
  const remaining = hasVisitorKey ? Math.max(0, ownMax - ownUsed) : ownerRemaining;
  const max = hasVisitorKey ? ownMax : ownerMax;
  const usedPct = Math.min(100, Math.round(((max - remaining) / Math.max(1, max)) * 100));
  const showKeyCta = ownerExhausted && !hasVisitorKey;
  const warn = remaining === 0;

  if (!usage) {
    return (
      <div className={`h-8 rounded-full bg-muted/60 animate-pulse ${dense ? 'w-16' : 'w-44'}`} aria-hidden />
    );
  }

  const label = hasVisitorKey
    ? `${remaining} of ${max} questions left on your key, ${formatTtl(ttl)}`
    : `${remaining} of ${max} questions left, ${formatTtl(ttl)}`;

  return (
    <div className="flex items-center gap-2 min-w-0">
      <button
        type="button"
        onClick={onOpenLimits}
        aria-label={label}
        className={`flex items-center gap-2 min-w-0 rounded-full border px-2.5 py-1 text-left transition-colors ${
          warn
            ? 'border-amber-500/35 bg-amber-500/10 hover:bg-amber-500/15'
            : 'border-border bg-card/80 hover:border-primary/40 hover:bg-muted/40'
        }`}
        title="Open limits"
      >
        <Gauge className={`size-3.5 shrink-0 ${warn ? 'text-amber-600' : 'text-primary'}`} />
        <span className="font-mono text-[11px] font-semibold text-foreground whitespace-nowrap">
          {remaining} left
        </span>
        {!dense && (
          <>
            <span className="hidden sm:inline text-[10px] text-muted-foreground font-mono">
              / {max}
            </span>
            <span className="hidden md:inline h-1 w-12 rounded-full bg-muted overflow-hidden">
              <span
                className={`block h-full ${warn || usedPct > 80 ? 'bg-amber-500' : 'bg-primary'}`}
                style={{ width: `${usedPct}%` }}
              />
            </span>
            <span className="hidden lg:inline text-[10px] text-muted-foreground font-mono whitespace-nowrap">
              {formatTtl(ttl)}
            </span>
          </>
        )}
      </button>
      {showKeyCta && onAddKey && (
        <button
          type="button"
          onClick={onAddKey}
          aria-label="Add your LLM key"
          className={`inline-flex items-center justify-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 text-[11px] font-semibold text-amber-700 dark:text-amber-400 hover:bg-amber-500/20 transition-colors shrink-0 ${
            dense ? 'size-10 px-0' : 'px-2 py-1'
          }`}
        >
          <KeyRound className="size-3.5" />
          <span className={dense ? 'sr-only' : ''}>Add your key</span>
        </button>
      )}
    </div>
  );
};
