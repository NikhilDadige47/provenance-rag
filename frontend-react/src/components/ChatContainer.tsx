import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Send,
  GitBranch,
  AlertTriangle,
  Shield,
  BookOpen,
  Menu,
  Lock,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { Button } from './ui/button';

import { ChatMessage, ExampleQuestion, SourceCard } from '../types';
import { api } from '../lib/api';
import { MarkdownMessage } from './MarkdownMessage';
import { AIReasoningTrace } from './AIReasoningTrace';
import { SourcesDropdown } from './SourcesDropdown';
import { SourceInspectorPanel } from './SourceInspectorPanel';
import queryHistoryIcon from '../assets/query-history.png';

interface ChatContainerProps {
  scope: string;
  exampleChips: ExampleQuestion[];
  queuedQuestion?: string | null;
  queuedNonce?: number;
  onUsageUpdate: () => void;
  onToast: (msg: string, type: 'info' | 'success' | 'warning' | 'error') => void;
  onOpenMobileMenu?: () => void;
  isIngesting?: boolean;
  documentCount?: number;
  activeDocName?: string;
  llmProvider?: string;
  llmModel?: string;
}

const PROVIDER_LABELS: Record<string, string> = {
  groq: 'Groq',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Gemini',
  mistral: 'Mistral',
};

function formatLlmLabel(provider?: string, model?: string): string {
  const rawProvider = (provider || '').trim();
  const rawModel = (model || '').trim();
  if (!rawProvider && !rawModel) return '';
  const name =
    PROVIDER_LABELS[rawProvider.toLowerCase()] ||
    (rawProvider ? rawProvider.charAt(0).toUpperCase() + rawProvider.slice(1) : 'LLM');
  if (!rawModel) return name;
  return `${name} (${rawModel})`;
}

export const ChatContainer: React.FC<ChatContainerProps> = ({
  scope,
  exampleChips,
  queuedQuestion = null,
  queuedNonce = 0,
  onUsageUpdate,
  onToast,
  onOpenMobileMenu,
  isIngesting = false,
  documentCount = 0,
  activeDocName,
  llmProvider,
  llmModel,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [inspectedSource, setInspectedSource] = useState<SourceCard | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const citationKey = (src: SourceCard) => src.citation.replace(/[\[\]【】]/g, '').trim();

  const openSourceInspector = useCallback((src: SourceCard) => {
    setInspectedSource((current) => {
      if (current && citationKey(current) === citationKey(src)) {
        setInspectorOpen(false);
        return null;
      }
      setInspectorOpen(true);
      return src;
    });
  }, []);
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

  const llmLabel = formatLlmLabel(llmProvider, llmModel);

  const getPlaceholder = () => {
    if (isProcessing) {
      return 'Ingesting document...';
    }
    if (isLocked) {
      return 'Upload a document to chat';
    }
    return 'Type your query...';
  };

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeThoughtStages]);

  useEffect(() => {
    if (!queuedQuestion || isInputDisabled) return;
    setInput(queuedQuestion);
    requestAnimationFrame(() => {
      document.getElementById('chat-input')?.focus();
    });
  }, [queuedQuestion, queuedNonce, isInputDisabled]);

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
    <div className="relative flex flex-col h-full flex-1 surface-panel overflow-hidden">
      {/* Chat Header */}
      <div className="h-16 px-4 border-b border-border surface-header flex items-center justify-between text-xs shrink-0">
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
        {llmLabel && (
          <span
            className="text-[11px] font-mono text-muted-foreground hidden sm:inline-block truncate max-w-[280px]"
            title={llmLabel}
          >
            {llmLabel}
          </span>
        )}
      </div>

      <div className="relative flex-1 min-h-0 flex flex-col overflow-hidden">
      {/* Messages Feed */}
      <div
        ref={chatScrollRef}
        className={`flex-1 min-h-0 ${
          messages.length === 0 && !isLoading
            ? 'flex flex-col items-center justify-center p-6 overflow-hidden'
            : 'overflow-y-auto p-4 space-y-4'
        }`}
      >
        {messages.length === 0 && !isLoading ? (
          <div className="flex flex-col items-center justify-center text-center select-none gap-3 px-4">
            <img
              src={queryHistoryIcon}
              alt=""
              title="History icon from Flaticon"
              className="size-20 object-contain opacity-90 dark:invert"
            />
            <h4 className="font-medium text-sm text-muted-foreground tracking-tight">
              What do you want to know?
            </h4>
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
                  <MarkdownMessage
                    content={msg.content}
                    sources={msg.sources}
                    onCitationClick={openSourceInspector}
                  />
                </div>

                {/* Sources Dropdown: Collapsed by default, reveals source buttons when opened */}
                {msg.sources && msg.sources.length > 0 && (
                  <SourcesDropdown
                    sources={msg.sources}
                    messageId={msg.id}
                    activeCitation={
                      inspectedSource
                        ? inspectedSource.citation.replace(/[\[\]【】]/g, '').trim()
                        : null
                    }
                    onSelectSource={openSourceInspector}
                  />
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
              modelUsed={llmLabel || undefined}
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

      <SourceInspectorPanel
        source={inspectedSource}
        open={inspectorOpen}
        onToggle={() => setInspectorOpen((prev) => !prev)}
        onClose={() => {
          setInspectorOpen(false);
          setInspectedSource(null);
        }}
      />
      </div>

      {/* Input Bar with Smart States */}
      <div className="px-3 sm:px-4 py-2.5 border-t border-border surface-header shrink-0">
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

        <div className="w-full flex items-center gap-2 relative">
          <div className="relative flex-1">
            {isLocked && (
              <div className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground">
                <Lock className="size-3.5" />
              </div>
            )}
            {isProcessing && (
              <div className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none text-primary">
                <Loader2 className="size-3.5 animate-spin" />
              </div>
            )}
            <input
              id="chat-input"
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
              autoComplete="off"
              className={`w-full h-10 ${
                isLocked || isProcessing ? 'pl-9 pr-3.5' : 'px-3.5'
              } rounded-lg border border-border bg-background/60 focus:bg-background text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/25 focus:border-primary transition-all disabled:opacity-60 disabled:cursor-not-allowed placeholder:text-muted-foreground/70`}
            />
          </div>
          <Button
            onClick={() => handleSend()}
            disabled={isInputDisabled || !input.trim()}
            className="gap-1.5 h-10 px-4 rounded-lg text-sm font-medium shadow-sm shrink-0"
          >
            {isProcessing ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                <span className="hidden sm:inline">Processing</span>
              </>
            ) : isLocked ? (
              <>
                <Lock className="size-3.5" />
                <span className="hidden sm:inline">Locked</span>
              </>
            ) : (
              <>
                <Send className="size-3.5" />
                <span className="hidden sm:inline">Send</span>
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};
