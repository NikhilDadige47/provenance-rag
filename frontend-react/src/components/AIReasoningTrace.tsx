import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Check, AlertTriangle, Minus, Loader2, ChevronDown } from 'lucide-react';
import { ShimmerText } from './ui/components-ai-thought-chain-utils/text-shimmer';
import { PipelineStageTrace } from '../types';

export interface AIReasoningTraceProps {
  isLoading?: boolean;
  activeStageIdx?: number;
  timings_ms?: {
    total_ms?: number;
    safety_ms?: number;
    rewrite_ms?: number;
    retrieval_ms?: number;
    rerank_ms?: number;
    expansion_ms?: number;
    generation_ms?: number;
    citation_ms?: number;
  };
  sourcesCount?: number;
  isGrounded?: boolean;
  rerankFallback?: boolean;
  isFound?: boolean;
  modelUsed?: string;
  scope?: string;
  defaultExpanded?: boolean;
  traceStages?: PipelineStageTrace[];
}

interface FallbackStep {
  id: string;
  title: string;
  loadingLabel: string;
  detail: string;
}

const DEFAULT_LOADING_STEPS: FallbackStep[] = [
  {
    id: 'safety',
    title: 'Input Safety & Scope',
    loadingLabel: 'Screening query & scope...',
    detail: 'Query passed safety filter',
  },
  {
    id: 'rewrite',
    title: 'Query Processing',
    loadingLabel: 'Analyzing context for rewrites...',
    detail: 'De-referenced query intent',
  },
  {
    id: 'retrieval',
    title: 'Hybrid Retrieval',
    loadingLabel: 'Searching vector & BM25 indices...',
    detail: 'Retrieved candidate chunks',
  },
  {
    id: 'rerank',
    title: 'Rerank & Relevance Gate',
    loadingLabel: 'Evaluating cross-encoder relevance...',
    detail: 'Relevance threshold verified',
  },
  {
    id: 'expansion',
    title: 'Context Expansion',
    loadingLabel: 'Compiling parent document context...',
    detail: 'Expanded parent passages',
  },
  {
    id: 'generation',
    title: 'Answer Generation',
    loadingLabel: 'Synthesizing grounded answer...',
    detail: 'Streamed response with citations',
  },
];

export const AIReasoningTrace: React.FC<AIReasoningTraceProps> = (props) => {
  const {
    isLoading = false,
    activeStageIdx = 0,
    timings_ms,
    defaultExpanded = false,
    traceStages,
  } = props;

  const [isExpanded, setIsExpanded] = useState<boolean>(defaultExpanded);

  // Calculate total latency
  const totalMs =
    timings_ms?.total_ms ||
    (traceStages && traceStages.reduce((sum, s) => sum + (s.latency_ms || 0), 0)) ||
    Object.values(timings_ms || {}).reduce((a, b) => a + (b || 0), 0) ||
    350;

  const formatThoughtDuration = (ms: number): string => {
    if (!ms || ms <= 0) return 'Thought for <1s';
    const totalSeconds = Math.round(ms / 1000);
    if (totalSeconds < 1) return `Thought for ${(ms / 1000).toFixed(1)}s`;
    return `Thought for ${totalSeconds}s`;
  };

  // When backend supplies actual trace stages, render them directly!
  const hasBackendStages = Boolean(traceStages && traceStages.length > 0);

  // During loading: progressive steps
  const currentStage = Math.min(activeStageIdx, DEFAULT_LOADING_STEPS.length - 1);
  const currentLoadingStep = DEFAULT_LOADING_STEPS[currentStage];

  return (
    <div className="w-full select-none my-1">
      {/* While loading: Live Thinking row */}
      {isLoading ? (
        <div className="w-full flex items-center py-1 px-0.5 text-left">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-xs font-semibold text-foreground tracking-tight">
              Thinking
            </span>
            <span className="text-muted-foreground/30">•</span>
            <span className="text-xs text-muted-foreground font-normal truncate max-w-[240px] sm:max-w-xs">
              <ShimmerText text={currentLoadingStep?.loadingLabel || 'Analyzing documents...'} />
            </span>
          </div>
        </div>
      ) : (
        /* Completed: 'Thought for -- s' toggle button */
        <div className="flex items-center py-0.5">
          <button
            type="button"
            onClick={() => setIsExpanded((prev) => !prev)}
            className="inline-flex items-center gap-1.5 py-1 px-2 -ml-1 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors cursor-pointer select-none group"
            title={isExpanded ? 'Hide pipeline trace' : 'Show pipeline trace'}
          >
            <span className="font-medium tracking-tight">
              {formatThoughtDuration(totalMs)}
            </span>
            <ChevronDown
              className={`size-3.5 text-muted-foreground/80 group-hover:text-foreground transition-transform duration-200 ${
                isExpanded ? 'rotate-180' : ''
              }`}
            />
          </button>
        </div>
      )}

      {/* Reasoning Process Timeline */}
      <AnimatePresence initial={false}>
        {(isLoading || isExpanded) && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className="overflow-hidden pt-1.5 pl-2"
          >
            <div className="space-y-0.5">
              {/* If we have real backend stages, render them */}
              {hasBackendStages && !isLoading ? (
                traceStages!.map((stage, idx) => {
                  const isLast = idx === traceStages!.length - 1;
                  const isDone = stage.status === 'done';
                  const isFailed = stage.status === 'failed';
                  const isSkipped = stage.status === 'skipped';

                  return (
                    <motion.div
                      key={stage.id || idx}
                      initial={{ opacity: 0, y: -2 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="flex gap-2.5 items-start relative group"
                    >
                      {/* Node Icon */}
                      <div className="flex flex-col items-center shrink-0">
                        <div className="mt-0.5">
                          {isDone ? (
                            <span className="flex size-3.5 items-center justify-center rounded-full bg-emerald-600 dark:bg-emerald-500 text-white shadow-xs">
                              <Check className="size-2.5" strokeWidth={3} />
                            </span>
                          ) : isFailed ? (
                            <span className="flex size-3.5 items-center justify-center rounded-full bg-amber-500 text-white shadow-xs">
                              <AlertTriangle className="size-2" strokeWidth={3} />
                            </span>
                          ) : (
                            <span className="flex size-3.5 items-center justify-center rounded-full bg-muted text-muted-foreground border border-border">
                              <Minus className="size-2" />
                            </span>
                          )}
                        </div>
                        {!isLast && (
                          <span className="w-0.5 min-h-3 flex-1 my-1 rounded-sm bg-border/50" />
                        )}
                      </div>

                      {/* Content */}
                      <div className="flex-1 pb-1.5 min-w-0">
                        <div className="inline-flex items-center gap-1.5 text-xs flex-wrap">
                          <span
                            className={`font-semibold tracking-tight ${
                              isFailed
                                ? 'text-amber-600 dark:text-amber-400'
                                : isSkipped
                                  ? 'text-muted-foreground/60'
                                  : 'text-foreground/90'
                            }`}
                          >
                            {stage.title}
                          </span>
                          {!isSkipped && stage.latency_ms > 0 && (
                            <span className="font-mono text-[10px] text-muted-foreground bg-muted/60 px-1.5 py-0.2 rounded border border-border/40 shrink-0">
                              {stage.latency_ms.toFixed(0)}ms
                            </span>
                          )}
                        </div>

                        {/* Concise single statement */}
                        {stage.details && stage.details.length > 0 && (
                          <div className="mt-0.5 text-[11px] text-muted-foreground leading-tight truncate">
                            {stage.details[0]}
                          </div>
                        )}
                      </div>
                    </motion.div>
                  );
                })
              ) : (
                /* Fallback loading view */
                DEFAULT_LOADING_STEPS.slice(0, isLoading ? currentStage + 1 : DEFAULT_LOADING_STEPS.length).map((step, idx) => {
                  const isStepDone = !isLoading || idx < currentStage;
                  const isStepActive = isLoading && idx === currentStage;
                  const isLast = idx === (isLoading ? currentStage : DEFAULT_LOADING_STEPS.length - 1);

                  return (
                    <motion.div
                      key={step.id}
                      initial={{ opacity: 0, y: -2 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="flex gap-2.5 items-start relative group"
                    >
                      <div className="flex flex-col items-center shrink-0">
                        <div className="mt-0.5">
                          {isStepDone ? (
                            <span className="flex size-3.5 items-center justify-center rounded-full bg-emerald-600 dark:bg-emerald-500 text-white shadow-xs">
                              <Check className="size-2.5" strokeWidth={3} />
                            </span>
                          ) : isStepActive ? (
                            <span className="flex size-3.5 items-center justify-center text-primary shrink-0">
                              <Loader2 className="size-3 animate-spin text-primary" />
                            </span>
                          ) : null}
                        </div>
                        {!isLast && (
                          <span className="w-0.5 min-h-3 flex-1 my-1 rounded-sm bg-border/50" />
                        )}
                      </div>

                      <div className="flex-1 pb-1.5 min-w-0">
                        <div className="inline-flex items-center gap-1.5 text-xs flex-wrap">
                          <span className="font-semibold tracking-tight text-foreground/90">
                            {isStepActive ? <ShimmerText text={step.title} /> : step.title}
                          </span>
                        </div>
                        <div className="mt-0.5 text-[11px] text-muted-foreground leading-tight">
                          {step.detail}
                        </div>
                      </div>
                    </motion.div>
                  );
                })
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
