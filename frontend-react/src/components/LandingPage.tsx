import React, { useEffect, useState } from 'react';
import {
  ArrowRight,
  Check,
  Eye,
  FileText,
  KeyRound,
  Loader2,
  Moon,
  Shield,
  Sun,
  Timer,
  Unplug,
  UploadCloud,
} from 'lucide-react';
import { Button } from './ui/button';
import logoImg from '../assets/logo.png';
import { ALLOWANCE_DEFAULTS } from '../lib/quota';
import { persistTermsAccepted, TermsModal } from './TermsModal';

interface LandingPageProps {
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onTryDemo: () => void;
  onUpload: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  theme,
  onToggleTheme,
  onTryDemo,
  onUpload,
}) => {
  const [termsOpen, setTermsOpen] = useState(false);

  return (
    <div className="min-h-screen w-full surface-shell text-foreground">
      <a
        href="#paths"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-sm"
      >
        Skip to how you can use it
      </a>

      <header className="sticky top-0 z-40 border-b border-border/80 surface-header backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 sm:px-8">
          <div className="flex items-center gap-2 min-w-0">
            <img src={logoImg} alt="" className="size-11 rounded-lg object-contain shrink-0" />
            <div className="min-w-0">
              <p
                className="truncate text-[15px] font-bold leading-tight tracking-tight"
                style={{ fontFamily: "'Poppins', sans-serif" }}
              >
                Provenance RAG
              </p>
              <p className="hidden text-[11px] text-muted-foreground sm:block">Cited answers. Capped spend.</p>
            </div>
          </div>

          <nav className="hidden items-center gap-6 text-xs font-medium text-muted-foreground md:flex">
            <a href="#paths" className="hover:text-foreground transition-colors">
              Paths
            </a>
            <a href="#guards" className="hover:text-foreground transition-colors">
              Guards &amp; limits
            </a>
          </nav>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              onClick={onToggleTheme}
              aria-label={theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme'}
              className="size-9"
            >
              {theme === 'light' ? <Moon className="size-4" /> : <Sun className="size-4" />}
            </Button>
            <Button size="sm" onClick={onTryDemo} className="hidden sm:inline-flex">
              Try the demo
            </Button>
          </div>
        </div>
      </header>

      <main>
        <section className="flex min-h-[calc(100svh-4rem)] items-center">
          <div className="mx-auto grid w-full max-w-6xl gap-10 px-5 py-10 sm:px-8 md:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] md:items-center md:gap-12">
            <div className="space-y-6">
              <h1
                className="text-[2.15rem] font-bold leading-[1.12] tracking-tight text-foreground sm:text-5xl"
                style={{ fontFamily: "'Poppins', sans-serif" }}
              >
                Ask a filing.
                <br />
                Get an answer you can trace.
              </h1>
              <p className="max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-[15px]">
                A three-path retrieval system with owner spend caps, isolated sessions, and
                citations — or a refusal. Start on the demo 10-Ks with nothing to paste. Upload
                your own PDF when you are ready.
              </p>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button size="lg" onClick={onTryDemo} className="gap-2">
                  Try the demo
                  <ArrowRight className="size-4" />
                </Button>
                <Button size="lg" variant="outline" onClick={onUpload} className="gap-2">
                  <UploadCloud className="size-4" />
                  Upload a PDF
                </Button>
              </div>
              <p className="text-[11px] text-muted-foreground">
                No keys required for the demo. Owner-funded answers are capped at{' '}
                {ALLOWANCE_DEFAULTS.ownerQuestions} per day on this connection.
              </p>
            </div>

            <div className="relative h-full min-h-[22rem] lg:min-h-[26rem]">
              <DemoStatusBadge />
              <div aria-hidden="true" className="h-full">
                <WorkspacePreview />
              </div>
            </div>
          </div>
        </section>

        <section id="paths" className="scroll-mt-20 border-t border-border/80">
          <div className="mx-auto max-w-6xl px-5 py-10 sm:px-8 sm:py-12">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  Three paths
                </p>
                <h2
                  className="mt-1 text-xl font-bold tracking-tight sm:text-2xl"
                  style={{ fontFamily: "'Poppins', sans-serif" }}
                >
                  Nothing to paste, your PDF, or your LLM key.
                </h2>
              </div>
              <p className="max-w-md text-xs leading-relaxed text-muted-foreground">
                Embeddings and rerank stay on the owner Cohere key. You only bring a parser or
                an LLM key if you want to.
              </p>
            </div>

            <div className="mt-6 grid gap-3 md:grid-cols-3">
              <PathCard
                kicker="A · Demo"
                title="Ask Apple 10-Ks"
                icon={Eye}
                lines={[
                  'You bring nothing',
                  'Cited answers on the pre-indexed corpus',
                  'Owner pays embed, rerank, and answers',
                ]}
                cta="Open the corpus"
                onClick={onTryDemo}
                emphasized
              />
              <PathCard
                kicker="B · Upload"
                title="Your document"
                icon={UploadCloud}
                lines={[
                  `${ALLOWANCE_DEFAULTS.docs} PDFs · ${ALLOWANCE_DEFAULTS.pages} pages, isolated to this session`,
                  'Parse, index, then ask — never mixed into the demo corpus',
                  'Owner pays embed, rerank, and answers within caps',
                ]}
                cta="Upload a PDF"
                onClick={onUpload}
              />
              <PathCard
                kicker="C · BYOK"
                title="Your LLM key"
                icon={KeyRound}
                lines={[
                  'Groq, OpenAI, or Anthropic — in RAM only, never disk or logs',
                  `${ALLOWANCE_DEFAULTS.ownQuestions} questions on your model`,
                  'Owner pays embed and rerank only',
                ]}
                cta="Paste a key on upload"
                onClick={onUpload}
              />
            </div>
          </div>
        </section>

        <section id="guards" className="scroll-mt-20 border-t border-border/80 bg-card/30">
          <div className="mx-auto max-w-6xl px-5 py-10 sm:px-8 sm:py-12">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  Guards &amp; limits
                </p>
                <h2
                  className="mt-1 text-xl font-bold tracking-tight sm:text-2xl"
                  style={{ fontFamily: "'Poppins', sans-serif" }}
                >
                  A public demo that cannot quietly drain a wallet or leak a key.
                </h2>
              </div>
              <p className="max-w-md text-xs leading-relaxed text-muted-foreground">
                Same numbers the workspace meter uses. Scope is derived on the server. Weak
                retrieval is refused, not dressed up.
              </p>
            </div>

            <div className="mt-6 grid gap-3 lg:grid-cols-[1.05fr_0.95fr]">
              <ul className="grid gap-2 sm:grid-cols-2">
                <GuardChip
                  icon={Eye}
                  title="No keys to start"
                  body="Judge retrieval on Apple 10-Ks before you upload."
                />
                <GuardChip
                  icon={FileText}
                  title="Cited, or it refuses"
                  body="Not-found gate runs before the LLM. Generation must cite."
                />
                <GuardChip
                  icon={Timer}
                  title="Two-hour TTL wipe"
                  body="Vectors, SQL, and parses go on expiry, tab close, or delete."
                />
                <GuardChip
                  icon={Unplug}
                  title="Uploads stay isolated"
                  body="Your PDF never joins the demo. No visitor URL, so no SSRF."
                />
                <GuardChip
                  icon={Shield}
                  title="Caps before the call"
                  body="Session, IP, daily jobs, and a kill switch. Budget gone → it says so."
                />
                <GuardChip
                  icon={KeyRound}
                  title="Keys are not state"
                  body="Parser key for the job, LLM key for the request. Then shredded."
                />
              </ul>

              <div className="rounded-xl border border-border bg-card/70 overflow-hidden">
                <div className="grid grid-cols-2 sm:grid-cols-3">
                  <LimitStat
                    value={`${ALLOWANCE_DEFAULTS.ownerQuestions}/day`}
                    label="Owner answers / connection"
                  />
                  <LimitStat
                    value={`${ALLOWANCE_DEFAULTS.ownQuestions}`}
                    label="Your-key answers / session"
                  />
                  <LimitStat
                    value={`${ALLOWANCE_DEFAULTS.docs} · ${ALLOWANCE_DEFAULTS.pages}`}
                    label="Docs · pages"
                  />
                  <LimitStat
                    value={`${ALLOWANCE_DEFAULTS.requestsPerMinute}/min`}
                    label="Requests / IP"
                  />
                  <LimitStat value="10/day" label="Uploads / IP" />
                  <LimitStat value="2h" label="Then wipe" />
                </div>
                <p className="border-t border-border px-4 py-3 text-[11px] leading-relaxed text-muted-foreground">
                  Pasted parser or LLM keys transit this host in memory for that job or request.
                  The demo corpus needs no key.{' '}
                  <button
                    type="button"
                    onClick={() => setTermsOpen(true)}
                    className="underline underline-offset-2 hover:text-foreground"
                  >
                    Terms
                  </button>
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border surface-footer">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-8 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p>Provenance RAG · hybrid access · citations required</p>
          <div className="flex flex-wrap items-center gap-4">
            <button
              type="button"
              onClick={() => setTermsOpen(true)}
              className="hover:text-foreground text-left"
            >
              Terms &amp; privacy
            </button>
            <button type="button" onClick={onTryDemo} className="hover:text-foreground text-left">
              Open workspace
            </button>
          </div>
        </div>
      </footer>
      <TermsModal
        open={termsOpen}
        onClose={() => setTermsOpen(false)}
        onAccept={() => {
          persistTermsAccepted(true);
          setTermsOpen(false);
        }}
      />
    </div>
  );
};

function PathCard({
  kicker,
  title,
  icon: Icon,
  lines,
  cta,
  onClick,
  emphasized,
}: {
  kicker: string;
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  lines: string[];
  cta: string;
  onClick: () => void;
  emphasized?: boolean;
}) {
  return (
    <article
      className={`flex flex-col rounded-xl border p-4 ${
        emphasized ? 'border-primary/40 bg-primary/5' : 'border-border bg-card/70'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground">
          {kicker}
        </span>
        <Icon className="size-4 text-primary shrink-0" />
      </div>
      <h3 className="mt-2 text-base font-semibold tracking-tight">{title}</h3>
      <ul className="mt-3 space-y-1.5 text-xs leading-relaxed text-muted-foreground">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <Button onClick={onClick} variant={emphasized ? 'default' : 'outline'} className="mt-4 w-full">
        {cta}
      </Button>
    </article>
  );
}

function GuardChip({
  icon: Icon,
  title,
  body,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
}) {
  return (
    <li className="flex gap-2.5 rounded-xl border border-border bg-card/70 px-3 py-3">
      <Icon className="mt-0.5 size-3.5 text-primary shrink-0" />
      <div className="min-w-0">
        <p className="text-sm font-semibold leading-tight">{title}</p>
        <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{body}</p>
      </div>
    </li>
  );
}

function LimitStat({ value, label }: { value: string; label: string }) {
  return (
    <div className="px-4 py-3">
      <p className="font-mono text-sm font-semibold text-foreground">{value}</p>
      <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{label}</p>
    </div>
  );
}

function DemoStatusBadge() {
  return (
    <p className="absolute -top-3 left-3 z-10 inline-flex items-center gap-2 rounded-md border border-emerald-500/25 bg-background/95 px-2.5 py-1 text-[11px] shadow-sm backdrop-blur-md">
      <span className="relative flex size-1.5 shrink-0" aria-hidden="true">
        <span className="absolute inset-0 rounded-full bg-emerald-500/70 animate-ping" />
        <span className="relative size-1.5 rounded-full bg-emerald-500" />
      </span>
      <span className="font-semibold tracking-wide text-foreground">Live demo</span>
      <span className="hidden h-3 w-px bg-border sm:block" aria-hidden="true" />
      <span className="hidden text-muted-foreground sm:inline">No account</span>
      <span className="hidden text-border sm:inline" aria-hidden="true">
        /
      </span>
      <span className="hidden text-muted-foreground sm:inline">Wiped on TTL</span>
    </p>
  );
}

const PREVIEW_QUESTION = 'What was net sales in 2024?';
const PREVIEW_ANSWER =
  'Net sales were $391.0 billion, taken from the consolidated statements — not from model memory.';
const TRACE_STEPS = [
  'Safety screen',
  'Embed query',
  'Hybrid retrieve',
  'Rerank + not-found gate',
  'Generate with citations',
];

type PreviewPhase = 'pick' | 'click' | 'ask' | 'trace' | 'answer' | 'cite' | 'source';

function WorkspacePreview() {
  const [phase, setPhase] = useState<PreviewPhase>('pick');
  const [traceIdx, setTraceIdx] = useState(-1);
  const [typed, setTyped] = useState('');

  useEffect(() => {
    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) {
      setPhase('source');
      setTraceIdx(TRACE_STEPS.length - 1);
      setTyped(PREVIEW_ANSWER);
      return;
    }

    let cancelled = false;
    const wait = (ms: number) =>
      new Promise<void>((resolve) => {
        window.setTimeout(resolve, ms);
      });

    const run = async () => {
      while (!cancelled) {
        setPhase('pick');
        setTraceIdx(-1);
        setTyped('');
        await wait(700);
        if (cancelled) return;
        setPhase('click');
        await wait(380);
        if (cancelled) return;
        setPhase('ask');
        await wait(420);
        if (cancelled) return;
        setPhase('trace');
        for (let i = 0; i < TRACE_STEPS.length; i += 1) {
          setTraceIdx(i);
          await wait(560);
          if (cancelled) return;
        }
        setPhase('answer');
        for (let i = 1; i <= PREVIEW_ANSWER.length; i += 1) {
          setTyped(PREVIEW_ANSWER.slice(0, i));
          await wait(14);
          if (cancelled) return;
        }
        await wait(480);
        if (cancelled) return;
        setPhase('cite');
        await wait(720);
        if (cancelled) return;
        setPhase('source');
        await wait(3200);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  const asked = phase !== 'pick' && phase !== 'click';
  const showTrace = phase === 'trace' || phase === 'answer' || phase === 'cite' || phase === 'source';
  const showCite = phase === 'cite' || phase === 'source';
  const showSource = phase === 'source';

  return (
    <div className="h-full rounded-xl border border-border bg-card shadow-sm overflow-hidden flex flex-col">
      <div className="flex h-10 items-center gap-2 border-b border-border px-3 surface-header shrink-0">
        <span className="size-2 rounded-full bg-muted-foreground/30" />
        <span className="size-2 rounded-full bg-muted-foreground/30" />
        <span className="size-2 rounded-full bg-muted-foreground/30" />
        <span className="ml-2 text-[10px] font-medium text-muted-foreground">Demo corpus · Form 10-K</span>
        <span className="ml-auto text-[10px] font-medium text-primary">
          {phase === 'trace' ? 'Tracing…' : phase === 'source' ? 'Cited' : 'Copilot'}
        </span>
      </div>
      <div className="grid min-h-[280px] flex-1 grid-cols-[72px_1fr] sm:grid-cols-[88px_minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <div className="border-r border-border p-2 space-y-1.5 surface-panel">
          <div className="h-7 rounded-md bg-primary" />
          <div className="h-7 rounded-md bg-muted" />
          <div className="h-7 rounded-md bg-muted" />
        </div>
        <div className="hidden border-r border-border p-3 sm:block surface-inset">
          <p className="text-[10px] font-semibold text-muted-foreground">Example questions</p>
          <div className="mt-2 space-y-1.5">
            <div
              className={`rounded-md border px-2 py-1.5 text-[10px] transition-all duration-300 ${
                phase === 'click'
                  ? 'scale-[0.98] border-primary bg-primary text-primary-foreground shadow-sm'
                  : asked
                    ? 'border-primary/40 bg-primary/10 text-foreground'
                    : 'border-border bg-card text-foreground'
              }`}
            >
              {PREVIEW_QUESTION}
            </div>
            <div className="rounded-md border border-border/70 px-2 py-1.5 text-[10px] text-muted-foreground">
              How did Services grow year over year?
            </div>
            <div className="rounded-md border border-border/70 px-2 py-1.5 text-[10px] text-muted-foreground">
              What is not in this filing?
            </div>
          </div>
        </div>
        <div className="relative p-3 space-y-2.5 overflow-hidden">
          {asked && (
            <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 animate-in fade-in slide-in-from-bottom-1 duration-300">
              <p className="text-[10px] text-muted-foreground">You</p>
              <p className="text-xs font-medium">{PREVIEW_QUESTION}</p>
            </div>
          )}

          {showTrace && (
            <div className="rounded-lg border border-border bg-card/80 px-2.5 py-2 space-y-1">
              {TRACE_STEPS.map((label, i) => {
                const done = i < traceIdx || (i === traceIdx && phase !== 'trace');
                const active = phase === 'trace' && i === traceIdx;
                return (
                  <div
                    key={label}
                    className={`flex items-center gap-1.5 text-[10px] transition-colors ${
                      done ? 'text-foreground' : active ? 'text-primary' : 'text-muted-foreground/50'
                    }`}
                  >
                    {done ? (
                      <Check className="size-3 text-emerald-500 shrink-0" />
                    ) : active ? (
                      <Loader2 className="size-3 animate-spin text-primary shrink-0" />
                    ) : (
                      <span className="size-3 rounded-full border border-border shrink-0" />
                    )}
                    <span className={active ? 'font-medium' : ''}>{label}</span>
                  </div>
                );
              })}
            </div>
          )}

          {(phase === 'answer' || showCite) && (
            <div className="rounded-lg border border-primary/20 bg-primary/5 px-3 py-2">
              <p className="text-[10px] text-muted-foreground">Answer · cited</p>
              <p className="mt-1 text-xs leading-relaxed">
                {typed}
                {phase === 'answer' && typed.length < PREVIEW_ANSWER.length && (
                  <span className="ml-px inline-block h-3 w-[1px] bg-primary align-middle animate-pulse" />
                )}{' '}
                {showCite && (
                  <span
                    className={`inline-flex items-center justify-center font-mono text-[10px] font-bold px-1 py-px mx-0.5 rounded bg-amber-500/15 text-amber-600 border border-amber-500/30 transition-all ${
                      phase === 'cite' ? 'scale-125 ring-2 ring-amber-400/70' : 'scale-100'
                    }`}
                  >
                    [1]
                  </span>
                )}
              </p>
            </div>
          )}

          {showSource && (
            <div className="rounded-lg border border-amber-500/30 bg-card px-3 py-2 shadow-sm animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[10px] font-semibold text-amber-600">Source [1] · traced</p>
                <span className="text-[10px] font-mono text-muted-foreground">p. 31</span>
              </div>
              <p className="mt-1 text-[10px] text-muted-foreground">Form 10-K · Item 8 · Consolidated statements</p>
              <p className="mt-1.5 text-[11px] leading-relaxed text-foreground">
                “Net sales were{' '}
                <mark className="rounded-sm bg-amber-500/25 px-0.5 text-foreground">
                  $391,035 million
                </mark>{' '}
                for 2024, compared with $383,285 million for 2023.”
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
