import React from 'react';
import { Eye, Gauge, Lock, Moon, Sun, UploadCloud, type LucideIcon } from 'lucide-react';
import logoImg from '../assets/logo.png';
import { UsageInfo } from '../types';
import { NavItem } from './NavSidebar';
import { AllowanceMeter } from './AllowanceMeter';

export type MobilePane = 'context' | 'chat';

const TABS: {
  id: NavItem;
  label: string;
  icon: LucideIcon;
}[] = [
  { id: 'tier_a', label: 'Demo', icon: Eye },
  { id: 'tier_b', label: 'Upload', icon: UploadCloud },
  { id: 'limits', label: 'Limits', icon: Gauge },
];

interface MobileTopBarProps {
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onBrandClick?: () => void;
  usage: UsageInfo | null;
  hasVisitorKey: boolean;
  onAddKey: () => void;
  onOpenLimits: () => void;
}

/** Compact app bar. Brand returns home; quota stays one tap away. */
export const MobileTopBar: React.FC<MobileTopBarProps> = ({
  theme,
  onToggleTheme,
  onBrandClick,
  usage,
  hasVisitorKey,
  onAddKey,
  onOpenLimits,
}) => {
  return (
    <header className="lg:hidden shrink-0 border-b border-border surface-header pt-[env(safe-area-inset-top)] z-30">
      <div className="flex h-12 items-center gap-2 px-3">
        <button
          type="button"
          onClick={onBrandClick}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-md text-left"
          title="Back to overview"
        >
          <img src={logoImg} alt="" className="size-8 shrink-0 rounded-lg object-contain" />
          <span
            className="truncate text-sm font-bold tracking-tight"
            style={{ fontFamily: "'Poppins', sans-serif" }}
          >
            Provenance
          </span>
        </button>

        <AllowanceMeter
          usage={usage}
          hasVisitorKey={hasVisitorKey}
          onAddKey={onAddKey}
          onOpenLimits={onOpenLimits}
          dense
        />

        <button
          type="button"
          onClick={onToggleTheme}
          aria-label={theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme'}
          className="flex size-10 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          {theme === 'light' ? <Moon className="size-4" /> : <Sun className="size-4" />}
        </button>
      </div>
    </header>
  );
};

interface MobilePaneSwitchProps {
  activeNav: NavItem;
  pane: MobilePane;
  onChange: (pane: MobilePane) => void;
}

/** Two jobs, one screen: the section's setup, or the conversation. */
export const MobilePaneSwitch: React.FC<MobilePaneSwitchProps> = ({
  activeNav,
  pane,
  onChange,
}) => {
  const contextLabel = activeNav === 'tier_b' ? 'Document' : 'Questions';

  return (
    <div className="lg:hidden shrink-0 border-b border-border surface-header px-3 py-2">
      <div
        role="tablist"
        aria-label="Workspace view"
        className="grid grid-cols-2 gap-1 rounded-xl bg-muted/80 p-1"
      >
        <PaneTab
          selected={pane === 'context'}
          onClick={() => onChange('context')}
          label={contextLabel}
        />
        <PaneTab selected={pane === 'chat'} onClick={() => onChange('chat')} label="Chat" />
      </div>
    </div>
  );
};

function PaneTab({
  selected,
  onClick,
  label,
}: {
  selected: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      onClick={onClick}
      className={`h-9 rounded-lg text-[13px] font-semibold transition-colors ${
        selected
          ? 'bg-card text-foreground shadow-sm'
          : 'text-muted-foreground hover:text-foreground'
      }`}
    >
      {label}
    </button>
  );
}

interface MobileTabBarProps {
  activeNav: NavItem;
  onSelectNav: (item: NavItem) => void;
  isIngesting?: boolean;
}

/** Thumb-zone navigation. Replaces the desktop sidebar below 1024px. */
export const MobileTabBar: React.FC<MobileTabBarProps> = ({
  activeNav,
  onSelectNav,
  isIngesting = false,
}) => {
  return (
    <nav
      className="lg:hidden shrink-0 border-t border-border surface-header pb-[env(safe-area-inset-bottom)] z-30"
      aria-label="Workspace"
    >
      <div className="grid grid-cols-3">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeNav === tab.id;
          const isLocked = tab.id === 'tier_a' && isIngesting;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onSelectNav(tab.id)}
              aria-current={isActive ? 'page' : undefined}
              aria-disabled={isLocked}
              className={`flex h-14 flex-col items-center justify-center gap-0.5 ${
                isLocked ? 'opacity-50' : isActive ? 'text-primary' : 'text-muted-foreground'
              }`}
            >
              <span
                className={`relative flex size-8 items-center justify-center rounded-lg ${
                  isActive && !isLocked ? 'bg-primary text-primary-foreground' : ''
                }`}
              >
                {isLocked ? (
                  <Lock className="size-[18px]" strokeWidth={2.25} />
                ) : (
                  <Icon className="size-[18px]" strokeWidth={2.25} />
                )}
                {tab.id === 'tier_b' && isIngesting && (
                  <span className="absolute -right-0.5 -top-0.5 size-1.5 rounded-full bg-primary" />
                )}
              </span>
              <span className={`text-[10px] leading-none ${isActive ? 'font-semibold' : 'font-medium'}`}>
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
