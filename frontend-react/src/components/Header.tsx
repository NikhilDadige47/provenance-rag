import React from 'react';
import { Shield, Moon, Sun, Database } from 'lucide-react';
import { Button } from './ui/button';
import { AccessTier } from '../types';

interface HeaderProps {
  currentTier: AccessTier;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  documentCount?: number;
}

export const Header: React.FC<HeaderProps> = ({ currentTier, theme, onToggleTheme, documentCount = 3 }) => {
  const tierLabels: Record<AccessTier, { label: string; color: string }> = {
    tier_a: { label: 'Demo Corpus', color: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20' },
    tier_b: { label: 'Custom Uploads', color: 'bg-blue-500/10 text-blue-600 border-blue-500/20' },
    tier_c: { label: 'BYOK Model Keys', color: 'bg-amber-500/10 text-amber-600 border-amber-500/20' },
  };

  return (
    <header className="border-b border-border bg-card/80 backdrop-blur sticky top-0 z-30 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="size-9 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shadow-sm">
            <Shield className="size-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold font-poppins tracking-tight text-base sm:text-lg" style={{ fontFamily: "'Poppins', sans-serif", fontWeight: 700 }}>Provenance RAG</span>
              <span className="hidden sm:inline-block text-[11px] font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground border border-border">
                v2.1 Hybrid
              </span>
            </div>
            <p className="text-xs text-muted-foreground hidden sm:block">
              High-Assurance Hybrid Document Intelligence with Strict Source Attribution
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden md:flex items-center gap-1.5 text-xs text-muted-foreground mr-2 font-mono">
            <Database className="size-3.5" />
            <span>{documentCount} docs indexed</span>
          </div>

          <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${tierLabels[currentTier].color}`}>
            {tierLabels[currentTier].label}
          </span>

          <Button
            variant="outline"
            size="icon"
            onClick={onToggleTheme}
            aria-label="Toggle theme"
            className="size-9 rounded-md"
          >
            {theme === 'light' ? <Moon className="size-4" /> : <Sun className="size-4" />}
          </Button>
        </div>
      </div>
    </header>
  );
};
