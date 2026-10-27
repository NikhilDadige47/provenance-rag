import React, { useEffect } from 'react';
import { CheckCircle2, AlertTriangle, Info, X } from 'lucide-react';

export interface ToastMessage {
  id: string;
  message: string;
  type: 'info' | 'success' | 'warning' | 'error';
}

interface ToastProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export const Toast: React.FC<ToastProps> = ({ toasts, onDismiss }) => {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
      {toasts.map((t) => {
        const icons = {
          info: <Info className="size-4 text-blue-500 shrink-0" />,
          success: <CheckCircle2 className="size-4 text-emerald-500 shrink-0" />,
          warning: <AlertTriangle className="size-4 text-amber-500 shrink-0" />,
          error: <AlertTriangle className="size-4 text-destructive shrink-0" />,
        };

        const borders = {
          info: 'border-blue-500/20 bg-card text-foreground',
          success: 'border-emerald-500/20 bg-card text-foreground',
          warning: 'border-amber-500/20 bg-card text-foreground',
          error: 'border-destructive/20 bg-card text-foreground',
        };

        return (
          <div
            key={t.id}
            className={`pointer-events-auto p-3.5 rounded-lg border shadow-lg flex items-center justify-between gap-3 text-xs animate-in slide-in-from-bottom-2 duration-200 ${borders[t.type]}`}
          >
            <div className="flex items-center gap-2">
              {icons[t.type]}
              <span>{t.message}</span>
            </div>
            <button
              onClick={() => onDismiss(t.id)}
              className="text-muted-foreground hover:text-foreground p-0.5"
            >
              <X className="size-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
