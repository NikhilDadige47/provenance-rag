import React, { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  UploadCloud,
  FileText,
  Trash2,
  Loader2,
  Sparkles,
  ArrowRight,
} from 'lucide-react';
import { Button } from './ui/button';
import { UploadedDoc, LLMConfig } from '../types';
import { api } from '../lib/api';
import { IngestProgress } from '../lib/ingestProgress';
import { previewUrlForDoc } from '../lib/uploadedFiles';
import { DocViewerModal, DemoDocData } from './DocViewerModal';
import { TierCKeys } from './TierCKeys';

interface TierBUploadProps {
  documents: UploadedDoc[];
  onRequestDelete: () => void;
  onToast: (msg: string, type: 'info' | 'success' | 'warning' | 'error') => void;
  onKeyConfigChange?: (config: LLMConfig | null) => void;
  onAskExample?: (q: string) => void;
  onStartIngest: (file: File) => void;
  ingest: IngestProgress | null;
  suggestedQuestions?: string[];
}

export const TierBUpload: React.FC<TierBUploadProps> = ({
  documents,
  onRequestDelete,
  onToast,
  onKeyConfigChange,
  onAskExample,
  onStartIngest,
  ingest,
  suggestedQuestions = [],
}) => {
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Optional BYOK State (activates TierCKeys within the upload workflow)
  const [useCustomKey, setUseCustomKey] = useState(false);

  // Document preview popup state
  const [previewDoc, setPreviewDoc] = useState<DemoDocData | null>(null);

  const isUploading = Boolean(ingest && ingest.phase !== 'done' && ingest.phase !== 'error');
  const uploadProgress =
    ingest && ingest.phase !== 'error' ? { stage: ingest.stage, pct: ingest.pct } : null;

  const handleToggleCustomKey = (checked: boolean) => {
    setUseCustomKey(checked);
    if (!checked) {
      api.setVisitorKeys(null);
      onKeyConfigChange?.(null);
      onToast('Switched back to standard owner-backed quota.', 'info');
    }
  };

  const startIngestionForFile = (file: File) => {
    if (isUploading) {
      onToast('A document is already indexing. Please wait until it finishes.', 'warning');
      return;
    }
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      onToast('Only PDF documents are supported.', 'error');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      onToast('File size exceeds the 10MB limit.', 'error');
      return;
    }

    onStartIngest(file);
  };

  const handleOpenDocPreview = (doc: UploadedDoc) => {
    const url = previewUrlForDoc(doc.doc_id, doc.filename);
    if (!url) {
      onToast('PDF preview is available for files uploaded in this browser session.', 'warning');
      return;
    }
    setPreviewDoc({
      title: doc.filename,
      filename: doc.filename,
      desc: `Ingested document: ${doc.chunk_count} chunks, ${doc.page_count || doc.token_count || 0} pages.`,
      pages: doc.page_count || 1,
      chunks: doc.chunk_count,
      category: 'Uploaded PDF',
      pdfUrl: url,
    });
  };

  return (
    <div className="space-y-4">
      {/* Upload Box */}
      <div className="border border-border/80 rounded-lg p-5 surface-inset shadow-sm space-y-4">
        <div className="space-y-0.5">
          <h3 className="font-semibold text-base text-foreground">Document Ingestion</h3>
          <p className="text-xs text-muted-foreground">
            Isolated session · Max 10MB · 30 pages · Owner-paid parse · TTL shred
          </p>
        </div>

        {/* Drag and Drop Zone */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragActive(false);
            if (e.dataTransfer.files?.[0]) {
              startIngestionForFile(e.dataTransfer.files[0]);
            }
          }}
          onClick={() => !isUploading && fileInputRef.current?.click()}
          className={`border border-dashed rounded-lg p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-colors ${
            dragActive
              ? 'border-primary bg-primary/5'
              : 'border-border/80 hover:border-primary/50 hover:bg-muted/20'
          } ${isUploading ? 'opacity-50 pointer-events-none' : ''}`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.[0]) {
                startIngestionForFile(e.target.files[0]);
              }
            }}
          />

          <UploadCloud className="size-6 text-muted-foreground mb-2" />

          <p className="text-xs font-medium text-foreground">
            {ingest?.fileName && isUploading
              ? ingest.fileName
              : 'Click to browse or drop your PDF here'}
          </p>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            PDF files only (max 10MB, up to 30 pages)
          </p>
        </div>

        {/* Live Upload & Indexing Progress */}
        {uploadProgress && (
          <div className="space-y-2 p-3.5 rounded-lg border border-border bg-muted/40">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-foreground flex items-center gap-2">
                <Loader2 className="size-3.5 animate-spin text-primary" />
                <span>{uploadProgress.stage}</span>
              </span>
              <span className="font-mono text-muted-foreground font-bold">{uploadProgress.pct}%</span>
            </div>
            <div className="w-full bg-muted rounded-full h-2 overflow-hidden border border-border/50">
              <div
                className="bg-primary h-full transition-all duration-300 rounded-full"
                style={{ width: `${uploadProgress.pct}%` }}
              />
            </div>
            <p className="text-[11px] text-muted-foreground">
              Indexing keeps running if you open Limits. Demo Corpus stays locked until this finishes.
            </p>
          </div>
        )}

        {/* Optional BYOK API Key Checkbox & Slide-down Zone */}
        <div className="pt-2 border-t border-border/60 space-y-3">
          <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground select-none">
            <input
              type="checkbox"
              checked={useCustomKey}
              onChange={(e) => handleToggleCustomKey(e.target.checked)}
              className="size-3.5 rounded border-border text-primary focus:ring-primary cursor-pointer accent-primary"
            />
            <span>I want to use my own LLM API Key (Optional)</span>
          </label>

          <AnimatePresence>
            {useCustomKey && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.22, ease: 'easeOut' }}
                className="overflow-hidden pt-1"
              >
                <TierCKeys
                  onToast={onToast}
                  onKeyConfigChange={(cfg) => {
                    onKeyConfigChange?.(cfg);
                  }}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Suggested Starter Questions upon Upload */}
      {suggestedQuestions.length > 0 && onAskExample && (
        <div className="p-4 rounded-lg border border-primary/20 bg-primary/5 space-y-2 text-xs">
          <div className="flex items-center gap-1.5 font-semibold text-foreground">
            <Sparkles className="size-3.5 text-primary" />
            <span>Suggested Questions for Uploaded Document:</span>
          </div>
          <div className="flex flex-col gap-1.5">
            {suggestedQuestions.map((q, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => onAskExample(q)}
                className="text-left p-2 rounded-md bg-card hover:bg-muted border border-border/80 hover:border-primary/50 text-muted-foreground hover:text-foreground flex items-center justify-between gap-2 transition-colors cursor-pointer group"
              >
                <span className="line-clamp-1">{q}</span>
                <ArrowRight className="size-3 text-primary opacity-60 group-hover:opacity-100 shrink-0" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Session Ingested Documents List with Click to View PDF Modal */}
      <div className="border border-border rounded-lg p-5 surface-inset shadow-sm space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="size-4 text-primary" />
            <h4 className="font-semibold text-sm">Session Ingested Documents</h4>
          </div>
          <span className="text-xs font-mono text-muted-foreground">
            {documents.length} / 3 maximum
          </span>
        </div>

        {documents.length === 0 ? (
          <div className="text-center py-6 border border-dashed border-border rounded-md text-xs text-muted-foreground">
            No custom documents uploaded yet in this session.
          </div>
        ) : (
          <div className="space-y-2">
            {documents.map((doc) => (
              <div
                key={doc.doc_id}
                className="rounded-md border border-border bg-muted/20 hover:bg-muted/50 hover:border-primary/50 transition-all flex items-center gap-1 text-xs group"
              >
                <button
                  type="button"
                  onClick={() => handleOpenDocPreview(doc)}
                  className="flex-1 min-w-0 p-3 flex items-center justify-between gap-3 text-left cursor-pointer"
                  title={`Click to preview ${doc.filename}`}
                >
                  <span className="flex items-center gap-2.5 min-w-0">
                    <FileText className="size-4 text-primary shrink-0 group-hover:scale-110 transition-transform" />
                    <span className="min-w-0">
                      <span className="font-medium text-foreground truncate group-hover:text-primary transition-colors block">
                        {doc.filename}
                      </span>
                      <span className="text-[11px] text-muted-foreground font-mono block">
                        {doc.page_count ? `${doc.page_count} pages` : ''}
                        {doc.page_count && doc.chunk_count ? ' • ' : ''}
                        {doc.chunk_count > 0 ? `${doc.chunk_count} chunks` : ''}
                        {!doc.page_count && !doc.chunk_count ? 'Ready to preview' : ''}
                      </span>
                    </span>
                  </span>
                  <span className="text-[10px] font-mono text-primary bg-primary/10 px-2 py-0.5 rounded-full border border-primary/20 shrink-0">
                    View PDF
                  </span>
                </button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => onRequestDelete()}
                  className="size-7 mr-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 shrink-0"
                  title="Wipe document vectors"
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* PDF Document Preview Popup Modal */}
      <DocViewerModal doc={previewDoc} onClose={() => setPreviewDoc(null)} />
    </div>
  );
};
