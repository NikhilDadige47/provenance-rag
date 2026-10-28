import React from 'react';
import { Shield, Moon, Sun, Database, Eye, UploadCloud, Key, X } from 'lucide-react';
import { Button } from './ui/button';
import logoImg from '../assets/logo.png';
import { AllowanceMeter } from './AllowanceMeter';
import { TierADemo } from './TierADemo';
import { TierBUpload } from './TierBUpload';
import { TierCKeys } from './TierCKeys';
import { AccessTier, UsageInfo, UploadedDoc, LLMConfig } from '../types';

interface SidebarProps {
  currentTier: AccessTier;
  onSelectTier: (tier: AccessTier) => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  documentCount: number;
  usage: UsageInfo | null;
  documents: UploadedDoc[];
  onUploadSuccess: () => void;
  onRequestDelete: () => void;
  onToast: (msg: string, type: 'info' | 'success' | 'warning' | 'error') => void;
  onKeyConfigChange: (cfg: LLMConfig | null) => void;
  onAskExample: (q: string) => void;
  isOpenMobile?: boolean;
  onCloseMobile?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTier,
  onSelectTier,
  theme,
  onToggleTheme,
  documentCount,
  usage,
  documents,
  onUploadSuccess,
  onRequestDelete,
  onToast,
  onKeyConfigChange,
  onAskExample,
  isOpenMobile = false,
  onCloseMobile,
}) => {
  const tabs = [
    {
      id: 'tier_a' as AccessTier,
      title: 'Demo Corpus',
      desc: 'Free queries over pre-indexed corpus',
      icon: Eye,
      badge: 'Free Instant',
      badgeColor: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20',
    },
    {
      id: 'tier_b' as AccessTier,
      title: 'Upload Documents',
      desc: 'Direct PDF upload with isolated session scope & optional BYOK',
      icon: UploadCloud,
      badge: 'Session',
      badgeColor: 'bg-blue-500/10 text-blue-600 border-blue-500/20',
    },
  ];

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpenMobile && (
        <div
          onClick={onCloseMobile}
          className="fixed inset-0 bg-background/80 backdrop-blur-sm z-40 lg:hidden"
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-[360px] xl:w-[400px] border-r border-border bg-card/95 backdrop-blur flex flex-col h-screen transition-transform duration-300 ease-in-out lg:static lg:translate-x-0 ${
          isOpenMobile ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Sidebar Header: Brand & Theme Toggle */}
        <div className="p-4 border-b border-border flex items-center justify-between shrink-0">
          <div className="flex items-center gap-0.5">
            <img
              src={logoImg}
              alt="Provenance RAG"
              className="size-11 rounded-lg object-contain shrink-0"
            />
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-bold font-poppins tracking-tight text-base sm:text-[17px]" style={{ fontFamily: "'Poppins', sans-serif", fontWeight: 700 }}>Provenance RAG</span>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-muted text-muted-foreground border border-border">
                  v2.1
                </span>
              </div>
              <p className="text-[11px] text-muted-foreground truncate">
                Hybrid Retrieval Architecture
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <Button
              variant="outline"
              size="icon"
              onClick={onToggleTheme}
              aria-label="Toggle theme"
              className="size-8 rounded-md"
            >
              {theme === 'light' ? <Moon className="size-3.5" /> : <Sun className="size-3.5" />}
            </Button>
            {onCloseMobile && (
              <Button
                variant="ghost"
                size="icon"
                onClick={onCloseMobile}
                className="size-8 lg:hidden"
              >
                <X className="size-4" />
              </Button>
            )}
          </div>
        </div>

        {/* Scrollable Middle: Tier Navigation & Tier Action Workspace */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Section: Access Tiers */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-[11px] font-semibold text-muted-foreground uppercase tracking-wider px-1">
              <span>Workspaces & Ingestion</span>
              <span className="flex items-center gap-1 font-mono lowercase">
                <Database className="size-3" />
                {documentCount} docs
              </span>
            </div>

            {/* Vertical Tier Navigation Buttons */}
            <div className="flex flex-col gap-2">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = currentTier === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => onSelectTier(tab.id)}
                    className={`flex items-start gap-3 p-3 rounded-lg border text-left transition-all relative overflow-hidden group ${
                      isActive
                        ? 'bg-card border-primary ring-1 ring-primary shadow-sm'
                        : 'bg-card/40 border-border hover:bg-card hover:border-muted-foreground/30'
                    }`}
                  >
                    <div
                      className={`size-7 rounded-md flex items-center justify-center shrink-0 mt-0.5 transition-colors ${
                        isActive
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted text-muted-foreground group-hover:text-foreground'
                      }`}
                    >
                      <Icon className="size-3.5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-1">
                        <span className="font-semibold text-xs leading-snug">{tab.title}</span>
                        <span className={`text-[9.5px] font-mono px-1.5 py-0.2 rounded border ${tab.badgeColor}`}>
                          {tab.badge}
                        </span>
                      </div>
                      <div className="text-[11px] text-muted-foreground truncate mt-0.5">
                        {tab.desc}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Section: Active Tier Workspace (Tier A, Tier B, Tier C) */}
          <div className="pt-2 border-t border-border">
            {currentTier === 'tier_a' && (
              <TierADemo onAskExample={onAskExample} />
            )}

            {currentTier === 'tier_b' && (
              <TierBUpload
                documents={documents}
                onUploadSuccess={onUploadSuccess}
                onRequestDelete={onRequestDelete}
                onToast={onToast}
              />
            )}
          </div>
        </div>

        {/* Sidebar Footer: Pinned Allowance Meter */}
        <div className="p-3.5 border-t border-border bg-card/90 shrink-0">
          <AllowanceMeter usage={usage} />
        </div>
      </aside>
    </>
  );
};
