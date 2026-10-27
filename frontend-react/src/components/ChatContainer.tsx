import React, { useState, useRef, useEffect } from 'react';
import {
  Send,
  GitBranch,
  AlertTriangle,
  Shield,
  BookOpen,
  Sparkles,
  Menu,
  Lock,
  Loader2,
  ShieldCheck,
  FileText,
  CheckCircle2,
} from 'lucide-react';
import { Button } from './ui/button';

import { ChatMessage, ExampleQuestion, SourceCard } from '../types';
import { api } from '../lib/api';
import { MarkdownMessage } from './MarkdownMessage';
import { AIReasoningTrace } from './AIReasoningTrace';
import { SourcesDropdown } from './SourcesDropdown';

interface ChatContainerProps {
  scope: string;
  exampleChips: ExampleQuestion[];
  onUsageUpdate: () => void;
  onToast: (msg: string, type: 'info' | 'success' | 'warning' | 'error') => void;
  onOpenMobileMenu?: () => void;
  isIngesting?: boolean;
  documentCount?: number;
  activeDocName?: string;
}

export const ChatContainer: React.FC<ChatContainerProps> = ({
  scope,
  exampleChips,
  onUsageUpdate,
  onToast,
  onOpenMobileMenu,
  isIngesting = false,
  documentCount = 0,
  activeDocName,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [activeThoughtStages, setActiveThoughtStages] = useState<{
    stageIdx: number;
    timings?: Record<string, number>;
    isDone?: boolean;
    data?: any;
  } | null>(null);

  // Smart Chat Box States:
  // State 1: Locked & Grayed Out (custom scope with zero docs uploaded)
  // State 2: Processing (ingesting document & generating embeddings)
  // State 3: Unlocked & Ready (demo corpus or custom docs available)
  const isLocked = scope !== 'demo' && (!documentCount || documentCount === 0);
  const isProcessing = isIngesting;
  const isInputDisabled = isLoading || isProcessing || isLocked;

  const getPlaceholder = () => {
    if (isProcessing) {
      return activeDocName
        ? `Ingesting "${activeDocName}" & building vectors... Please wait.`
        : 'Ingesting document and generating embeddings... Please wait.';
    }
    if (isLocked) {
      return 'Please upload a PDF or select Demo Corpus to start chatting...';
    }
    if (activeDocName) {
      return `Ask anything about "${activeDocName}" with strict citations...`;
    }
    if (scope === 'demo') {
      return 'Ask anything about the demo documents with strict citations...';
    }
    return 'Ask a question with verified citations...';
  };

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeThoughtStages]);

  const handleSend = async (questionText?: string) => {
    const q = (questionText || input).trim();
    if (!q || isLoading) return;

    setInput('');
    const userMsgId = `user_${Date.now()}`;
    const assistantMsgId = `asst_${Date.now()}`;

    // Add user message
    setMessages((prev) => [
      ...prev,
      {
        id: userMsgId,
        role: 'user',
        content: q,
        timestamp: 'Just now',
      },
    ]);

    setIsLoading(true);

    // Initialize thought chain progress at Stage 0 (Safety Screen)
    setActiveThoughtStages({
      stageIdx: 0,
      isDone: false,
    });

    // Advance stages smoothly one by one while awaiting backend
    const ticker = setInterval(() => {
      setActiveThoughtStages((prev) => {
        if (!prev || prev.isDone || prev.stageIdx >= 5) return prev;
        return {
          ...prev,
          stageIdx: prev.stageIdx + 1,
        };
      });
    }, 550);

    try {
      // Build history
      const history = messages.slice(-6).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const response = await api.sendChat(q, history);
      clearInterval(ticker);

      setActiveThoughtStages({
        stageIdx: 5,
        isDone: true,
        timings: response.timings_ms || {},
        data: response,
      });

      // Append assistant answer
      setMessages((prev) => [
        ...prev,
        {
          id: assistantMsgId,
          role: 'assistant',
          content: response.answer,
          timestamp: 'Just now',
          timings_ms: response.timings_ms,
          sources: response.sources || [],
          is_found: response.is_found,
          is_grounded: response.is_grounded,
          rerank_fallback: response.rerank_fallback,
          used_visitor_key: response.used_visitor_key,
          model_used: response.model_used,
        },
      ]);

      onUsageUpdate();
    } catch (err: any) {
      clearInterval(ticker);
      setActiveThoughtStages(null);
      onToast(err.message || 'Failed to generate answer', 'error');
      setMessages((prev) => [
        ...prev,
        {
          id: `err_${Date.now()}`,
          role: 'assistant',
          content: `Error: ${err.message || 'An error occurred during retrieval/generation.'}`,
          timestamp: 'Just now',
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };



  const parseMarkdownCitations = (text: string) => {
    // Splits text into chunks and citation buttons
    const parts = text.split(/(\[\d+\])/g);
    return parts.map((part, idx) => {
      const match = part.match(/\[(\d+)\]/);
      if (match) {
        const num = match[1];
        return (
          <button
            key={idx}
            type="button"
            onClick={() => {
              const el = document.getElementById(`source-card-${num}`);
              if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                el.classList.add('ring-2', 'ring-primary');
                setTimeout(() => el.classList.remove('ring-2', 'ring-primary'), 2000);
              }
            }}
            className="inline-flex items-center justify-center font-mono text-[11px] font-bold px-1.5 py-0.5 mx-0.5 rounded bg-amber-500/10 text-amber-600 border border-amber-500/25 hover:bg-amber-500 hover:text-white transition-all cursor-pointer"
            title={`View Source [${num}]`}
          >
            [{num}]
          </button>
        );
      }
      return <span key={idx}>{part}</span>;
    });
  };

  return (
    <div className="flex flex-col h-screen flex-1 bg-card overflow-hidden">
      {/* Chat Header */}
      <div className="h-16 px-4 border-b border-border bg-card flex items-center justify-between text-xs shrink-0">
        <div className="flex items-center gap-2.5">
          {onOpenMobileMenu && (
            <Button
              variant="outline"
              size="icon"
              onClick={onOpenMobileMenu}
              className="size-7 lg:hidden mr-1"
              aria-label="Open sidebar"
            >
              <Menu className="size-4" />
            </Button>
          )}
          <div className="flex items-center gap-1.5">
            <span className="font-bold text-sm sm:text-base text-foreground tracking-tight">Provenance Copilot</span>
            <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse shrink-0" />
          </div>
        </div>
        <span className="text-[11px] font-mono text-muted-foreground hidden sm:inline-block">Groq Llama-3.3 + Cohere v3.5</span>
      </div>

      {/* Messages Feed */}
      <div
        ref={chatScrollRef}
        className={`flex-1 ${
          messages.length === 0 && !isLoading
            ? 'flex flex-col items-center justify-center p-6 overflow-hidden'
            : 'overflow-y-auto p-4 space-y-4'
        }`}
      >
        {messages.length === 0 && !isLoading ? (
          <div className="flex flex-col items-center justify-center text-center text-muted-foreground space-y-3.5 select-none max-w-md px-4">
            <div className="size-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shadow-sm">
              <Sparkles className="size-6" />
            </div>
            <div className="space-y-1.5">
              <h4 className="font-semibold text-foreground text-sm sm:text-[15px] tracking-tight">Ask anything over the documents</h4>
              <p className="text-xs sm:text-[13px] text-muted-foreground max-w-sm leading-relaxed">
                Every statement is backed by verifiable provenance citations. Type a question or click any sample question to start.
              </p>
            </div>
          </div>
        ) : (
          <>

        {messages.map((msg) => (
          <div key={msg.id} className="w-full">
            {msg.role === 'user' ? (
              /* User Chat Bubble - sized neatly based on input content */
              <div className="flex flex-col items-end w-full group my-1">
                <div className="w-fit max-w-[85%] sm:max-w-[75%] rounded-2xl rounded-br-xs px-4 py-2.5 bg-primary text-primary-foreground shadow-xs text-[13.5px] leading-relaxed break-words font-normal">
                  {msg.content}
                </div>
                <span className="text-[10px] text-muted-foreground/60 px-1 pt-1 font-mono">
                  {msg.timestamp}
                </span>
              </div>
            ) : (
              /* Assistant Stream - Sticks directly to the chat canvas with NO enclosing container */
              <div className="flex flex-col items-start w-full space-y-3 py-2">
                {/* AI Reasoning Trace: Direct borderless elements with Copilot logo and progressive reveal */}
                <AIReasoningTrace
                  isLoading={false}
                  timings_ms={msg.timings_ms}
                  sourcesCount={msg.sources?.length}
                  isGrounded={msg.is_grounded}
                  rerankFallback={msg.rerank_fallback}
                  isFound={msg.is_found}
                  modelUsed={msg.model_used}
                  scope={scope}
                  defaultExpanded={false}
                />

                {/* Fallback & Not-Found Notices */}
                {msg.rerank_fallback && (
                  <div className="p-2 rounded-md bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 text-xs flex items-center gap-2">
                    <AlertTriangle className="size-3.5 shrink-0" />
                    <span>Cohere Rerank circuit breaker active — sorted via hybrid search order</span>
                  </div>
                )}

                {!msg.is_found && (
                  <div className="p-2 rounded-md bg-amber-500/10 border border-amber-500/20 text-amber-600 dark:text-amber-400 text-xs flex items-center gap-2">
                    <Shield className="size-3.5 shrink-0" />
                    <span>Not-Found Gate: Query out-of-domain (score below threshold)</span>
                  </div>
                )}

                {/* Message Content: Borderless typography rendered directly */}
                <div className="w-full text-[14px] leading-relaxed text-foreground pl-0.5">
                  <MarkdownMessage content={msg.content} />
                </div>

                {/* Sources Dropdown: Collapsed by default, reveals source buttons when opened */}
                {msg.sources && msg.sources.length > 0 && (
                  <SourcesDropdown sources={msg.sources} messageId={msg.id} />
                )}

                {/* Provenance Grounding Audit Badge */}
                {msg.is_found !== false && (
                  <div className="flex flex-wrap items-center gap-2 pt-1 pb-0.5 text-[11px] font-mono select-none">
                    <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 shadow-xs">
                      <ShieldCheck className="size-3.5 shrink-0" />
                      <span className="font-semibold">{msg.is_grounded !== false ? '100% Grounded' : 'Cited Provenance'}</span>
                    </div>
                    <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-muted/50 text-muted-foreground border border-border">
                      <Sparkles className="size-3 text-primary shrink-0" />
                      <span>{msg.rerank_fallback ? 'Hybrid Rank (Circuit Breaker)' : 'Cohere Rerank v3.5'}</span>
                    </div>
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-muted/50 text-muted-foreground border border-border">
                        <FileText className="size-3 text-primary shrink-0" />
                        <span>{msg.sources.length} {msg.sources.length === 1 ? 'Source' : 'Sources'} Verified</span>
                      </div>
                    )}
                    {msg.model_used && (
                      <div className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] text-muted-foreground/70 border border-border/40">
                        <span>{msg.model_used.includes('/') ? msg.model_used.split('/').pop() : msg.model_used}</span>
                      </div>
                    )}
                  </div>
                )}

              </div>
            )}
          </div>
        ))}

        {/* Live AI Reasoning Trace while awaiting response (Borderless direct elements) */}
        {isLoading && activeThoughtStages && (
          <div className="flex flex-col items-start w-full space-y-1 py-1">
            <AIReasoningTrace
              isLoading={true}
              activeStageIdx={activeThoughtStages.stageIdx}
              timings_ms={activeThoughtStages.timings}
              modelUsed="Groq Llama-3.3-70b-versatile"
              scope={scope}
              defaultExpanded={true}
            />
            <span className="text-[10px] text-muted-foreground/60 px-0.5 font-mono">
              Executing pipeline...
            </span>
          </div>
        )}

            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input Bar with Smart States */}
      <div className="px-3 sm:px-4 py-3 pb-4 border-t border-border bg-card shadow-[0_-4px_16px_rgba(0,0,0,0.04)] shrink-0">
        {/* Processing State Banner */}
        {isProcessing && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/10 border border-primary/20 text-xs text-primary mb-2.5 font-medium animate-pulse">
            <Loader2 className="size-3.5 animate-spin shrink-0" />
            <span className="truncate">
              Ingesting <strong>{activeDocName || 'document'}</strong> & generating vector embeddings... Please wait before querying.
            </span>
          </div>
        )}

        {/* Locked State Helper Banner */}
        {isLocked && !isProcessing && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-muted/60 border border-border text-xs text-muted-foreground mb-2.5">
            <Lock className="size-3.5 text-muted-foreground/70 shrink-0" />
            <span>
              Workspace is empty. Upload a PDF in <strong>Upload Documents</strong> or select <strong>Demo Corpus</strong> to enable chat.
            </span>
          </div>
        )}

        <div className="w-full flex items-center gap-2.5 relative">
          <div className="relative flex-1">
            {isLocked && (
              <div className="absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground">
                <Lock className="size-4" />
              </div>
            )}
            {isProcessing && (
              <div className="absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none text-primary">
                <Loader2 className="size-4 animate-spin" />
              </div>
            )}
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !isInputDisabled) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              disabled={isInputDisabled}
              placeholder={getPlaceholder()}
              className={`w-full h-13 sm:h-14 ${
                isLocked || isProcessing ? 'pl-11 pr-5' : 'px-5'
              } rounded-xl border border-border bg-background/60 focus:bg-background text-sm sm:text-base shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/25 focus:border-primary transition-all disabled:opacity-60 disabled:cursor-not-allowed`}
            />
          </div>
          <Button
            onClick={() => handleSend()}
            disabled={isInputDisabled || !input.trim()}
            className="gap-2 h-13 sm:h-14 px-5 sm:px-6 rounded-xl text-sm sm:text-base font-medium shadow-sm shrink-0"
          >
            {isProcessing ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                <span className="hidden sm:inline">Processing...</span>
              </>
            ) : isLocked ? (
              <>
                <Lock className="size-4" />
                <span className="hidden sm:inline">Locked</span>
              </>
            ) : (
              <>
                <Send className="size-4 sm:size-5" />
                <span className="hidden sm:inline">Send</span>
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};
