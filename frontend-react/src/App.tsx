import React, { useState, useEffect, useRef } from 'react';
import { NavSidebar, NavItem } from './components/NavSidebar';
import { SectionDetails } from './components/SectionDetails';
import { ChatContainer } from './components/ChatContainer';
import { SectionFooter } from './components/SectionFooter';
import { DeleteModal } from './components/DeleteModal';
import { Database } from 'lucide-react';
import { Toast, ToastMessage } from './components/Toast';
import { AccessTier, UsageInfo, ExampleQuestion, UploadedDoc, LLMConfig } from './types';
import { api } from './lib/api';

const DEFAULT_MIDDLE_WIDTH = 480;
const MIN_MIDDLE_WIDTH = 400;

export function App() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('provenance_theme_v2');
    return (saved as 'light' | 'dark') || 'dark';
  });
  const [activeNav, setActiveNav] = useState<NavItem>('tier_a');
  const [currentTier, setCurrentTier] = useState<AccessTier>('tier_a');
  const [scope, setScope] = useState<string>('demo');
  const [usage, setUsage] = useState<UsageInfo | null>(null);
  const [exampleChips, setExampleChips] = useState<ExampleQuestion[]>([]);
  const [documents, setDocuments] = useState<UploadedDoc[]>([]);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [activeDocName, setActiveDocName] = useState<string>('');
  const [queuedQuestion, setQueuedQuestion] = useState<string | null>(null);
  const [queuedNonce, setQueuedNonce] = useState(0);
  const [visitorLlm, setVisitorLlm] = useState<LLMConfig | null>(null);

  // Nav sidebar collapse state
  const [isNavCollapsed, setIsNavCollapsed] = useState<boolean>(false);

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
      setDocuments(docs);
    } catch {
      // Ignored
    }
  };

  // Initialize session on mount & register automatic unload/reload cleanup listeners
  useEffect(() => {
    const initApp = async () => {
      try {
        // If previous session left uploaded vectors/documents, purge them immediately
        const previousSession = sessionStorage.getItem('provenance_active_session');
        if (previousSession) {
          await api.purgeSession(previousSession);
        }

        const sess = await api.createSession('tier_a');
        setScope(sess.scope || 'demo');
        refreshUsage();
        const chips = await api.getExamples();
        setExampleChips(chips);
        refreshDocuments();
      } catch (err: any) {
        addToast(err.message || 'Failed to initialize session', 'error');
      }
    };

    initApp();

    // Register browser close/unload lifecycle listeners to auto-wipe vectors from Qdrant
    const handleUnload = () => {
      api.purgeOnUnload();
    };

    window.addEventListener('pagehide', handleUnload);
    window.addEventListener('beforeunload', handleUnload);

    return () => {
      window.removeEventListener('pagehide', handleUnload);
      window.removeEventListener('beforeunload', handleUnload);
    };
  }, []);

  const handleSelectTier = async (tier: AccessTier) => {
    setCurrentTier(tier);
    api.setTier(tier);
    try {
      const sess = await api.createSession(tier);
      setScope(sess.scope || (tier === 'tier_a' ? 'demo' : 'isolated'));
      refreshUsage();
      refreshDocuments();
    } catch (err: any) {
      addToast(err.message || 'Failed to switch tier', 'error');
    }
  };

  const handleConfirmDelete = async () => {
    setIsDeleting(true);
    try {
      await api.deleteSession();
      setShowDeleteModal(false);
      setDocuments([]);
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

  const indexedDocCount = documents.length + 3;

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden surface-shell text-foreground transition-colors select-none">
      <div className="flex-1 min-h-0 flex overflow-hidden">
        {/* SECTION 1: Nav Sidebar Menu with Collapse Control */}
        <NavSidebar
          activeNav={activeNav}
          onSelectNav={(item) => {
            setActiveNav(item);
            if (item === 'tier_a' || item === 'tier_b') {
              handleSelectTier(item);
            }
          }}
          theme={theme}
          onToggleTheme={toggleTheme}
          isCollapsed={isNavCollapsed}
          onToggleCollapse={() => setIsNavCollapsed((prev) => !prev)}
        />

        {/* SECTION 2: Details Panel for Selected Menu Item (Equally divided 50/50 by default) */}
        <SectionDetails
          activeNav={activeNav}
          usage={usage}
          scope={scope}
          documents={documents}
          onUploadSuccess={() => {
            refreshDocuments();
            refreshUsage();
          }}
          onRequestDelete={() => setShowDeleteModal(true)}
          onToast={addToast}
          onKeyConfigChange={(cfg: LLMConfig | null) => {
            api.setVisitorKeys(cfg);
            setVisitorLlm(cfg);
          }}
          onAskExample={handleAskExample}
          exampleChips={exampleChips}
          width={effectiveMiddleWidth}
          isDragging={isDragging}
          theme={theme}
          onToggleTheme={toggleTheme}
          onIngestStateChange={(ingesting, docName) => {
            setIsIngesting(ingesting);
            if (docName) setActiveDocName(docName);
          }}
        />

        {/* INTERACTIVE RESIZABLE DIVIDER LINE (Between Section 2 and Section 3) */}
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

        {/* SECTION 3: Primary Chatbox Canvas (Equally divided 50/50 by default, attached to borders) */}
        <main className="flex-1 basis-0 min-w-[400px] flex flex-col h-full overflow-hidden">
          <ChatContainer
            scope={scope}
            exampleChips={exampleChips}
            queuedQuestion={queuedQuestion}
            queuedNonce={queuedNonce}
            onUsageUpdate={refreshUsage}
            onToast={addToast}
            isIngesting={isIngesting}
            documentCount={documents.length}
            activeDocName={activeDocName || documents[0]?.filename}
            llmProvider={visitorLlm ? visitorLlm.provider : usage?.owner_llm_provider}
            llmModel={visitorLlm ? visitorLlm.model : usage?.owner_llm_model}
          />
        </main>
      </div>

      <SectionFooter>
        <span
          className="flex items-center gap-1 font-mono text-[10px] text-muted-foreground"
          title={`${indexedDocCount} total docs indexed`}
        >
          <Database className="size-3 shrink-0" />
          <span>{indexedDocCount} docs</span>
        </span>
      </SectionFooter>

      {/* Delete Confirmation Modal */}
      <DeleteModal
        isOpen={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        onConfirm={handleConfirmDelete}
        isDeleting={isDeleting}
      />

      {/* Toast Notification Hub */}
      <Toast toasts={toasts} onDismiss={removeToast} />
    </div>
  );
}

export default App;
