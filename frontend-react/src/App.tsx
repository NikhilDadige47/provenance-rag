import React, { useState, useEffect, useRef } from 'react';
import { NavSidebar, NavItem } from './components/NavSidebar';
import { SectionDetails } from './components/SectionDetails';
import { ChatContainer } from './components/ChatContainer';
import { SectionFooter } from './components/SectionFooter';
import { DeleteModal } from './components/DeleteModal';
import { Toast, ToastMessage } from './components/Toast';
import { LandingPage } from './components/LandingPage';
import { MobilePane, MobilePaneSwitch, MobileTabBar, MobileTopBar } from './components/MobileChrome';
import { useCompactLayout } from './lib/useCompactLayout';
import { AccessTier, UsageInfo, ExampleQuestion, UploadedDoc, LLMConfig } from './types';
import { api } from './lib/api';
import {
  bindUploadedDoc,
  clearUploadedFiles,
  originalNameForDoc,
  rememberUploadedFile,
} from './lib/uploadedFiles';
import {
  IngestProgress,
  INGEST_POLL_MS,
  INGEST_TIMEOUT_MS,
  isJobFailed,
  isJobSuccess,
  progressForJobStatus,
  suggestedQuestionsForFile,
} from './lib/ingestProgress';

const DEFAULT_MIDDLE_WIDTH = 480;
const MIN_MIDDLE_WIDTH = 400;

type Surface = 'landing' | 'app';
type Entry = 'demo' | 'upload';

function readHash(): { surface: Surface; entry: Entry } {
  const raw = (window.location.hash || '#/').replace(/^#/, '') || '/';
  if (raw.startsWith('/upload')) return { surface: 'app', entry: 'upload' };
  if (raw.startsWith('/app') || raw.startsWith('/demo') || raw.startsWith('/limits')) {
    return { surface: 'app', entry: 'demo' };
  }
  return { surface: 'landing', entry: 'demo' };
}

function writeHash(surface: Surface, entry: Entry = 'demo') {
  const next =
    surface === 'landing' ? '#/' : entry === 'upload' ? '#/upload' : '#/app';
  if (window.location.hash !== next) {
    window.history.replaceState(null, '', next);
  }
}

export function App() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('provenance_theme_v2');
    return (saved as 'light' | 'dark') || 'dark';
  });
  const [surface, setSurface] = useState<Surface>(() => readHash().surface);
  const [activeNav, setActiveNav] = useState<NavItem>(
    () => (readHash().entry === 'upload' ? 'tier_b' : 'tier_a')
  );
  const [currentTier, setCurrentTier] = useState<AccessTier>('tier_a');
  const [scope, setScope] = useState<string>('demo');
  const [usage, setUsage] = useState<UsageInfo | null>(null);
  const [exampleChips, setExampleChips] = useState<ExampleQuestion[]>([]);
  const [documents, setDocuments] = useState<UploadedDoc[]>([]);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [ingest, setIngest] = useState<IngestProgress | null>(null);
  const isIngesting = Boolean(ingest && ingest.phase !== 'done' && ingest.phase !== 'error');
  const activeDocName = ingest?.fileName || documents[0]?.filename;
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [queuedQuestion, setQueuedQuestion] = useState<string | null>(null);
  const [queuedNonce, setQueuedNonce] = useState(0);
  const [visitorLlm, setVisitorLlm] = useState<LLMConfig | null>(null);

  // Nav sidebar collapse state
  const [isNavCollapsed, setIsNavCollapsed] = useState<boolean>(false);
  const compact = useCompactLayout();
  const [mobilePane, setMobilePane] = useState<MobilePane>('context');
  const [keyboardOpen, setKeyboardOpen] = useState(false);

  // Section 2 (Middle details panel) custom width in pixels (null = equal 50/50 division by default)
  const [middleWidth, setMiddleWidth] = useState<number | null>(() => {
    // Clear legacy fixed width storage so 50/50 is default
    localStorage.removeItem('provenance_middle_width');
    const saved = localStorage.getItem('provenance_custom_middle_width');
    if (!saved) return null;
    const parsed = parseInt(saved, 10);
    return isNaN(parsed) ? null : Math.max(MIN_MIDDLE_WIDTH, parsed);
  });
  const [isDragging, setIsDragging] = useState<boolean>(false);

  const isDraggingRef = useRef<boolean>(false);

  // Auto-resize logic: When custom width is set, NavSidebar collapse expands Section 2.
  // When null, both Section 2 and Section 3 flex-1 basis-0 naturally divide 50/50!
  const effectiveMiddleWidth = middleWidth !== null
    ? (isNavCollapsed ? middleWidth + 152 : middleWidth)
    : null;

  useEffect(() => {
    if (!compact) {
      setKeyboardOpen(false);
      return;
    }

    const isTextField = (el: EventTarget | null) => {
      if (!(el instanceof HTMLElement)) return false;
      const tag = el.tagName;
      if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
      if (tag !== 'INPUT') return false;
      const type = (el as HTMLInputElement).type;
      return !['checkbox', 'radio', 'file', 'button', 'submit', 'hidden'].includes(type);
    };

    const onFocusIn = (event: FocusEvent) => {
      if (isTextField(event.target)) setKeyboardOpen(true);
    };
    const onFocusOut = () => {
      window.setTimeout(() => {
        if (!isTextField(document.activeElement)) setKeyboardOpen(false);
      }, 120);
    };

    document.addEventListener('focusin', onFocusIn);
    document.addEventListener('focusout', onFocusOut);
    return () => {
      document.removeEventListener('focusin', onFocusIn);
      document.removeEventListener('focusout', onFocusOut);
    };
  }, [compact]);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('provenance_theme_v2', theme);
    localStorage.setItem('provenance_theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
  };

  const addToast = (message: string, type: 'info' | 'success' | 'warning' | 'error') => {
    const id = `toast_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const refreshUsage = async () => {
    try {
      const u = await api.getUsage();
      setUsage(u);
    } catch {
      // Ignored
    }
  };

  const refreshDocuments = async () => {
    try {
      const docs = await api.getDocuments();
      setDocuments((prev) => {
        if (docs.length === 0) return prev;
        return docs.map((doc) => {
          const filename = originalNameForDoc(doc.doc_id, doc.filename);
          bindUploadedDoc(doc.doc_id, filename);
          return { ...doc, filename };
        });
      });
    } catch {
      // Ignored
    }
  };

  const sessionStarted = useRef(false);

  const enterWorkspace = (entry: Entry) => {
    setActiveNav(entry === 'upload' ? 'tier_b' : 'tier_a');
    if (entry === 'upload') {
      setCurrentTier('tier_b');
      api.setTier('tier_b');
      setScope('isolated');
    } else {
      setCurrentTier('tier_a');
      api.setTier('tier_a');
      setScope('demo');
    }
    setSurface('app');
    writeHash('app', entry);
  };

  const returnToOverview = () => {
    setSurface('landing');
    writeHash('landing');
  };

  // Session starts only after the visitor leaves the overview. Landing is static.
  useEffect(() => {
    if (surface !== 'app' || sessionStarted.current) return;
    sessionStarted.current = true;

    const initApp = async () => {
      try {
        const sess = await api.ensureSession('tier_a');
        setScope(sess.scope || 'demo');
        await refreshUsage();
        const chips = await api.getExamples();
        setExampleChips(chips);
        refreshDocuments();
      } catch (err: any) {
        addToast(err.message || 'Failed to initialize session', 'error');
      }
    };

    initApp();
  }, [surface]);

  useEffect(() => {
    const onHash = () => {
      const next = readHash();
      setSurface(next.surface);
      if (next.surface !== 'app') return;
      if (next.entry === 'upload') {
        setActiveNav('tier_b');
        setCurrentTier('tier_b');
        api.setTier('tier_b');
        setScope('isolated');
      } else {
        setActiveNav('tier_a');
        setCurrentTier('tier_a');
        api.setTier('tier_a');
        setScope('demo');
      }
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // Keep ingest polling at the App level so it survives leaving the Upload panel.
  useEffect(() => {
    if (!ingest?.jobId || ingest.phase !== 'processing') return;

    let cancelled = false;
    let settled = false;
    let inFlight = false;
    const jobId = ingest.jobId;
    const fileName = ingest.fileName;
    const startedAt = Date.now();

    const finishSuccess = (status: {
      doc_id?: string;
      chunks?: number;
      pages?: number;
      parser_name?: string;
      parser_used?: string;
      degraded?: boolean;
    }) => {
      if (settled || cancelled) return;
      settled = true;
      if (status.doc_id) {
        bindUploadedDoc(status.doc_id, fileName);
      }
      const parserUsed = status.parser_used || status.parser_name || 'auto';
      const degraded = Boolean(status.degraded) || parserUsed === 'local_pymupdf';
      const localDoc: UploadedDoc = {
        doc_id: status.doc_id || `local_${jobId}`,
        filename: fileName,
        chunk_count: Number(status.chunks || 0),
        token_count: 0,
        parser_tier: parserUsed,
        uploaded_at: new Date().toISOString(),
        page_count: Number(status.pages || 0),
        degraded,
      };
      setDocuments((prev) => {
        const withoutDup = prev.filter(
          (doc) => doc.doc_id !== localDoc.doc_id && doc.filename !== fileName
        );
        return [localDoc, ...withoutDup];
      });
      setIngest({
        jobId,
        fileName,
        stage: 'Indexing complete!',
        pct: 100,
        phase: 'done',
      });
      setSuggestedQuestions(suggestedQuestionsForFile(fileName));
      refreshDocuments();
      refreshUsage();
      if (degraded) {
        addToast(
          `"${fileName}" indexed with basic extract. Premium parsers were out of budget or unavailable.`,
          'warning'
        );
      } else {
        addToast(`"${fileName}" indexed. Ready to query.`, 'success');
      }
      window.setTimeout(() => {
        setIngest(null);
      }, 700);
    };

    const finishFailure = (message: string) => {
      if (settled || cancelled) return;
      settled = true;
      setIngest(null);
      addToast(message, 'error');
    };

    const poll = async () => {
      if (cancelled || settled || inFlight) return;
      inFlight = true;
      try {
        const status = await api.pollJob(jobId);
        if (cancelled || settled) return;
        if (isJobSuccess(status.status)) {
          finishSuccess(status);
          return;
        }
        if (isJobFailed(status.status)) {
          finishFailure(status.error_message || status.error || 'Ingestion failed during processing.');
          return;
        }
        const next = progressForJobStatus(status.status);
        setIngest((prev) =>
          prev && prev.jobId === jobId
            ? { ...prev, stage: next.stage, pct: next.pct, phase: 'processing' }
            : prev
        );
      } catch (pollErr) {
        console.warn('Polling warning:', pollErr);
      } finally {
        inFlight = false;
      }

      if (Date.now() - startedAt > INGEST_TIMEOUT_MS) {
        finishFailure('Ingestion timed out. Please check server status.');
      }
    };

    poll();
    const intervalId = window.setInterval(poll, INGEST_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [ingest?.jobId, ingest?.phase]);

  const handleSelectTier = async (tier: AccessTier) => {
    setCurrentTier(tier);
    api.setTier(tier);
    setScope(tier === 'tier_a' ? 'demo' : 'isolated');
    try {
      await api.ensureSession(tier);
      await refreshUsage();
      await refreshDocuments();
    } catch (err: any) {
      addToast(err.message || 'Failed to switch tier', 'error');
    }
  };

  const applyNavScope = (item: NavItem) => {
    if (item === 'tier_a') {
      setCurrentTier('tier_a');
      api.setTier('tier_a');
      setScope('demo');
    } else if (item === 'tier_b') {
      setCurrentTier('tier_b');
      api.setTier('tier_b');
      setScope('isolated');
    }
  };

  const handleSelectNav = (item: NavItem) => {
    if (item === 'tier_a' && isIngesting) {
      addToast(
        'Indexing is still running. Demo Corpus is locked until your document is ready.',
        'warning'
      );
      return;
    }
    setActiveNav(item);
    applyNavScope(item);
    setMobilePane('context');
  };

  const handleStartIngest = async (file: File) => {
    rememberUploadedFile(file);
    setSuggestedQuestions([]);
    setCurrentTier('tier_b');
    api.setTier('tier_b');
    setScope('isolated');
    setIngest({
      jobId: null,
      fileName: file.name,
      stage: 'Validating & uploading document...',
      pct: 15,
      phase: 'uploading',
    });

    try {
      const res = await api.uploadFile(file, 'auto');
      const queued = progressForJobStatus('queued');
      setIngest({
        jobId: res.job_id,
        fileName: file.name,
        stage: queued.stage,
        pct: queued.pct,
        phase: 'processing',
      });
    } catch (err: any) {
      setIngest(null);
      addToast(err.message || 'Failed to upload document', 'error');
    }
  };

  const handleConfirmDelete = async () => {
    setIsDeleting(true);
    try {
      await api.deleteSession();
      setShowDeleteModal(false);
      setDocuments([]);
      setIngest(null);
      setSuggestedQuestions([]);
      clearUploadedFiles();
      // Reset to tier A
      setActiveNav('tier_a');
      await handleSelectTier('tier_a');
      addToast('Session documents and vectors permanently wiped.', 'success');
    } catch (err: any) {
      addToast(err.message || 'Failed to delete session', 'error');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleAskExample = (q: string) => {
    setQueuedQuestion(q);
    setQueuedNonce((n) => n + 1);
    setMobilePane('chat');
  };

  // Resizable divider drag handlers
  const handleMouseDownDivider = (e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingRef.current = true;
    setIsDragging(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const navWidth = isNavCollapsed ? 72 : 224;
      let targetWidth = moveEvent.clientX - navWidth;
      const minW = isNavCollapsed ? MIN_MIDDLE_WIDTH + 152 : MIN_MIDDLE_WIDTH;
      const maxW = Math.max(minW + 50, window.innerWidth - navWidth - MIN_MIDDLE_WIDTH);
      targetWidth = Math.max(minW, Math.min(maxW, targetWidth));
      const base = isNavCollapsed ? targetWidth - 152 : targetWidth;
      setMiddleWidth(base);
      localStorage.setItem('provenance_custom_middle_width', base.toString());
    };

    const handleMouseUp = () => {
      isDraggingRef.current = false;
      setIsDragging(false);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const handleResetDivider = () => {
    setMiddleWidth(null);
    localStorage.removeItem('provenance_custom_middle_width');
    localStorage.removeItem('provenance_middle_width');
  };

  const hideChat = activeNav === 'limits';
  const showContext = !compact || mobilePane === 'context' || hideChat;
  const showChat = !hideChat && (!compact || mobilePane === 'chat');
  const showMobileSwitcher = compact && !hideChat && !keyboardOpen;

  if (surface === 'landing') {
    return (
      <>
        <LandingPage
          theme={theme}
          onToggleTheme={toggleTheme}
          onTryDemo={() => enterWorkspace('demo')}
          onUpload={() => enterWorkspace('upload')}
        />
        <Toast toasts={toasts} onDismiss={removeToast} />
      </>
    );
  }

  return (
    <div className="h-dvh w-full max-w-[100vw] flex flex-col overflow-hidden surface-shell text-foreground transition-colors lg:select-none">
      {compact && (
        <MobileTopBar
          theme={theme}
          onToggleTheme={toggleTheme}
          onBrandClick={returnToOverview}
          usage={usage}
          hasVisitorKey={Boolean(visitorLlm)}
          onAddKey={() => handleSelectNav('tier_b')}
          onOpenLimits={() => handleSelectNav('limits')}
        />
      )}

      {showMobileSwitcher && (
        <MobilePaneSwitch activeNav={activeNav} pane={mobilePane} onChange={setMobilePane} />
      )}

      <div className="flex-1 min-h-0 min-w-0 flex overflow-hidden">
        {/* SECTION 1: Nav Sidebar Menu with Collapse Control */}
        <NavSidebar
          activeNav={activeNav}
          onSelectNav={handleSelectNav}
          theme={theme}
          onToggleTheme={toggleTheme}
          isCollapsed={isNavCollapsed}
          onToggleCollapse={() => setIsNavCollapsed((prev) => !prev)}
          isIngesting={isIngesting}
          onBrandClick={returnToOverview}
        />

        {/* SECTION 2: Details Panel for Selected Menu Item (Equally divided 50/50 by default) */}
        <SectionDetails
          activeNav={activeNav}
          usage={usage}
          scope={scope}
          documents={documents}
          onRequestDelete={() => setShowDeleteModal(true)}
          onToast={addToast}
          onKeyConfigChange={(cfg: LLMConfig | null) => {
            api.setVisitorKeys(cfg);
            setVisitorLlm(cfg);
          }}
          onAskExample={handleAskExample}
          exampleChips={exampleChips}
          width={hideChat || compact ? null : effectiveMiddleWidth}
          isDragging={isDragging}
          theme={theme}
          onToggleTheme={toggleTheme}
          onStartIngest={handleStartIngest}
          ingest={ingest}
          suggestedQuestions={suggestedQuestions}
          onGoToUpload={() => handleSelectNav('tier_b')}
          hasVisitorKey={Boolean(visitorLlm)}
          fillWidth={compact}
          hideHeader={compact}
          concealed={!showContext}
        />

        {/* INTERACTIVE RESIZABLE DIVIDER LINE (Between Section 2 and Section 3) */}
        {!hideChat && !compact && (
        <div
          onMouseDown={handleMouseDownDivider}
          onDoubleClick={handleResetDivider}
          className="w-2 hover:w-2.5 h-full shrink-0 bg-transparent hover:bg-primary/30 active:bg-primary/60 transition-all cursor-col-resize relative flex items-center justify-center group select-none z-20"
          title="Drag to resize middle section & chatbox • Double-click to reset to default 50/50 split"
        >
          <div className="w-[1px] h-full bg-border group-hover:bg-primary transition-colors" />
          <div className="absolute size-4 rounded-full bg-card border border-border shadow-sm flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
            <div className="w-1.5 h-2 border-x border-muted-foreground/60" />
          </div>
        </div>
        )}

        {/* SECTION 3: Primary Chatbox Canvas (Equally divided 50/50 by default, attached to borders) */}
        <main
          className={
            showChat
              ? compact
                ? 'flex min-h-0 min-w-0 w-full max-w-full flex-1 flex-col overflow-hidden'
                : 'flex min-h-0 min-w-[400px] flex-1 basis-0 flex-col overflow-hidden'
              : 'hidden'
          }
          aria-hidden={!showChat}
        >
          <ChatContainer
            scope={scope}
            exampleChips={exampleChips}
            queuedQuestion={queuedQuestion}
            queuedNonce={queuedNonce}
            onUsageUpdate={refreshUsage}
            onToast={addToast}
            isIngesting={isIngesting}
            ingestPct={ingest?.pct}
            documentCount={documents.length}
            activeDocName={activeDocName}
            llmProvider={visitorLlm ? visitorLlm.provider : usage?.owner_llm_provider}
            llmModel={visitorLlm ? visitorLlm.model : usage?.owner_llm_model}
            activeNav={activeNav}
            onGoToUpload={() => handleSelectNav('tier_b')}
            usage={usage}
            hasVisitorKey={Boolean(visitorLlm)}
            onOpenLimits={() => handleSelectNav('limits')}
            compact={compact}
            onShowContext={() => setMobilePane('context')}
          />
        </main>
      </div>

      {!compact && <SectionFooter />}

      {compact && !keyboardOpen && (
        <MobileTabBar
          activeNav={activeNav}
          onSelectNav={handleSelectNav}
          isIngesting={isIngesting}
        />
      )}

      {/* Delete Confirmation Modal */}
      <DeleteModal
        isOpen={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        onConfirm={handleConfirmDelete}
        isDeleting={isDeleting}
      />

      {/* Toast Notification Hub */}
      <Toast
        toasts={toasts}
        onDismiss={removeToast}
        className={
          compact && !keyboardOpen
            ? 'bottom-[calc(4.25rem+env(safe-area-inset-bottom))]'
            : undefined
        }
      />
    </div>
  );
}

export default App;
