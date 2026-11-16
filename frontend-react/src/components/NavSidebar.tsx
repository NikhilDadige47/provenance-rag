import React, { useState } from 'react';
import {
  Eye,
  UploadCloud,
  Cpu,
  Gauge,
  ChevronLeft,
  ChevronRight,
  Lock,
} from 'lucide-react';
import logoImg from '../assets/logo.png';

export type NavItem = 'tier_a' | 'tier_b' | 'models' | 'limits';

interface NavSidebarProps {
  activeNav: NavItem;
  onSelectNav: (item: NavItem) => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  isIngesting?: boolean;
  onBrandClick?: () => void;
}

export const NavSidebar: React.FC<NavSidebarProps> = ({
  activeNav,
  onSelectNav,
  isCollapsed: controlledCollapsed,
  onToggleCollapse,
  isIngesting = false,
  onBrandClick,
}) => {
  const [internalCollapsed, setInternalCollapsed] = useState(false);
  const isCollapsed = controlledCollapsed !== undefined ? controlledCollapsed : internalCollapsed;
  const toggleCollapse = onToggleCollapse || (() => setInternalCollapsed(!internalCollapsed));

  const navItems = [
    {
      id: 'tier_a' as NavItem,
      title: 'Sample Reports',
      subtitle: 'Instant answers from Apple filings',
      icon: Eye,
      tag: 'Instant',
    },
    {
      id: 'tier_b' as NavItem,
      title: 'Your Documents',
      subtitle: 'Upload PDFs & ask questions',
      icon: UploadCloud,
      tag: 'Private',
    },
    {
      id: 'models' as NavItem,
      title: 'AI Models',
      subtitle: 'Cloud, local Ollama or personal key',
      icon: Cpu,
      tag: 'Smart',
    },
    {
      id: 'limits' as NavItem,
      title: 'Usage & Limits',
      subtitle: 'Free questions & session timer',
      icon: Gauge,
      tag: 'Quota',
    },
  ];

  return (
    <aside
      className={`hidden lg:flex border-r border-border bg-card bg-gradient-to-b from-primary/[0.07] via-card/95 to-card dark:from-primary/[0.10] dark:via-card/90 dark:to-background/95 flex-col h-full shrink-0 transition-[width] duration-200 ease-out select-none relative backdrop-blur-xs ${
        isCollapsed ? 'lg:w-[72px]' : 'lg:w-56'
      }`}
    >
      {/* Subtle ambient lighting layer for soft depth */}
      <div
        className="absolute inset-0 overflow-hidden bg-[radial-gradient(ellipse_120%_60%_at_50%_0%,rgba(59,130,246,0.06),transparent_70%)] dark:bg-[radial-gradient(ellipse_120%_60%_at_50%_0%,rgba(59,130,246,0.10),transparent_70%)] pointer-events-none"
        aria-hidden="true"
      />

      {/* Brand Header */}
      <div
        className={`h-16 px-3 flex items-center shrink-0 border-b border-border/50 relative z-10 ${
          isCollapsed ? 'justify-center' : 'justify-between'
        }`}
      >
        {!isCollapsed && (
          <button
            type="button"
            onClick={onBrandClick}
            className="flex items-center gap-0.5 overflow-hidden text-left rounded-md hover:opacity-90 transition-opacity"
            title="Back to overview"
          >
            <img
              src={logoImg}
              alt="Provenance RAG"
              className="size-11 rounded-lg object-contain shrink-0"
            />
            <div className="min-w-0">
              <span
                className="font-bold font-poppins tracking-tight text-base sm:text-[17px] text-foreground truncate block leading-snug"
                style={{ fontFamily: "'Poppins', sans-serif", fontWeight: 700 }}
              >
                Provenance RAG
              </span>
            </div>
          </button>
        )}

        {isCollapsed && (
          <button type="button" onClick={onBrandClick} title="Back to overview">
            <img
              src={logoImg}
              alt="Provenance RAG"
              className="size-12 rounded-lg object-contain shrink-0"
            />
          </button>
        )}
      </div>

      {/* Edge Toggle Handle attached to the vertical centre of the right side edge */}
      <button
        type="button"
        id="sidebar-edge-toggle"
        data-testid="sidebar-edge-toggle"
        onClick={() => toggleCollapse()}
        className="absolute top-1/2 -translate-y-1/2 -right-3 z-40 size-6 rounded-full bg-card border border-border shadow-sm flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors duration-150 cursor-pointer outline-none focus:outline-none focus-visible:outline-none ring-0 focus:ring-0 active:ring-0 select-none group"
        title={isCollapsed ? 'Expand Navigation Menu' : 'Collapse Navigation Menu'}
        aria-label={isCollapsed ? 'Expand Navigation Menu' : 'Collapse Navigation Menu'}
      >
        {isCollapsed ? (
          <ChevronRight className="size-3.5" />
        ) : (
          <ChevronLeft className="size-3.5" />
        )}
      </button>

      {/* Nav Menu */}
      <div className="flex-1 p-2 space-y-1.5 overflow-y-auto">

        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeNav === item.id;
          const isLocked = item.id === 'tier_a' && isIngesting;

          return (
            <button
              key={item.id}
              onClick={() => onSelectNav(item.id)}
              aria-disabled={isLocked}
              title={
                isLocked
                  ? 'Indexing in progress — Demo Corpus is locked until your document is ready'
                  : `${item.title} — ${item.subtitle}`
              }
              className={`w-full h-10 rounded-lg flex items-center transition-colors duration-150 relative group outline-none focus:outline-none focus-visible:outline-none ring-0 focus:ring-0 ${
                isCollapsed ? 'justify-center px-0' : 'gap-2.5 px-2.5 text-left'
              } ${
                isLocked
                  ? 'text-muted-foreground/50 cursor-not-allowed opacity-60'
                  : isActive
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              }`}
            >
              {isLocked ? (
                <Lock className="size-[19px] shrink-0" strokeWidth={2.25} />
              ) : (
                <Icon className="size-[19px] shrink-0" strokeWidth={2.25} />
              )}
              {!isCollapsed && (
                <span className="min-w-0 flex-1 font-semibold text-xs truncate leading-none">
                  {item.title}
                </span>
              )}
            </button>
          );
        })}
      </div>

    </aside>
  );
};
