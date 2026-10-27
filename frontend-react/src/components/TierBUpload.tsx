import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  UploadCloud,
  FileText,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  ShieldCheck,
  FileCheck,
  Key,
  Sparkles,
  ArrowRight,
  HelpCircle,
} from 'lucide-react';
import { Button } from './ui/button';
import { UploadedDoc, CostEstimate, LLMConfig } from '../types';
import { api } from '../lib/api';
import { DocViewerModal, DemoDocData } from './DocViewerModal';
import { TierCKeys } from './TierCKeys';

interface TierBUploadProps {
  documents: UploadedDoc[];
  onUploadSuccess: () => void;
  onRequestDelete: () => void;
  onToast: (msg: string, type: 'info' | 'success' | 'warning' | 'error') => void;
  onKeyConfigChange?: (config: LLMConfig) => void;
  onAskExample?: (q: string) => void;
  onIngestStateChange?: (isIngesting: boolean, docName?: string) => void;
}

export const TierBUpload: React.FC<TierBUploadProps> = ({
  documents,
  onUploadSuccess,
  onRequestDelete,
  onToast,
  onKeyConfigChange,
  onAskExample,
  onIngestStateChange,
}) => {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ stage: string; pct: number } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Optional BYOK State (activates TierCKeys within the upload workflow)
  const [useCustomKey, setUseCustomKey] = useState(false);

  // Document preview popup state & cached blob URLs for uploaded files
  const [previewDoc, setPreviewDoc] = useState<DemoDocData | null>(null);
  const [blobUrls, setBlobUrls] = useState<Record<string, string>>({});

  // Dynamic starter questions for ingested documents
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);

  // Notify parent of ingesting state
  useEffect(() => {
    onIngestStateChange?.(isUploading, selectedFile?.name);
  }, [isUploading, selectedFile, onIngestStateChange]);

  const handleToggleCustomKey = (checked: boolean) => {
    setUseCustomKey(checked);
    if (!checked) {
      // Reset visitor key on API client so it uses server keys
      api.setVisitorKeys(null as any);
      onToast('Switched back to standard owner-backed quota.', 'info');
    }
  };

  const startIngestionForFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      onToast('Only PDF documents are supported.', 'error');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      onToast('File size exceeds the 10MB limit.', 'error');
      return;
    }

    setSelectedFile(file);
    setIsUploading(true);
    setUploadProgress({ stage: 'Validating & uploading document...', pct: 20 });

    // Store local blob URL for instant PDF preview popup
    const blobUrl = URL.createObjectURL(file);
    setBlobUrls((prev) => ({ ...prev, [file.name]: blobUrl }));

    try {
      const res = await api.uploadFile(file, 'local_pymupdf');
      const jobId = res.job_id;

      setUploadProgress({ stage: 'Extracting text and structure...', pct: 45 });
      let pollCount = 0;

      const pollInterval = setInterval(async () => {
        pollCount += 1;
        try {
          const status = await api.pollJob(jobId);

          if (status.status === 'completed') {
            clearInterval(pollInterval);
            setUploadProgress({ stage: 'Indexing complete!', pct: 100 });

            // Generate clean starter questions based on the uploaded file
            const baseName = file.name.replace(/\.[^/.]+$/, '').replace(/[_-]/g, ' ');
            setSuggestedQuestions([
              `Summarize key findings and core metrics from ${baseName}`,
              `What are the primary operational requirements and obligations in ${baseName}?`,
              `Identify the major structural components and conclusions in ${baseName}`,
            ]);

            setTimeout(() => {
              setIsUploading(false);
              setUploadProgress(null);
              setSelectedFile(null);
              onUploadSuccess();
              onToast(`"${file.name}" indexed! Ready to query.`, 'success');
            }, 600);
          } else if (status.status === 'failed') {
            clearInterval(pollInterval);
            setIsUploading(false);
            setUploadProgress(null);
            onToast(status.error || 'Ingestion failed during processing.', 'error');
          } else {
            const targetPct = Math.min(45 + pollCount * 10, 92);
            const stages = [
              'Extracting text & layout structure...',
              'Generating semantic parent & child chunks...',
              'Computing Cohere 1024-dim embeddings...',
              'Upserting vectors into isolated Qdrant tenant...',
            ];
            const stageIndex = Math.min(Math.floor(pollCount / 2), stages.length - 1);
            setUploadProgress({ stage: stages[stageIndex], pct: targetPct });
          }
        } catch (pollErr: any) {
          console.warn('Polling warning:', pollErr);
        }

        if (pollCount > 60) {
          clearInterval(pollInterval);
          setIsUploading(false);
          setUploadProgress(null);
          onToast('Ingestion timed out. Please check server status.', 'error');
        }
      }, 1400);
    } catch (err: any) {
      setIsUploading(false);
      setUploadProgress(null);
      onToast(err.message || 'Failed to upload document', 'error');
    }
  };

  const handleOpenDocPreview = (doc: UploadedDoc) => {
    const url = blobUrls[doc.filename] || `/demo_corpus/${doc.filename}`;
    setPreviewDoc({
      title: doc.filename,
      filename: doc.filename,
      desc: `Ingested document: ${doc.chunk_count} chunks, ${doc.token_count} tokens.`,
      pages: 1,
      chunks: doc.chunk_count,
      category: 'Uploaded PDF',
      pdfUrl: url,
    });
  };

  return (
    <div className="space-y-4">
      {/* Upload Box */}
      <div className="border border-border rounded-lg p-5 bg-card shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <UploadCloud className="size-5 text-primary" />
            <h3 className="font-semibold text-base">Document Ingestion</h3>
          </div>
          <span className="text-xs font-mono bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 px-2.5 py-0.5 rounded-full">
            Isolated Session Tenant
          </span>
        </div>

        {/* Guardrail Limits Banner */}
        <div className="p-3 rounded-lg border border-border/80 bg-muted/30 space-y-1.5 text-xs">
          <div className="flex items-center gap-1.5 font-semibold text-foreground">
            <ShieldCheck className="size-4 text-emerald-600 dark:text-emerald-400" />
            <span>Built-in Enterprise Limits & Safety</span>
          </div>
          <div className="flex flex-wrap gap-2 text-[11px] font-mono text-muted-foreground pt-1">
            <span className="px-2 py-0.5 rounded bg-card border border-border/70">
              Max 10MB PDF
            </span>
            <span className="px-2 py-0.5 rounded bg-card border border-border/70">
              Up to 30 Pages
            </span>
            <span className="px-2 py-0.5 rounded bg-card border border-border/70">
              3 Docs / Session
            </span>
            <span className="px-2 py-0.5 rounded bg-card border border-border/70 text-emerald-600 dark:text-emerald-400">
              Auto-Shredded on Exit
            </span>
          </div>
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
          className={`border-2 border-dashed rounded-lg p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-all ${
            dragActive
              ? 'border-primary bg-primary/5'
              : 'border-border/80 hover:border-primary/50 hover:bg-muted/30'
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

          <div className="size-12 rounded-full bg-primary/10 flex items-center justify-center text-primary mb-3">
            <UploadCloud className="size-6" />
          </div>

          <p className="text-sm font-medium text-foreground">
            {selectedFile ? selectedFile.name : 'Click to browse or drop your PDF here'}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Direct auto-parsing • Max 10MB • Up to 30 pages
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
          </div>
        )}

        {/* Optional BYOK API Key Checkbox & Slide-down Zone */}
        <div className="pt-2 border-t border-border/60 space-y-3">
          <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-foreground select-none">
            <input
              type="checkbox"
              checked={useCustomKey}
              onChange={(e) => handleToggleCustomKey(e.target.checked)}
              className="size-4 rounded border-border text-primary focus:ring-primary cursor-pointer accent-primary"
            />
            <span className="flex items-center gap-1.5">
              <Key className="size-3.5 text-amber-500" />
              <span>I want to use my own LLM API Key (Optional)</span>
            </span>
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
      <div className="border border-border rounded-lg p-5 bg-card shadow-sm space-y-3">
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
                onClick={() => handleOpenDocPreview(doc)}
                className="p-3 rounded-md border border-border bg-muted/20 hover:bg-muted/50 hover:border-primary/50 transition-all cursor-pointer flex items-center justify-between gap-3 text-xs group select-none"
                title={`Click to preview ${doc.filename}`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <FileText className="size-4 text-primary shrink-0 group-hover:scale-110 transition-transform" />
                  <div className="min-w-0">
                    <p className="font-medium text-foreground truncate group-hover:text-primary transition-colors">
                      {doc.filename}
                    </p>
                    <p className="text-[11px] text-muted-foreground font-mono">
                      {doc.chunk_count} chunks • {doc.token_count} tokens
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <span className="text-[10px] font-mono text-primary bg-primary/10 px-2 py-0.5 rounded-full border border-primary/20 opacity-0 group-hover:opacity-100 transition-opacity">
                    View PDF
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={(e) => {
                      e.stopPropagation();
                      onRequestDelete();
                    }}
                    className="size-7 text-muted-foreground hover:text-destructive hover:bg-destructive/10 shrink-0"
                    title="Wipe document vectors"
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
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
