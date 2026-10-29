import React from 'react';
import { Moon, Sun, Loader2, ArrowRight } from 'lucide-react';
import { Button } from './ui/button';
import { NavItem } from './NavSidebar';
import { TierADemo } from './TierADemo';
import { TierBUpload } from './TierBUpload';
import { LimitsPanel } from './LimitsPanel';
import { UsageInfo, UploadedDoc, LLMConfig, ExampleQuestion } from '../types';
import { IngestProgress } from '../lib/ingestProgress';

interface SectionDetailsProps {
  activeNav: NavItem;
  usage: UsageInfo | null;
  scope: string;
  documents: UploadedDoc[];
  onRequestDelete: () => void;
  onToast: (msg: string, type: 'info' | 'success' | 'warning' | 'error') => void;
  onKeyConfigChange: (cfg: LLMConfig | null) => void;
  onAskExample: (q: string) => void;
  exampleChips?: ExampleQuestion[];
  width?: number | null;
  isDragging?: boolean;
  theme?: 'light' | 'dark';
  onToggleTheme?: () => void;
  onStartIngest: (file: File) => void;
  ingest: IngestProgress | null;
  suggestedQuestions?: string[];
  onGoToUpload?: () => void;
}

export const SectionDetails: React.FC<SectionDetailsProps> = ({
  activeNav,
  usage,
  scope,
  documents,
  onRequestDelete,
  onToast,
  onKeyConfigChange,
  onAskExample,
  exampleChips = [],
  width,
  isDragging,
  theme,
  onToggleTheme,
  onStartIngest,
  ingest,
  suggestedQuestions = [],
  onGoToUpload,
}) => {
  const sectionHeaders: Record<NavItem, { title: string; subtitle: string }> = {
    tier_a: {
      title: 'Pre-Indexed Demo Corpus',
      subtitle: 'Instant queries over Apple Form 10-K filings (FY2023–FY2025)',
    },
    tier_b: {
      title: 'Custom Document Ingestion & BYOK',
      subtitle: 'Upload custom PDFs & optionally connect personal LLM API keys',
    },
    limits: {
      title: 'System Limits & Spend Gates',
      subtitle: 'Real-time session caps, rate limits, and cost controls',
    },
  };

  return (
    <section
      style={width ? { width: `${width}px`, minWidth: '400px' } : { minWidth: '400px' }}
      className={`surface-panel flex flex-col h-full overflow-hidden min-w-[400px] ${
        isDragging ? 'transition-none' : 'transition-[width] duration-200 ease-out'
      } ${width ? 'shrink-0' : 'flex-1 basis-0'}`}
    >
      {/* Details Section Header */}
      <div className="h-16 px-4 border-b border-border surface-header flex items-center justify-between shrink-0">
        <div className="min-w-0 pr-2">
          <h2 className="font-semibold text-sm leading-tight text-foreground truncate">
            {sectionHeaders[activeNav].title}
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
            {sectionHeaders[activeNav].subtitle}
          </p>
        </div>

        {onToggleTheme && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleTheme}
            aria-label="Toggle theme"
            className="size-8 rounded-md text-muted-foreground hover:text-foreground focus:outline-none focus:ring-0 ring-0 shrink-0 cursor-pointer"
            title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
          >
            {theme === 'light' ? <Moon className="size-4" /> : <Sun className="size-4" />}
          </Button>
        )}
      </div>

      {/* Dynamic Content Panel */}
      <div className="p-4 space-y-4 flex-1 overflow-y-auto">
        {ingest && ingest.phase !== 'done' && ingest.phase !== 'error' && activeNav !== 'tier_b' && (
          <button
            type="button"
            onClick={onGoToUpload}
            className="w-full text-left space-y-2 p-3 rounded-lg border border-primary/30 bg-primary/5 hover:bg-primary/10 transition-colors"
          >
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-foreground flex items-center gap-2">
                <Loader2 className="size-3.5 animate-spin text-primary" />
                <span className="truncate">Indexing {ingest.fileName}</span>
              </span>
              <span className="font-mono text-muted-foreground font-bold shrink-0">{ingest.pct}%</span>
            </div>
            <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-primary h-full transition-all duration-300 rounded-full"
                style={{ width: `${ingest.pct}%` }}
              />
            </div>
            <p className="text-[11px] text-muted-foreground flex items-center justify-between gap-2">
              <span className="truncate">{ingest.stage}</span>
              <span className="inline-flex items-center gap-1 text-primary shrink-0">
                View upload
                <ArrowRight className="size-3" />
              </span>
            </p>
          </button>
        )}

        {activeNav === 'tier_a' && (
          <TierADemo onAskExample={onAskExample} exampleChips={exampleChips} />
        )}

        {activeNav === 'tier_b' && (
          <TierBUpload
            documents={documents}
            onRequestDelete={onRequestDelete}
            onToast={onToast}
            onKeyConfigChange={onKeyConfigChange}
            onAskExample={onAskExample}
            onStartIngest={onStartIngest}
            ingest={ingest}
            suggestedQuestions={suggestedQuestions}
          />
        )}

        {activeNav === 'limits' && (
          <LimitsPanel usage={usage} scope={scope} />
        )}
      </div>
    </section>
  );
};
