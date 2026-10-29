import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { FileText, X } from 'lucide-react';
import { Button } from './ui/button';

export const TERMS_STORAGE_KEY = 'provenance_terms_v1';

export function readTermsAccepted(): boolean {
  try {
    return sessionStorage.getItem(TERMS_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

export function persistTermsAccepted(accepted: boolean) {
  try {
    sessionStorage.setItem(TERMS_STORAGE_KEY, accepted ? '1' : '0');
  } catch {
    /* private mode */
  }
}

const TERMS = [
  {
    title: 'Right to upload',
    body: 'You must have the right to submit this file. Do not upload other people’s confidential documents without permission.',
  },
  {
    title: 'Where text goes',
    body: 'Parsed text is sent to the parser you choose, then to Cohere for embeddings and rerank, and to the active LLM (owner key or yours).',
  },
  {
    title: 'Retention',
    body: 'Uploads stay in this isolated session. Vectors, SQL, and cached parses are wiped on the two-hour TTL, tab close, or delete.',
  },
  {
    title: 'Keys',
    body: 'Visitor parser and LLM keys transit this host in memory for that job or request only. They are never written to disk, logs, or the database.',
  },
  {
    title: 'Caps',
    body: 'Owner-funded questions, documents, pages, and daily IP limits apply. When they hit, paste your own LLM key or wait for the daily reset.',
  },
];

interface TermsModalProps {
  open: boolean;
  onClose: () => void;
  onAccept: () => void;
}

export const TermsModal: React.FC<TermsModalProps> = ({ open, onClose, onAccept }) => {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[220] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="terms-title"
    >
      <button
        type="button"
        className="absolute inset-0 bg-black/70 backdrop-blur-[2px]"
        aria-label="Close terms"
        onClick={onClose}
      />
      <div className="relative z-10 w-full max-w-md rounded-xl border border-border bg-card shadow-2xl">
        <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="flex items-start gap-2.5 min-w-0">
            <FileText className="mt-0.5 size-4 text-primary shrink-0" />
            <div>
              <h2 id="terms-title" className="text-sm font-semibold text-foreground">
                Upload terms
              </h2>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                Accept these before you upload a PDF. Your files never join the demo corpus.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="size-8 rounded-full border border-border bg-background hover:bg-muted flex items-center justify-center shrink-0"
            aria-label="Close"
          >
            <X className="size-4" />
          </button>
        </header>
        <ol className="max-h-[min(52vh,22rem)] overflow-y-auto px-5 py-3 space-y-3">
          {TERMS.map((item, i) => (
            <li key={item.title} className="flex gap-3 text-xs leading-relaxed">
              <span className="font-mono text-[10px] text-primary pt-0.5">{i + 1}</span>
              <div>
                <p className="font-semibold text-foreground">{item.title}</p>
                <p className="mt-0.5 text-muted-foreground">{item.body}</p>
              </div>
            </li>
          ))}
        </ol>
        <footer className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
          <Button
            size="sm"
            onClick={() => {
              persistTermsAccepted(true);
              onAccept();
            }}
          >
            I accept
          </Button>
        </footer>
      </div>
    </div>,
    document.body
  );
};
