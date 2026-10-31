import React, { useCallback, useEffect, useRef, useState } from 'react';
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy, type RenderTask } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

GlobalWorkerOptions.workerSrc = workerUrl;

interface PdfCanvasViewerProps {
  url: string;
}

/**
 * Draws the PDF onto canvases. Phone browsers leave an iframe PDF blank,
 * so the filing has to be painted by the page itself.
 */
export const PdfCanvasViewer: React.FC<PdfCanvasViewerProps> = ({ url }) => {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let loadingTask: ReturnType<typeof getDocument> | null = null;
    setPdf(null);
    setPageCount(0);
    setError(null);

    (async () => {
      try {
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`Could not load PDF (${response.status})`);
        }
        const data = new Uint8Array(await response.arrayBuffer());
        if (cancelled) return;
        loadingTask = getDocument({ data });
        const doc = await loadingTask.promise;
        if (cancelled) {
          await loadingTask.destroy();
          return;
        }
        setPdf(doc);
        setPageCount(doc.numPages);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Could not render this PDF.');
      }
    })();

    return () => {
      cancelled = true;
      loadingTask?.destroy();
    };
  }, [url]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const measure = () => setWidth(Math.max(0, Math.floor(el.clientWidth - 16)));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [pdf]);

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
      data-pdf-scroll="true"
      className="absolute inset-0 overflow-y-auto overscroll-contain bg-neutral-800"
    >
      {!pdf || width < 8 ? (
        <p className="px-4 py-8 text-center text-sm text-neutral-300">Loading pages…</p>
      ) : (
        <div className="mx-auto flex w-full flex-col gap-2 px-2 py-2">
          {Array.from({ length: pageCount }, (_, index) => (
            <PdfPage
              key={`${url}-${index + 1}`}
              pdf={pdf}
              pageNumber={index + 1}
              width={width}
            />
          ))}
        </div>
      )}
    </div>
  );
};

function PdfPage({
  pdf,
  pageNumber,
  width,
}: {
  pdf: PDFDocumentProxy;
  pageNumber: number;
  width: number;
}) {
  const holderRef = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(pageNumber === 1);
  const [ratio, setRatio] = useState(11 / 8.5);

  const rememberRatio = useCallback((next: number) => {
    setRatio((current) => (Math.abs(current - next) < 0.01 ? current : next));
  }, []);

  useEffect(() => {
    const node = holderRef.current;
    const root = node?.closest('[data-pdf-scroll]');
    if (!node || !(root instanceof Element)) return;
    const observer = new IntersectionObserver(
      ([entry]) => setInView(entry.isIntersecting),
      { root, rootMargin: '800px 0px' }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={holderRef}
      className="relative mx-auto overflow-hidden bg-white shadow-sm"
      style={{ width, height: Math.max(1, Math.round(width * ratio)) }}
    >
      {inView ? (
        <PdfPageCanvas pdf={pdf} pageNumber={pageNumber} width={width} onRatio={rememberRatio} />
      ) : (
        <span className="absolute inset-x-0 top-3 text-center text-[11px] text-neutral-400">
          Page {pageNumber}
        </span>
      )}
    </div>
  );
}

function PdfPageCanvas({
  pdf,
  pageNumber,
  width,
  onRatio,
}: {
  pdf: PDFDocumentProxy;
  pageNumber: number;
  width: number;
  onRatio: (ratio: number) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || width < 8) return;

    let cancelled = false;
    let renderTask: RenderTask | null = null;

    (async () => {
      try {
        const page = await pdf.getPage(pageNumber);
        if (cancelled) return;
        const base = page.getViewport({ scale: 1 });
        onRatio(base.height / base.width);
        const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
        const viewport = page.getViewport({ scale: (width / base.width) * pixelRatio });
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        const task = page.render({ canvas, viewport });
        renderTask = task;
        await task.promise;
      } catch {
        /* Cancelled when the page leaves the screen or the viewer closes. */
      }
    })();

    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [pdf, pageNumber, width, onRatio]);

  return <canvas ref={canvasRef} className="block h-full w-full" />;
}
