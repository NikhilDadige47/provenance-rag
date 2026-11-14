import React, { useEffect, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Loader2,
  ZoomIn,
  ZoomOut,
  RefreshCw,
} from 'lucide-react';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

try {
  pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;
} catch {
  pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
}

interface PdfCanvasViewerProps {
  url: string;
}

/**
 * Mobile-first high-performance PDF viewer for demo filings and uploaded documents.
 * Employs pagination and safe width detection to prevent mobile canvas OOM crashes on 60+ page filings.
 */
export const PdfCanvasViewer: React.FC<PdfCanvasViewerProps> = ({ url }) => {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [numPages, setNumPages] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [scale, setScale] = useState<number>(1.0);
  const [width, setWidth] = useState<number>(() => {
    if (typeof window !== 'undefined') {
      return Math.max(280, Math.min(window.innerWidth - 32, 650));
    }
    return 360;
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setNumPages(0);
    setCurrentPage(1);
    setError(null);
  }, [url]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const measure = () => {
      if (el.clientWidth > 100) {
        setWidth(Math.floor(el.clientWidth - 24));
      }
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [url]);

  const handlePrevPage = () => {
    setCurrentPage((prev) => Math.max(1, prev - 1));
  };

  const handleNextPage = () => {
    setCurrentPage((prev) => Math.min(numPages || 1, prev + 1));
  };

  const handleZoomIn = () => {
    setScale((prev) => Math.min(2.0, +(prev + 0.15).toFixed(2)));
  };

  const handleZoomOut = () => {
    setScale((prev) => Math.max(0.7, +(prev - 0.15).toFixed(2)));
  };

  if (error) {
    return (
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center bg-card">
        <p className="text-sm font-semibold text-foreground">Mobile preview unavailable</p>
        <p className="max-w-sm text-xs text-muted-foreground">{error}</p>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium shadow-sm hover:opacity-90"
        >
          <ExternalLink className="size-3.5" />
          Open PDF in Native Viewer
        </a>
      </div>
    );
  }

  return (
    <div className="absolute inset-0 flex flex-col bg-neutral-900 text-white overflow-hidden">
      {/* Mobile Sticky Toolbar */}
      <div className="h-10 px-3 bg-neutral-950/90 border-b border-neutral-800 flex items-center justify-between text-xs shrink-0 z-20">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={currentPage <= 1}
            onClick={handlePrevPage}
            className="size-7 rounded flex items-center justify-center hover:bg-neutral-800 disabled:opacity-30 disabled:pointer-events-none transition-colors"
            title="Previous page"
          >
            <ChevronLeft className="size-4" />
          </button>
          <span className="font-mono text-[11px] px-1 text-neutral-300">
            {numPages > 0 ? `${currentPage} / ${numPages}` : 'Loading...'}
          </span>
          <button
            type="button"
            disabled={numPages > 0 && currentPage >= numPages}
            onClick={handleNextPage}
            className="size-7 rounded flex items-center justify-center hover:bg-neutral-800 disabled:opacity-30 disabled:pointer-events-none transition-colors"
            title="Next page"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={handleZoomOut}
            className="size-7 rounded flex items-center justify-center hover:bg-neutral-800 transition-colors"
            title="Zoom out"
          >
            <ZoomOut className="size-3.5" />
          </button>
          <span className="text-[10px] font-mono text-neutral-400 w-8 text-center">
            {Math.round(scale * 100)}%
          </span>
          <button
            type="button"
            onClick={handleZoomIn}
            className="size-7 rounded flex items-center justify-center hover:bg-neutral-800 transition-colors"
            title="Zoom in"
          >
            <ZoomIn className="size-3.5" />
          </button>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="size-7 ml-1 rounded flex items-center justify-center hover:bg-neutral-800 text-neutral-300 transition-colors"
            title="Open in new tab"
          >
            <ExternalLink className="size-3.5" />
          </a>
        </div>
      </div>

      {/* Canvas Scroll Area */}
      <div
        ref={scrollerRef}
        className="flex-1 min-h-0 overflow-y-auto overscroll-contain flex flex-col items-center justify-start p-2"
      >
        <Document
          key={url}
          file={url}
          onLoadSuccess={(pdf) => setNumPages(pdf.numPages)}
          onLoadError={(err) =>
            setError(err instanceof Error ? err.message : 'Could not render this PDF.')
          }
          loading={
            <div className="flex flex-col items-center justify-center gap-2 py-16 text-neutral-400">
              <Loader2 className="size-6 animate-spin text-primary" />
              <p className="text-xs">Loading filing…</p>
            </div>
          }
          className="flex flex-col items-center"
        >
          {numPages > 0 && width > 0 && (
            <div className="shadow-lg rounded-sm overflow-hidden my-1 bg-white">
              <Page
                key={`${url}-p${currentPage}`}
                pageNumber={currentPage}
                width={Math.floor(width * scale)}
                renderTextLayer={false}
                renderAnnotationLayer={false}
                className="bg-white"
                loading={
                  <div
                    style={{ width: `${Math.floor(width * scale)}px`, height: '400px' }}
                    className="flex items-center justify-center bg-white text-neutral-400"
                  >
                    <Loader2 className="size-5 animate-spin text-primary" />
                  </div>
                }
              />
            </div>
          )}
        </Document>
      </div>
    </div>
  );
};
