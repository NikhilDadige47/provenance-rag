export type JobLifecycleStatus =
  | 'queued'
  | 'parsing'
  | 'chunking'
  | 'embedding'
  | 'indexing'
  | 'ready'
  | 'completed'
  | 'failed';

export interface IngestProgress {
  jobId: string | null;
  fileName: string;
  stage: string;
  pct: number;
  phase: 'uploading' | 'processing' | 'done' | 'error';
}

const JOB_STAGE_COPY: Record<string, { stage: string; pct: number }> = {
  queued: { stage: 'Queued for isolated ingestion...', pct: 18 },
  parsing: { stage: 'Extracting text and layout structure...', pct: 38 },
  chunking: { stage: 'Generating semantic parent & child chunks...', pct: 55 },
  embedding: { stage: 'Computing Cohere embeddings...', pct: 76 },
  indexing: { stage: 'Upserting vectors into isolated Qdrant tenant...', pct: 90 },
  ready: { stage: 'Indexing complete!', pct: 100 },
  completed: { stage: 'Indexing complete!', pct: 100 },
};

export const INGEST_POLL_MS = 1200;
export const INGEST_TIMEOUT_MS = 8 * 60 * 1000;

export function isJobSuccess(status: string | undefined): boolean {
  return status === 'ready' || status === 'completed';
}

export function isJobFailed(status: string | undefined): boolean {
  return status === 'failed';
}

export function progressForJobStatus(status: string | undefined): { stage: string; pct: number } {
  if (!status) {
    return { stage: 'Processing document...', pct: 45 };
  }
  return JOB_STAGE_COPY[status] ?? { stage: 'Processing document...', pct: 45 };
}

export function suggestedQuestionsForFile(fileName: string): string[] {
  const baseName = fileName.replace(/\.[^/.]+$/, '').replace(/[_-]/g, ' ');
  return [
    `Summarize key findings and core metrics from ${baseName}`,
    `What are the primary operational requirements and obligations in ${baseName}?`,
    `Identify the major structural components and conclusions in ${baseName}`,
  ];
}
