import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Bookmark, ChevronLeft, ChevronRight, FileText, X } from 'lucide-react';
import { SourceCard } from '../types';

interface SourceInspectorPanelProps {
  source: SourceCard | null;
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
}

export const SourceInspectorPanel: React.FC<SourceInspectorPanelProps> = ({
  source,
  open,
  onToggle,
  onClose,
}) => {
  const citation = source?.citation.replace(/[\[\]【】]/g, '').trim() ?? '';

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!source) return null;

  return (
    <AnimatePresence>
      {open ? (
        <motion.aside
          key="source-inspector"
          initial={{ x: '100%' }}
          animate={{ x: 0 }}
          exit={{ x: '100%' }}
          transition={{ type: 'tween', duration: 0.22, ease: 'easeInOut' }}
          className="absolute inset-y-0 right-0 z-30 w-[min(28rem,92%)] bg-card border-l border-border shadow-[-12px_0_32px_rgba(0,0,0,0.12)] flex"
          aria-label="Source inspector"
        >
          <button
            type="button"
            onClick={onToggle}
            title="Collapse source panel"
            aria-label="Collapse source panel"
            className="absolute -left-3 top-1/2 -translate-y-1/2 z-40 size-6 rounded-full bg-card border border-border shadow-sm text-muted-foreground hover:text-foreground hover:border-primary/40 flex items-center justify-center cursor-pointer"
          >
            <ChevronLeft className="size-3.5" />
          </button>

          <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
            <div className="h-12 px-3 border-b border-border flex items-center justify-between gap-2 shrink-0">
              <div className="flex items-center gap-1.5 min-w-0">
                <FileText className="size-3.5 text-primary shrink-0" />
                <span className="text-xs font-semibold truncate">Source [{citation}]</span>
              </div>
              <button
                type="button"
                onClick={onClose}
                title="Close"
                aria-label="Close source panel"
                className="size-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted flex items-center justify-center cursor-pointer"
              >
                <X className="size-3.5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <h4 className="text-sm font-semibold leading-snug text-foreground">
                  {source.title}
                </h4>
                <span className="text-[10.5px] font-mono text-muted-foreground bg-muted/60 px-2 py-0.5 rounded-full border border-border/50 shrink-0">
                  Page {source.page}
                </span>
              </div>

              {source.breadcrumb && (
                <div className="flex items-start gap-1 text-[11px] text-muted-foreground font-mono bg-muted/30 px-2 py-1 rounded-md border border-border/40">
                  <Bookmark className="size-3 text-primary/70 shrink-0 mt-0.5" />
                  <span className="break-words">{source.breadcrumb}</span>
                </div>
              )}

              <div
                id={`source-card-${citation}`}
                className="pl-3 py-2.5 border-l-2 border-primary/60 bg-muted/20 rounded-r-md"
              >
                <p className="text-foreground/90 text-[13px] leading-relaxed select-text whitespace-pre-wrap break-words">
                  {source.snippet}
                </p>
              </div>
            </div>
          </div>
        </motion.aside>
      ) : (
        <motion.button
          key="source-inspector-tab"
          type="button"
          initial={{ x: 24, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 24, opacity: 0 }}
          transition={{ duration: 0.16 }}
          onClick={onToggle}
          title="Expand source panel"
          aria-label="Expand source panel"
          className="absolute right-0 top-1/2 -translate-y-1/2 z-30 h-14 w-6 rounded-l-md bg-card border border-r-0 border-border shadow-sm text-muted-foreground hover:text-foreground hover:border-primary/40 flex items-center justify-center cursor-pointer"
        >
          <ChevronRight className="size-3.5" />
        </motion.button>
      )}
    </AnimatePresence>
  );
};
