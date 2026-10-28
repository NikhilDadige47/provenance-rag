import React, { useState } from 'react';
import { FileText, ShieldCheck, ArrowRight, HelpCircle } from 'lucide-react';
import { DocViewerModal, DemoDocData } from './DocViewerModal';
import { ExampleQuestion } from '../types';

interface TierADemoProps {
  onAskExample: (question: string) => void;
  exampleChips?: ExampleQuestion[];
}

const DEMO_DOCS: DemoDocData[] = [
  {
    title: 'Apple Form 10-K — FY2023',
    filename: 'Apple-Annual-Report-2023.pdf',
    desc: 'Apple Inc. Form 10-K for the fiscal year ended September 30, 2023.',
    pages: 65,
    chunks: 0,
    category: 'FY2023',
    pdfUrl: '/demo_corpus/Apple-Annual-Report-2023.pdf',
  },
  {
    title: 'Apple Form 10-K — FY2024',
    filename: 'Apple-Annual-Report-2024.pdf',
    desc: 'Apple Inc. Form 10-K for the fiscal year ended September 28, 2024.',
    pages: 65,
    chunks: 0,
    category: 'FY2024',
    pdfUrl: '/demo_corpus/Apple-Annual-Report-2024.pdf',
  },
  {
    title: 'Apple Form 10-K — FY2025',
    filename: 'Apple-Annual-Report-2025.pdf',
    desc: 'Apple Inc. Form 10-K for the fiscal year ended September 27, 2025.',
    pages: 67,
    chunks: 0,
    category: 'FY2025',
    pdfUrl: '/demo_corpus/Apple-Annual-Report-2025.pdf',
  },
];

const FALLBACK_QUESTIONS = [
  "What was Apple's total net sales in fiscal year 2023?",
  "What was Apple's total net sales in fiscal year 2024?",
  "What was Apple's total net sales in fiscal year 2025?",
  "What was Apple's operating income in fiscal year 2025?",
  'What were iPhone net sales in fiscal year 2025 according to the category table?',
  'What were Services net sales in fiscal year 2024?',
  'How much did Apple spend on Research and Development (R&D) in FY2025?',
  "What was total shareholders' equity on the balance sheet at the end of FY2025?",
  "What was Apple's total copper mining revenue on Mars in FY2024?",
  'How many supersonic passenger jets did Apple deliver to airlines in 2023?',
];

export const TierADemo: React.FC<TierADemoProps> = ({ onAskExample, exampleChips = [] }) => {
  const [selectedDoc, setSelectedDoc] = useState<DemoDocData | null>(null);

  const sampleQuestions =
    exampleChips.length > 0
      ? exampleChips.map((ex) => ex.question)
      : FALLBACK_QUESTIONS;

  return (
    <div className="space-y-3">
      <div className="border border-border rounded-lg p-3 surface-inset shadow-sm space-y-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="size-3.5 text-emerald-600 shrink-0" />
            <h3 className="font-semibold text-sm">Pre-Indexed Demo Corpus</h3>
          </div>
          <span className="text-[10px] bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 px-1.5 py-px rounded-full whitespace-nowrap shrink-0 font-medium">
            Ready
          </span>
        </div>

        <p className="text-[11px] text-muted-foreground">
          Apple financial reports (Form 10-K, FY2023–FY2025). Click a filing to preview, or a question to query.
        </p>

        <div className="grid grid-cols-3 gap-1.5">
          {DEMO_DOCS.map((doc) => (
            <button
              key={doc.filename}
              type="button"
              onClick={() => setSelectedDoc(doc)}
              className="min-w-0 rounded-md border border-border/70 bg-muted/15 hover:bg-muted/40 hover:border-primary/40 transition-colors cursor-pointer px-1.5 py-1.5 flex items-center gap-1.5 text-left group"
              title={`Click to preview ${doc.title}`}
            >
              <FileText className="size-3 text-muted-foreground group-hover:text-primary shrink-0" />
              <span className="min-w-0 flex flex-col leading-tight">
                <span className="text-[11px] font-medium text-foreground truncate">
                  {doc.category}
                </span>
                <span className="text-[10px] text-muted-foreground">{doc.pages} pages</span>
              </span>
            </button>
          ))}
        </div>

        <div className="space-y-1.5 pt-2 border-t border-border/40">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-foreground">
            <HelpCircle className="size-3 text-primary" />
            <span>Sample questions</span>
            <span className="text-[10px] text-muted-foreground font-normal">
              {sampleQuestions.length}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-1">
            {sampleQuestions.map((q, idx) => (
              <button
                key={`${idx}-${q}`}
                type="button"
                onClick={() => onAskExample(q)}
                className="w-full text-left text-[11px] leading-snug bg-muted/30 hover:bg-muted border border-border/60 hover:border-primary/40 rounded px-1.5 py-1 transition-colors text-muted-foreground hover:text-foreground flex items-start gap-1 group cursor-pointer"
              >
                <span className="line-clamp-2 flex-1 min-w-0">{q}</span>
                <ArrowRight className="size-2.5 mt-0.5 opacity-30 group-hover:opacity-100 group-hover:text-primary transition-opacity shrink-0" />
              </button>
            ))}
          </div>
        </div>
      </div>

      <DocViewerModal doc={selectedDoc} onClose={() => setSelectedDoc(null)} />
    </div>
  );
};
