import React from 'react';
import { Eye, UploadCloud, Key } from 'lucide-react';
import { AccessTier } from '../types';

interface TierSelectorProps {
  currentTier: AccessTier;
  onSelectTier: (tier: AccessTier) => void;
}

export const TierSelector: React.FC<TierSelectorProps> = ({ currentTier, onSelectTier }) => {
  const tabs = [
    {
      id: 'tier_a' as AccessTier,
      title: 'Demo Corpus',
      desc: 'Free queries over pre-indexed corpus',
      icon: Eye,
    },
    {
      id: 'tier_b' as AccessTier,
      title: 'Upload Documents',
      desc: 'Direct PDF upload with isolated session scope & optional BYOK',
      icon: UploadCloud,
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = currentTier === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onSelectTier(tab.id)}
            className={`flex items-start gap-3 p-3.5 rounded-lg border text-left transition-all relative overflow-hidden ${
              isActive
                ? 'bg-card border-primary ring-1 ring-primary shadow-sm'
                : 'bg-card/40 border-border hover:bg-card hover:border-muted-foreground/30'
            }`}
          >
            <div
              className={`size-8 rounded-md flex items-center justify-center shrink-0 mt-0.5 ${
                isActive ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
              }`}
            >
              <Icon className="size-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-sm leading-snug">{tab.title}</div>
              <div className="text-xs text-muted-foreground truncate mt-0.5">{tab.desc}</div>
            </div>
          </button>
        );
      })}
    </div>
  );
};
