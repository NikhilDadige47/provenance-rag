import React from 'react';

interface CopilotLogoProps {
  className?: string;
  size?: number;
}

export const CopilotLogo: React.FC<CopilotLogoProps> = ({ className = 'size-4', size }) => {
  const width = size || 16;
  const height = size || 16;

  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`shrink-0 ${className}`}
      aria-label="Microsoft Copilot"
    >
      <defs>
        <linearGradient id="copilot-gradient-left" x1="2" y1="2" x2="16" y2="20" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#00A4EF" />
          <stop offset="45%" stopColor="#0078D4" />
          <stop offset="100%" stopColor="#7F3FBF" />
        </linearGradient>
        <linearGradient id="copilot-gradient-right" x1="22" y1="6" x2="8" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#FF7A00" />
          <stop offset="35%" stopColor="#FF007A" />
          <stop offset="70%" stopColor="#A855F7" />
          <stop offset="100%" stopColor="#6366F1" />
        </linearGradient>
        <filter id="copilot-soft-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="1" stdDeviation="1.5" floodOpacity="0.25" floodColor="#7F3FBF" />
        </filter>
      </defs>

      {/* Primary Copilot Ribbon Loop (Left side) */}
      <path
        d="M13.8 2.2C10.9 0.7 7.2 1.4 5.2 3.8C2.6 6.9 3.1 11.6 6.3 14.1L10.2 17.2C11.9 18.6 14.4 18.9 16.4 17.8C18.8 16.5 19.6 13.4 18.2 11L15.9 7.3C15.4 6.3 14.7 4.5 13.8 2.2Z"
        fill="url(#copilot-gradient-left)"
      />

      {/* Secondary Copilot Ribbon Loop (Right & Crossing) */}
      <path
        d="M10.2 21.8C13.1 23.3 16.8 22.6 18.8 20.2C21.4 17.1 20.9 12.4 17.7 9.9L13.8 6.8C12.1 5.4 9.6 5.1 7.6 6.2C5.2 7.5 4.4 10.6 5.8 13L8.1 16.7C8.6 17.7 9.3 19.5 10.2 21.8Z"
        fill="url(#copilot-gradient-right)"
        opacity="0.95"
      />

      {/* Central Blend Accent */}
      <circle
        cx="12"
        cy="12"
        r="2.2"
        fill="#FFFFFF"
        fillOpacity="0.35"
        style={{ mixBlendMode: 'overlay' }}
      />
    </svg>
  );
};
