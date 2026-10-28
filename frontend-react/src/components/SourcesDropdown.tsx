import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { BookOpen, ChevronDown, FileText } from 'lucide-react';
import { SourceCard } from '../types';

export interface SourcesDropdownProps {
  sources: SourceCard[];
  messageId?: string;
  activeCitation?: string | null;
  onSelectSource?: (source: SourceCard) => void;
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

const citationIndex = (source: SourceCard): string =>
  source.citation.replace(/[\[\]【】]/g, '').trim();

const sourceLabel = (source: SourceCard): string => {
  const section = source.breadcrumb
    ?.split(/[>/|]/)
    .map((part) => part.replace(/\*+/g, '').trim())
    .filter(Boolean)
    .pop();
  if (section && section.toLowerCase() !== source.title.toLowerCase()) {
    return section;
  }
  return source.title.replace(/\.pdf$/i, '');
};

export const SourcesDropdown: React.FC<SourcesDropdownProps> = ({
  sources,
  activeCitation = null,
  onSelectSource,
}) => {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  useEffect(() => {
    const handleOpenCitation = (e: Event) => {
      const customEvent = e as CustomEvent<{ citation: string }>;
      const targetCitation = customEvent.detail?.citation?.replace(/[\[\]【】]/g, '').trim();
      if (!targetCitation) return;

      const found = sources.find((s) => citationIndex(s) === targetCitation);
      if (!found) return;
      onSelectSource?.(found);
    };

    window.addEventListener('open-source-card', handleOpenCitation);
    return () => window.removeEventListener('open-source-card', handleOpenCitation);
  }, [sources, onSelectSource]);

  if (!sources || sources.length === 0) return null;

  return (
    <div className="w-full pt-1.5 space-y-2 select-none">
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

      <AnimatePresence initial={false}>
        {isDropdownOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className="space-y-2 pt-0.5"
          >
            <div className="flex flex-wrap gap-1.5">
              {sources.map((src, idx) => {
                const cIndex = citationIndex(src);
                const isActive = activeCitation === cIndex;

                return (
                  <button
                    key={idx}
                    id={`source-btn-${cIndex}`}
                    type="button"
                    onClick={() => onSelectSource?.(src)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition-all cursor-pointer select-none ${
                      isActive
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
                    <span className="truncate max-w-[160px] sm:max-w-[220px]">{sourceLabel(src)}</span>
                    {src.page > 1 && (
                      <span className="text-[10px] font-mono text-muted-foreground">p.{src.page}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
