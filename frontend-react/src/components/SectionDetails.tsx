import React from 'react';
import { Moon, Sun, Loader2, ArrowRight, Cpu } from 'lucide-react';
import { Button } from './ui/button';
import { NavItem } from './NavSidebar';
import { TierADemo } from './TierADemo';
import { TierBUpload } from './TierBUpload';
import { LimitsPanel } from './LimitsPanel';
import { ModelSelector } from './ModelSelector';
import { UsageInfo, UploadedDoc, LLMConfig, ExampleQuestion } from '../types';
import { IngestProgress } from '../lib/ingestProgress';
import { formatDefaultModelLabel } from '../lib/modelUtils';

interface SectionDetailsProps {
  activeNav: NavItem;
  usage: UsageInfo | null;
  defaultModel?: string;
  defaultProvider?: string;
  scope: string;
  documents: UploadedDoc[];
  onRequestDelete: () => void;
  onToast: (msg: string, type: 'info' | 'success' | 'warning' | 'error') => void;
  llmConfig?: LLMConfig | null;
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
  onGoToModels?: () => void;
  hasVisitorKey?: boolean;
  fillWidth?: boolean;
  hideHeader?: boolean;
  concealed?: boolean;
}

export const SectionDetails: React.FC<SectionDetailsProps> = ({
  activeNav,
  usage,
  defaultModel,
  defaultProvider,
  scope,
  documents,
  onRequestDelete,
  onToast,
  llmConfig = null,
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
  onGoToModels,
  hasVisitorKey = false,
  fillWidth = false,
  hideHeader = false,
  concealed = false,
}) => {
  const sectionHeaders: Record<NavItem, { title: string; subtitle: string }> = {
    tier_a: {
      title: 'Sample Financial Reports',
      subtitle: 'Instant answers across Apple annual reports (10-K) with source citations',
    },
    tier_b: {
      title: 'Analyze Your Own Documents',
      subtitle: 'Upload any PDF to search, summarize, and ask questions with verified proof',
    },
    models: {
      title: 'AI Model & Intelligence',
      subtitle: 'Choose which AI answers your questions — works across all your documents',
    },
    limits: {
      title: 'Session Usage & Limits',
      subtitle: 'Track your remaining questions, document page allowance, and active session timer',
    },
  };

  return (
    <section
      style={
        concealed || fillWidth
          ? undefined
          : width
            ? { width: `${width}px`, minWidth: '400px' }
            : { minWidth: '400px' }
      }
      className={
        concealed
          ? 'hidden'
          : `surface-panel flex min-h-0 min-w-0 flex-col overflow-hidden ${
              fillWidth
                ? 'h-full w-full max-w-full flex-1'
                : `h-full min-w-[400px] ${
                    isDragging ? 'transition-none' : 'transition-[width] duration-200 ease-out'
                  } ${width ? 'shrink-0' : 'flex-1 basis-0'}`
            }`
      }
    >
      {/* Details Section Header */}
      {!hideHeader && (
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
      )}

      {/* Dynamic Content Panel */}
      <div className="p-2.5 sm:p-4 space-y-2.5 sm:space-y-4 flex-1 min-h-0 overflow-y-auto">
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
          <TierADemo
            onAskExample={onAskExample}
            exampleChips={exampleChips}
            llmConfig={llmConfig}
            defaultModel={defaultModel}
            defaultProvider={defaultProvider}
            onKeyConfigChange={onKeyConfigChange}
            onToast={onToast}
            onGoToModels={onGoToModels}
          />
        )}

        {activeNav === 'tier_b' && (
          <TierBUpload
            documents={documents}
            onRequestDelete={onRequestDelete}
            onToast={onToast}
            llmConfig={llmConfig}
            defaultModel={defaultModel}
            defaultProvider={defaultProvider}
            onKeyConfigChange={onKeyConfigChange}
            onAskExample={onAskExample}
            onStartIngest={onStartIngest}
            ingest={ingest}
            suggestedQuestions={suggestedQuestions}
            usage={usage}
            onGoToModels={onGoToModels}
          />
        )}

        {activeNav === 'models' && (
          <div className="p-3.5 sm:p-5 space-y-4 overflow-y-auto">
            <div className="rounded-lg border border-border/80 bg-card/60 p-3 sm:p-4 space-y-1.5 shadow-2xs">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <Cpu className="size-3.5 text-primary" />
                  <span>Active AI Engine</span>
                </span>
                {llmConfig ? (
                  <span className="text-[10.5px] font-mono px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 whitespace-nowrap">
                    {llmConfig.isLocal ? `Local (${llmConfig.model})` : `Custom (${llmConfig.provider.toUpperCase()}: ${llmConfig.model})`}
                  </span>
                ) : (
                  <span className="text-[10.5px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 whitespace-nowrap">
                    {formatDefaultModelLabel(defaultProvider, defaultModel)}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                Your selected AI answers questions across <strong>both sample reports and your uploaded documents</strong> with exact citations.
              </p>
            </div>

            <ModelSelector
              config={llmConfig}
              onChange={onKeyConfigChange}
              onToast={onToast}
              sectionContext="standalone"
              defaultModel={defaultModel}
              defaultProvider={defaultProvider}
            />
          </div>
        )}

        {activeNav === 'limits' && (
          <LimitsPanel
            usage={usage}
            scope={scope}
            hasVisitorKey={hasVisitorKey}
            onAddKey={onGoToUpload}
            defaultModel={defaultModel}
          />
        )}
      </div>
    </section>
  );
};
