import React, { lazy, Suspense, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'motion/react';
import { ExternalLink, FileText, Loader2, Maximize2, Minimize2, X } from 'lucide-react';
import { useCompactLayout } from '../lib/useCompactLayout';

const PdfCanvasViewer = lazy(() =>
  import('./PdfCanvasViewer').then((mod) => ({ default: mod.PdfCanvasViewer }))
);

export interface DemoDocData {
  title: string;
  filename: string;
  desc: string;
  pages: number;
  chunks: number;
  category: string;
  pdfUrl: string;
}

interface DocViewerModalProps {
  doc: DemoDocData | null;
  onClose: () => void;
}

function isBlobUrl(url: string): boolean {
  return url.startsWith('blob:');
}

export const DocViewerModal: React.FC<DocViewerModalProps> = ({ doc, onClose }) => {
  const compact = useCompactLayout();
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    setExpanded(false);
  }, [doc?.filename]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (expanded) {
        setExpanded(false);
        return;
      }
      onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [expanded, onClose]);

  useEffect(() => {
    if (!doc) {
      setObjectUrl(null);
      setError(null);
      setLoading(false);
      return;
    }

    document.body.style.overflow = 'hidden';

    if (isBlobUrl(doc.pdfUrl)) {
      setObjectUrl(doc.pdfUrl);
      setError(null);
      setLoading(false);
      return () => {
        document.body.style.overflow = '';
      };
    }

    const controller = new AbortController();
    let created: string | null = null;
    setLoading(true);
    setError(null);
    setObjectUrl(null);

    (async () => {
      try {
        const res = await fetch(doc.pdfUrl, {
          credentials: 'include',
          signal: controller.signal,
        });
        if (!res.ok) {
          throw new Error(`Could not load PDF (${res.status})`);
        }
        const blob = await res.blob();
        if (blob.size < 5) {
          throw new Error('The PDF file was empty.');
        }
        created = URL.createObjectURL(blob);
        setObjectUrl(created);
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : 'Could not load this PDF.');
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();

    return () => {
      controller.abort();
      if (created) URL.revokeObjectURL(created);
      document.body.style.overflow = '';
    };
  }, [doc]);

  return createPortal(
    <AnimatePresence>
      {doc && (
        <div
          className="fixed inset-0 z-[200] flex items-stretch justify-center p-0 sm:items-center sm:p-6"
          role="dialog"
          aria-modal="true"
          aria-label={doc.title}
        >
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0 bg-black/70 backdrop-blur-[2px]"
          />

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            onClick={(e) => e.stopPropagation()}
            className={`relative z-10 flex min-h-0 w-full flex-col overflow-hidden bg-card border border-border shadow-2xl ${
              expanded
                ? 'h-full max-w-none'
                : 'h-full sm:h-[90vh] sm:max-w-4xl sm:rounded-xl'
            }`}
          >
            <header className="flex min-h-12 shrink-0 items-center justify-between gap-2 border-b border-border surface-header px-3 pt-[max(0.5rem,env(safe-area-inset-top))] pb-2 sm:px-4 sm:py-2">
              <div className="flex items-center gap-2 min-w-0">
                <FileText className="size-4 text-primary shrink-0" />
                <div className="min-w-0">
                  <h2 className="font-semibold text-sm text-foreground truncate">{doc.title}</h2>
                  <p className="text-[11px] text-muted-foreground truncate">
                    {doc.filename}
                    {doc.pages ? ` · ${doc.pages} pages` : ''}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {objectUrl && (
                  <a
                    href={objectUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex size-10 items-center justify-center rounded-full border border-border bg-background text-foreground sm:hidden"
                    title="Open PDF"
                    aria-label="Open PDF"
                  >
                    <ExternalLink className="size-4" />
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => setExpanded((v) => !v)}
                  className="hidden sm:flex size-8 rounded-full bg-background hover:bg-muted border border-border text-foreground items-center justify-center transition-colors cursor-pointer"
                  title={expanded ? 'Exit full screen' : 'Expand'}
                  aria-label={expanded ? 'Exit full screen' : 'Expand preview'}
                >
                  {expanded ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="size-10 sm:size-8 rounded-full bg-background hover:bg-muted border border-border text-foreground flex items-center justify-center transition-colors cursor-pointer"
                  title="Close"
                  aria-label="Close preview"
                >
                  <X className="size-4" />
                </button>
              </div>
            </header>

            <div className="relative min-h-0 flex-1 bg-muted/20">
              {loading && (
                <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 text-muted-foreground">
                  <Loader2 className="size-6 animate-spin text-primary" />
                  <p className="text-sm">Loading filing…</p>
                </div>
              )}
              {error && (
                <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 px-6 text-center">
                  <FileText className="size-8 text-muted-foreground" />
                  <p className="font-medium text-sm text-foreground">PDF preview unavailable</p>
                  <p className="text-xs text-muted-foreground max-w-sm">{error}</p>
                </div>
              )}
              {objectUrl && !error && !loading && (
                compact ? (
                  <Suspense
                    fallback={
                      <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-muted-foreground">
                        <Loader2 className="size-6 animate-spin text-primary" />
                        <p className="text-sm">Preparing preview…</p>
                      </div>
                    }
                  >
                    <PdfCanvasViewer url={objectUrl} />
                  </Suspense>
                ) : (
                  <iframe
                    src={`${objectUrl}#toolbar=1&navpanes=0&view=FitH`}
                    title={doc.title}
                    className="absolute inset-0 h-full w-full border-none bg-white"
                  />
                )
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
};
