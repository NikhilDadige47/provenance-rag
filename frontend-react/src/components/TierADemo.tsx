import React, { useState } from 'react';
import { FileText, ShieldCheck, Cpu, ArrowRight, HelpCircle, Eye } from 'lucide-react';
import { Button } from './ui/button';
import { DocViewerModal, DemoDocData } from './DocViewerModal';

interface TierADemoProps {
  onAskExample: (question: string) => void;
}

export const TierADemo: React.FC<TierADemoProps> = ({ onAskExample }) => {
  const [selectedDoc, setSelectedDoc] = useState<DemoDocData | null>(null);

  const demoDocs: DemoDocData[] = [
    {
      title: 'US Constitution & Bill of Rights',
      filename: 'us_constitution_bill_of_rights.pdf',
      desc: 'Foundational legal charter of the United States, defining federal government structure across Articles I–VII and protecting individual civil rights through the Bill of Rights (Amendments 1–10).',
      pages: 6,
      chunks: 24,
      category: 'Constitutional Law',
      pdfUrl: '/demo_corpus/us_constitution_bill_of_rights.pdf',
    },
    {
      title: 'Acme Corp FY2025 Annual Financial Report',
      filename: 'acme_annual_financial_report_2025.pdf',
      desc: 'Comprehensive annual financial report detailing Acme Corporation\'s FY2025 performance, Enterprise Cloud revenue growth, operating efficiency gains, and balance sheet structure.',
      pages: 4,
      chunks: 16,
      category: 'Corporate Finance',
      pdfUrl: '/demo_corpus/acme_annual_financial_report_2025.pdf',
    },
  ];

  const sampleQuestions = [
    "What was Acme Corporation's total consolidated revenue in FY2025?",
    "Which freedoms are explicitly protected under the First Amendment?",
    "How much revenue did Enterprise Cloud services contribute to Acme in 2025?",
    "Where are legislative powers vested according to Article I of the Constitution?",
    "By what percentage did Acme's operating expenses decrease?",
    "What is Acme Corporation's debt-to-equity ratio?",
  ];

  return (
    <div className="space-y-4">
      <div className="border border-border rounded-lg p-5 bg-card shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="size-5 text-emerald-600 shrink-0" />
            <h3 className="font-semibold text-base">Pre-Indexed Demo Corpus</h3>
          </div>
          <span className="text-xs bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 px-2.5 py-0.5 rounded-full whitespace-nowrap shrink-0 font-medium">
            Ready for instant queries
          </span>
        </div>

        <p className="text-xs text-muted-foreground leading-relaxed">
          The demo library contains verified reference documents, fully indexed for accurate semantic retrieval and factual citations. You can explore documents and ask questions immediately with no setup or file uploads needed.
        </p>

        {/* Real Demo Documents from demo_corpus */}
        <div className="grid grid-cols-1 gap-3">
          {demoDocs.map((doc, idx) => (
            <div
              key={idx}
              onClick={() => setSelectedDoc(doc)}
              className="p-4 rounded-lg border border-border bg-card/60 hover:bg-muted/40 hover:border-primary/50 transition-all cursor-pointer flex flex-col gap-2.5 group shadow-xs hover:shadow-md active:scale-[0.995]"
              title={`Click to preview ${doc.title}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="size-8 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0 group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                    <FileText className="size-4" />
                  </div>
                  <div className="min-w-0">
                    <span className="font-semibold text-sm text-foreground group-hover:text-primary transition-colors block truncate">
                      {doc.title}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs font-medium px-2.5 py-0.5 rounded-full bg-secondary text-secondary-foreground border border-border whitespace-nowrap">
                    {doc.category}
                  </span>
                  <span className="hidden sm:inline-flex items-center gap-1 text-xs font-medium text-primary bg-primary/10 px-2 py-0.5 rounded-full border border-primary/20 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Eye className="size-3" />
                    <span>Preview PDF</span>
                  </span>
                </div>
              </div>

              <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
                {doc.desc}
              </p>

              <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-border/50 text-xs text-muted-foreground">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11.5px]">
                  <span className="font-medium text-foreground/85 flex items-center gap-1.5">
                    <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-muted border border-border">PDF</span>
                    <span>{doc.pages} pages</span>
                  </span>
                  <span className="text-muted-foreground/40">•</span>
                  <span className="whitespace-nowrap">{doc.chunks} indexed sections</span>
                  <span className="text-muted-foreground/40">•</span>
                  <span className="text-muted-foreground/80 truncate max-w-[200px]">
                    {doc.category === 'Constitutional Law' ? 'Complete Edition' : 'Audited Filing'}
                  </span>
                </div>
                <span className="text-xs text-primary font-medium flex items-center gap-1 group-hover:translate-x-0.5 transition-transform">
                  <span>Open Document</span>
                  <ArrowRight className="size-3" />
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Curated Sample Questions */}
        <div className="space-y-2 pt-1">
          <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
            <HelpCircle className="size-3.5 text-primary" />
            <span>Click to test sample questions:</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {sampleQuestions.map((q, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => onAskExample(q)}
                className="text-left text-xs bg-muted/50 hover:bg-muted border border-border rounded-md px-2.5 py-1.5 transition-colors text-muted-foreground hover:text-foreground hover:border-primary/50 flex items-center gap-1.5 group"
              >
                <span className="line-clamp-1">{q}</span>
                <ArrowRight className="size-2.5 opacity-40 group-hover:opacity-100 group-hover:text-primary transition-opacity shrink-0" />
              </button>
            ))}
          </div>
        </div>

        <div className="pt-2 border-t border-border flex items-center justify-between text-xs">
          <span className="text-muted-foreground flex items-center gap-1.5">
            <Cpu className="size-3.5 text-primary" />
            Powered by Groq Llama-3.3-70b & Cohere Rerank v3.5
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onAskExample("What was Acme Corporation's total consolidated revenue in FY2025?")}
            className="text-primary hover:text-primary gap-1"
          >
            <span>Ask sample question</span>
            <ArrowRight className="size-3" />
          </Button>
        </div>
      </div>

      {/* Specific Document PDF Content Popup Modal */}
      <DocViewerModal doc={selectedDoc} onClose={() => setSelectedDoc(null)} />
    </div>
  );
};

