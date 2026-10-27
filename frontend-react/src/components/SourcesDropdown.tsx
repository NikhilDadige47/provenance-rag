import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { BookOpen, ChevronDown, FileText, Bookmark } from 'lucide-react';
import { SourceCard } from '../types';

export interface SourcesDropdownProps {
  sources: SourceCard[];
  messageId?: string;
}

/**
 * Calculates relative position and smoothly scrolls the closest scroll container
 * without getting blocked by overflow-hidden ancestors.
 */
export const scrollChatToElement = (el: HTMLElement) => {
  const scrollContainer =
    (el.closest('.overflow-y-auto') as HTMLElement) ||
    (document.querySelector('.overflow-y-auto') as HTMLElement);

  if (scrollContainer) {
    const containerRect = scrollContainer.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    const relativeTop = elRect.top - containerRect.top + scrollContainer.scrollTop;
    scrollContainer.scrollTo({
      top: Math.max(0, relativeTop - 70),
      behavior: 'smooth',
    });
  } else {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
};

export const SourcesDropdown: React.FC<SourcesDropdownProps> = ({ sources, messageId }) => {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [expandedSourceIndices, setExpandedSourceIndices] = useState<Set<number>>(new Set());

  // Listen for citation clicks from within markdown text
  useEffect(() => {
    const handleOpenCitation = (e: Event) => {
      const customEvent = e as CustomEvent<{ citation: string }>;
      const targetCitation = customEvent.detail?.citation?.replace(/[\[\]【】]/g, '').trim();
      if (!targetCitation) return;

      const foundIdx = sources.findIndex(
        (s) => s.citation.replace(/[\[\]【】]/g, '').trim() === targetCitation
      );

      if (foundIdx !== -1) {
        // Open the dropdown and expand this specific source
        setIsDropdownOpen(true);
        setExpandedSourceIndices((prev) => {
          const next = new Set(prev);
          next.add(foundIdx);
          return next;
        });

        // Repeated polling attempt to find the mounted card and scroll to it
        const attemptScroll = (attempt = 0) => {
          const card = document.getElementById(`source-card-${targetCitation}`);
          const btn = document.getElementById(`source-btn-${targetCitation}`);
          const target = card || btn;

          if (target) {
            scrollChatToElement(target);
            target.classList.add('ring-2', 'ring-primary', 'ring-offset-2', 'bg-primary/10');
            setTimeout(() => {
              target.classList.remove('ring-2', 'ring-primary', 'ring-offset-2', 'bg-primary/10');
            }, 2500);
          } else if (attempt < 15) {
            setTimeout(() => attemptScroll(attempt + 1), 50);
          }
        };

        setTimeout(() => attemptScroll(0), 40);
      }
    };

    window.addEventListener('open-source-card', handleOpenCitation);
    return () => window.removeEventListener('open-source-card', handleOpenCitation);
  }, [sources]);

  if (!sources || sources.length === 0) return null;

  const toggleSource = (idx: number, cIndex: string) => {
    setExpandedSourceIndices((prev) => {
      const next = new Set(prev);
      const willOpen = !next.has(idx);
      if (willOpen) {
        next.add(idx);
        setTimeout(() => {
          const card = document.getElementById(`source-card-${cIndex}`);
          if (card) scrollChatToElement(card);
        }, 50);
      } else {
        next.delete(idx);
      }
      return next;
    });
  };

  return (
    <div className="w-full pt-1.5 space-y-2 select-none">
      {/* Sources Dropdown Trigger */}
      <div className="flex items-center">
        <button
          type="button"
          onClick={() => setIsDropdownOpen((prev) => !prev)}
          className="inline-flex items-center gap-1.5 py-1 px-2.5 rounded-lg text-xs font-medium bg-muted/40 hover:bg-muted/80 text-muted-foreground hover:text-foreground border border-border/60 transition-all cursor-pointer select-none group shadow-2xs"
          title={isDropdownOpen ? 'Hide sources' : 'Show sources'}
        >
          <BookOpen className="size-3.5 text-primary/80" />
          <span className="font-semibold tracking-tight">Sources</span>
          <span className="font-mono text-[10px] text-muted-foreground bg-muted/80 px-1.5 py-0.2 rounded-full border border-border/50">
            {sources.length}
          </span>
          <ChevronDown
            className={`size-3.5 text-muted-foreground/80 group-hover:text-foreground transition-transform duration-200 ${
              isDropdownOpen ? 'rotate-180' : ''
            }`}
          />
        </button>
      </div>

      {/* When Dropdown is opened: Source Buttons and their expanded content */}
      <AnimatePresence initial={false}>
        {isDropdownOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className="space-y-2 pt-0.5"
          >
            {/* List of Source Buttons */}
            <div className="flex flex-wrap gap-1.5">
              {sources.map((src, idx) => {
                const cIndex = src.citation.replace(/[\[\]【】]/g, '').trim();
                const isExpanded = expandedSourceIndices.has(idx);

                return (
                  <button
                    key={idx}
                    id={`source-btn-${cIndex}`}
                    type="button"
                    onClick={() => toggleSource(idx, cIndex)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition-all cursor-pointer select-none ${
                      isExpanded
                        ? 'bg-primary/10 border-primary/30 text-primary shadow-xs'
                        : 'bg-muted/30 hover:bg-muted/70 border-border/60 text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <FileText className="size-3 shrink-0 text-blue-600 dark:text-blue-400" />
                    <span
                      className="font-mono font-bold text-[11px] text-blue-600 dark:text-blue-400 !text-blue-600 dark:!text-blue-400"
                      style={{ color: 'var(--citation-blue, #2563eb)' }}
                    >
                      [{cIndex}]
                    </span>
                    <span className="truncate max-w-[160px] sm:max-w-[220px]">
                      {src.title}
                    </span>
                    <span className="text-[10px] font-mono text-muted-foreground">
                      p.{src.page}
                    </span>
                    <ChevronDown
                      className={`size-3 transition-transform duration-150 ${
                        isExpanded ? 'rotate-180 text-primary' : 'text-muted-foreground/70'
                      }`}
                    />
                  </button>
                );
              })}
            </div>

            {/* Expanded Content for Clicked Sources */}
            <div className="space-y-2 pt-1">
              {sources.map((src, idx) => {
                const cIndex = src.citation.replace(/[\[\]【】]/g, '').trim();
                const isExpanded = expandedSourceIndices.has(idx);

                if (!isExpanded) return null;

                return (
                  <motion.div
                    key={idx}
                    id={`source-card-${cIndex}`}
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.18 }}
                    className="p-3 rounded-xl border border-border/80 bg-card/60 shadow-xs space-y-2 text-xs"
                  >
                    {/* Header: Title, Citation, Page */}
                    <div className="flex items-center justify-between gap-2 font-medium">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span
                          className="font-mono font-bold bg-blue-500/10 px-1.5 py-0.5 rounded text-[11px] border border-blue-500/20 shrink-0 text-blue-600 dark:text-blue-400"
                          style={{ color: 'var(--citation-blue, #2563eb)' }}
                        >
                          [{cIndex}]
                        </span>
                        <span className="text-foreground font-semibold truncate tracking-tight text-[12.5px]">
                          {src.title}
                        </span>
                      </div>
                      <span className="text-muted-foreground font-mono text-[10.5px] bg-muted/60 px-2 py-0.5 rounded-full border border-border/50 shrink-0">
                        Page {src.page}
                      </span>
                    </div>

                    {/* Breadcrumb section trail if available */}
                    {src.breadcrumb && (
                      <div className="flex items-center gap-1 text-[11px] text-muted-foreground font-mono bg-muted/30 px-2 py-1 rounded-md border border-border/40">
                        <Bookmark className="size-3 text-primary/70 shrink-0" />
                        <span className="truncate">{src.breadcrumb}</span>
                      </div>
                    )}

                    {/* Verbatim Snippet Quote */}
                    <div className="pl-3 py-1.5 border-l-2 border-primary/60 bg-muted/20 rounded-r-md">
                      <p className="text-muted-foreground italic text-[11.5px] leading-relaxed select-text">
                        "{src.snippet}"
                      </p>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
