import React from 'react';
import { Moon, Sun } from 'lucide-react';
import { Button } from './ui/button';
import { NavItem } from './NavSidebar';
import { TierADemo } from './TierADemo';
import { TierBUpload } from './TierBUpload';
import { LimitsPanel } from './LimitsPanel';
import { UsageInfo, UploadedDoc, LLMConfig, ExampleQuestion } from '../types';

interface SectionDetailsProps {
  activeNav: NavItem;
  usage: UsageInfo | null;
  scope: string;
  documents: UploadedDoc[];
  onUploadSuccess: () => void;
  onRequestDelete: () => void;
  onToast: (msg: string, type: 'info' | 'success' | 'warning' | 'error') => void;
  onKeyConfigChange: (cfg: LLMConfig | null) => void;
  onAskExample: (q: string) => void;
  exampleChips?: ExampleQuestion[];
  width?: number | null;
  isDragging?: boolean;
  theme?: 'light' | 'dark';
  onToggleTheme?: () => void;
  onIngestStateChange?: (isIngesting: boolean, docName?: string) => void;
}

export const SectionDetails: React.FC<SectionDetailsProps> = ({
  activeNav,
  usage,
  scope,
  documents,
  onUploadSuccess,
  onRequestDelete,
  onToast,
  onKeyConfigChange,
  onAskExample,
  exampleChips = [],
  width,
  isDragging,
  theme,
  onToggleTheme,
  onIngestStateChange,
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
        {activeNav === 'tier_a' && (
          <TierADemo onAskExample={onAskExample} exampleChips={exampleChips} />
        )}

        {activeNav === 'tier_b' && (
          <TierBUpload
            documents={documents}
            onUploadSuccess={onUploadSuccess}
            onRequestDelete={onRequestDelete}
            onToast={onToast}
            onKeyConfigChange={onKeyConfigChange}
            onAskExample={onAskExample}
            onIngestStateChange={onIngestStateChange}
          />
        )}

        {activeNav === 'limits' && (
          <LimitsPanel usage={usage} scope={scope} />
        )}
      </div>
    </section>
  );
};
