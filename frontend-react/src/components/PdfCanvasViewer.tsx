import React, { useEffect, useRef, useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

interface PdfCanvasViewerProps {
  url: string;
}

/**
 * Phone preview for demo filings and uploaded PDFs.
 * React-PDF paints the pages; mobile browsers leave an iframe PDF blank.
 */
export const PdfCanvasViewer: React.FC<PdfCanvasViewerProps> = ({ url }) => {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [numPages, setNumPages] = useState(0);
  const [width, setWidth] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setNumPages(0);
    setError(null);
  }, [url]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const measure = () => setWidth(Math.max(0, Math.floor(el.clientWidth - 16)));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [url]);

  if (error) {
    return (
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center">
        <p className="text-sm font-medium text-foreground">PDF preview unavailable</p>
        <p className="max-w-sm text-xs text-muted-foreground">{error}</p>
      </div>
    );
  }

  return (
    <div
      ref={scrollerRef}
      className="absolute inset-0 overflow-y-auto overscroll-contain bg-neutral-800"
    >
      <Document
        key={url}
        file={url}
        onLoadSuccess={(pdf) => setNumPages(pdf.numPages)}
        onLoadError={(err) =>
          setError(err instanceof Error ? err.message : 'Could not render this PDF.')
        }
        loading={<p className="px-4 py-8 text-center text-sm text-neutral-300">Loading pages…</p>}
        className="mx-auto flex w-full flex-col items-center gap-2 px-2 py-2"
      >
        {width > 0 &&
          Array.from({ length: numPages }, (_, index) => (
            <Page
              key={`${url}-${index + 1}`}
              pageNumber={index + 1}
              width={width}
              className="overflow-hidden bg-white shadow-sm"
              renderTextLayer
              renderAnnotationLayer
            />
          ))}
      </Document>
    </div>
  );
};
