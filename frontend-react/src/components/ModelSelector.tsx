import React, { useState, useEffect } from 'react';
import {
  Cpu,
  Laptop,
  Cloud,
  Check,
  AlertTriangle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Key,
  Eye,
  EyeOff,
  RefreshCw,
  Sparkles,
  Server,
  ShieldCheck,
  Edit3,
  Copy,
} from 'lucide-react';
import { Button } from './ui/button';
import { LLMConfig } from '../types';
import { api } from '../lib/api';
import { formatModelDisplayName, formatDefaultModelLabel } from '../lib/modelUtils';

export interface ModelSelectorProps {
  config: LLMConfig | null;
  onChange: (config: LLMConfig | null) => void;
  onToast: (msg: string, type: 'info' | 'success' | 'warning' | 'error') => void;
  sectionContext?: 'demo' | 'upload' | 'standalone';
  defaultModel?: string;
  defaultProvider?: string;
  isProduction?: boolean;
}

interface ModelItem {
  id: string;
  label: string;
  desc: string;
}

const CLOUD_MODELS: Record<string, ModelItem[]> = {
  groq: [
    { id: 'openai/gpt-oss-120b', label: 'GPT-OSS 120B', desc: '120B parameter reasoning model on Groq' },
    { id: 'llama-3.3-70b-versatile', label: 'Llama 3.3 70B Versatile', desc: 'Recommended: 128k context, top reasoning' },
    { id: 'llama-3.1-70b-versatile', label: 'Llama 3.1 70B Versatile', desc: '128k context, high quality' },
    { id: 'llama-3.1-8b-instant', label: 'Llama 3.1 8B Instant', desc: 'Ultra-low latency, 128k context' },
    { id: 'deepseek-r1-distill-llama-70b', label: 'DeepSeek R1 Distill 70B', desc: 'Advanced reasoning and mathematical synthesis' },
    { id: 'mixtral-8x7b-32768', label: 'Mixtral 8x7B 32k', desc: 'Mixture-of-Experts high throughput' },
    { id: 'gemma2-9b-it', label: 'Google Gemma 2 9B IT', desc: 'Google lightweight high-efficiency instruction model' },
    { id: 'qwen-2.5-32b', label: 'Qwen 2.5 32B', desc: 'Strong multilingual and technical coding reasoning' },
  ],
  openai: [
    { id: 'gpt-4o', label: 'GPT-4o', desc: 'Flagship multimodal high-intelligence model' },
    { id: 'gpt-4o-mini', label: 'GPT-4o Mini', desc: 'Fast, lightweight and cost-efficient' },
    { id: 'o1-mini', label: 'o1-mini', desc: 'Reasoning model for math and code' },
    { id: 'o3-mini', label: 'o3-mini', desc: 'Next-generation low-latency reasoning' },
    { id: 'gpt-4-turbo', label: 'GPT-4 Turbo', desc: '128k context window with vision' },
  ],
  anthropic: [
    { id: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet', desc: 'Benchmark-leading coding and analysis' },
    { id: 'claude-3-5-haiku-20241022', label: 'Claude 3.5 Haiku', desc: 'Rapid execution and responsiveness' },
    { id: 'claude-3-opus-20240229', label: 'Claude 3 Opus', desc: 'Deep synthesis for complex reasoning' },
  ],
  gemini: [
    { id: 'gemini-1.5-flash-latest', label: 'Gemini 1.5 Flash', desc: 'Ultra-fast multi-turn conversational speed' },
    { id: 'gemini-1.5-pro-latest', label: 'Gemini 1.5 Pro', desc: '1-million token context window' },
    { id: 'gemini-2.0-flash-exp', label: 'Gemini 2.0 Flash Experimental', desc: 'Next-gen real-time intelligence' },
  ],
  mistral: [
    { id: 'mistral-small-latest', label: 'Mistral Small', desc: 'Cost-effective high precision' },
    { id: 'mistral-large-latest', label: 'Mistral Large', desc: 'Top-tier reasoning capability' },
    { id: 'codestral-latest', label: 'Codestral', desc: 'Specialized for code & structured docs' },
  ],
};

const POPULAR_LOCAL_MODELS = [
  'qwen2.5:1.5b',
  'llama3.2:3b',
  'llama3.1:8b',
  'qwen2.5:7b',
  'mistral:latest',
  'deepseek-r1:8b',
  'phi4:latest',
];

export function getModelTierInfo(modelName: string): {
  tier: string;
  badge: string;
  desc: string;
  colorClass: string;
} {
  const m = (modelName || '').toLowerCase();
  const isMicro =
    /0\.[0-9]+b|1b|1\.[0-9]+b|2b|2\.[0-9]+b|3b|3\.[0-9]+b|phi[-_]?3|tinyllama/.test(m) ||
    m.includes('1.5b') ||
    m.includes('3b') ||
    m.includes('1b');

  if (isMicro) {
    return {
      tier: 'Compact & Fast (≤3B)',
      badge: '⚡ Instant Speed',
      desc: 'Extremely fast responses. Best for quick summaries and straightforward questions.',
      colorClass: 'text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20',
    };
  }

  const isMid =
    /7b|8b|9b|10b|11b|12b|13b|14b|mistral|gemma/.test(m) ||
    ['7b', '8b', '9b', '12b', '14b'].some((t) => m.includes(t));

  if (isMid) {
    return {
      tier: 'Balanced AI (7B–14B)',
      badge: '⚖️ Balanced Speed & Detail',
      desc: 'Great everyday balance between fast typing speed and thorough explanations.',
      colorClass: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    };
  }

  return {
    tier: 'Deep Reasoning (70B+ / Flagship)',
    badge: '🧠 Deep Comprehension',
    desc: 'Highest accuracy and depth. Best for complex financial tables and detailed synthesis.',
    colorClass: 'text-blue-600 dark:text-blue-400 bg-blue-500/10 border-blue-500/20',
  };
}

type ModelTab = 'default' | 'local' | 'byok';

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  config,
  onChange,
  onToast,
  sectionContext = 'demo',
  defaultModel = 'openai/gpt-oss-120b',
  defaultProvider = 'groq',
  isProduction = false,
}) => {
  const [isOpen, setIsOpen] = useState(sectionContext === 'standalone');

  // Automatic production detection (server config, VITE_APP_ENV, or cloud origin like render.com)
  const isProd = Boolean(
    isProduction ||
    (import.meta.env.VITE_APP_ENV === 'production') ||
    (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
  );

  // Tab state (in production, local Ollama is disabled so default to cloud AI)
  const initialTab: ModelTab = (!isProd && config?.isLocal)
    ? 'local'
    : config?.key
      ? 'byok'
      : 'default';
  const [activeTab, setActiveTab] = useState<ModelTab>(initialTab);

  // Switch away from local tab if environment is production
  useEffect(() => {
    if (isProd && activeTab === 'local') {
      setActiveTab('default');
    }
  }, [isProd, activeTab]);

  // Local model state
  const [localUrl, setLocalUrl] = useState(config?.baseUrl || 'http://localhost:11434/v1');
  const [localModel, setLocalModel] = useState(config?.isLocal ? config.model : 'llama3.1:8b');
  const [discoveredModels, setDiscoveredModels] = useState<string[]>([]);
  const [isTestingLocal, setIsTestingLocal] = useState(false);
  const [localStatus, setLocalStatus] = useState<{
    tested: boolean;
    success: boolean;
    message: string;
  } | null>(null);

  // Cloud BYOK state
  const [cloudProvider, setCloudProvider] = useState<'groq' | 'openai' | 'anthropic' | 'gemini' | 'mistral'>(
    !config?.isLocal && config?.provider && config.provider !== 'ollama' && config.provider !== 'local'
      ? (config.provider as any)
      : 'groq'
  );
  const [cloudKey, setCloudKey] = useState(config?.key || '');
  const [showKey, setShowKey] = useState(false);
  const [cloudModel, setCloudModel] = useState(
    !config?.isLocal && config?.model ? config.model : 'llama-3.3-70b-versatile'
  );
  const [discoveredCloudModels, setDiscoveredCloudModels] = useState<string[]>([]);
  const [isCustomCloudModel, setIsCustomCloudModel] = useState(false);
  const [customCloudModelValue, setCustomCloudModelValue] = useState('');
  const [isTestingCloud, setIsTestingCloud] = useState(false);
  const [cloudStatus, setCloudStatus] = useState<{
    tested: boolean;
    success: boolean;
    message: string;
  } | null>(null);

  const isKeyVerified = Boolean(
    cloudStatus?.success ||
      (config?.key &&
        config?.provider === cloudProvider &&
        cloudKey === config.key &&
        cloudStatus === null)
  );

  const isLocalVerified = Boolean(
    localStatus?.success ||
      (config?.isLocal &&
        config?.baseUrl === localUrl &&
        localStatus === null)
  );

  // Keep internal state aligned if config prop changes
  useEffect(() => {
    if (config?.isLocal) {
      setActiveTab('local');
      if (config.baseUrl) setLocalUrl(config.baseUrl);
      if (config.model) setLocalModel(config.model);
    } else if (config?.key) {
      setActiveTab('byok');
      setCloudKey(config.key);
      if (config.provider) setCloudProvider(config.provider as any);
      if (config.model) {
        setCloudModel(config.model);
        const known = CLOUD_MODELS[config.provider as any] || [];
        if (!known.some((m) => m.id === config.model)) {
          setIsCustomCloudModel(true);
          setCustomCloudModelValue(config.model);
        }
      }
    } else {
      setActiveTab('default');
    }
  }, [config]);

  // Test local Ollama connection and auto-fetch tags (browser direct + backend fallback)
  const handleTestLocal = async () => {
    setIsTestingLocal(true);
    setLocalStatus(null);
    const cleanUrl = localUrl.trim() || 'http://127.0.0.1:11434/v1';

    // Candidate URLs to probe: try 127.0.0.1 and localhost (prevents IPv6 loopback binding mismatch on Linux)
    const candidateUrls = [cleanUrl];
    if (cleanUrl.includes('localhost')) {
      candidateUrls.push(cleanUrl.replace('localhost', '127.0.0.1'));
    } else if (cleanUrl.includes('127.0.0.1')) {
      candidateUrls.push(cleanUrl.replace('127.0.0.1', 'localhost'));
    }

    // 1. Try direct browser probe first (critical for Render / cloud deployments so client talks to local Ollama directly)
    let isConnected = false;
    let foundModels: string[] = [];
    let workingUrl = cleanUrl;

    for (const cand of candidateUrls) {
      try {
        const probeBase = cand.replace(/\/v1\/?$/, '');
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3500);

        const [resTags, resModels] = await Promise.allSettled([
          fetch(`${probeBase}/api/tags`, { method: 'GET', signal: controller.signal }),
          fetch(`${cand.replace(/\/+$/, '')}/models`, { method: 'GET', signal: controller.signal }),
        ]);
        clearTimeout(timeoutId);

        if (resTags.status === 'fulfilled' && resTags.value.ok) {
          isConnected = true;
          workingUrl = cand;
          const data = await resTags.value.json().catch(() => null);
          if (data && Array.isArray(data.models)) {
            foundModels = data.models.map((m: any) => m.name || m.model).filter(Boolean);
          }
          break;
        } else if (resModels.status === 'fulfilled' && resModels.value.ok) {
          isConnected = true;
          workingUrl = cand;
          const data = await resModels.value.json().catch(() => null);
          if (data && Array.isArray(data.data)) {
            foundModels = data.data.map((m: any) => m.id).filter(Boolean);
          }
          break;
        }
      } catch {
        // Continue to next candidate URL
      }
    }

    if (isConnected) {
      if (workingUrl !== localUrl) {
        setLocalUrl(workingUrl);
      }
      if (foundModels.length > 0) {
        setLocalStatus({
          tested: true,
          success: true,
          message: `Connected directly! Found ${foundModels.length} local model(s) on your machine.`,
        });
        setDiscoveredModels(foundModels);
        if (!foundModels.includes(localModel)) {
          setLocalModel(foundModels[0]);
        }
        onToast(`Connected to local Ollama (${foundModels.length} models found).`, 'success');
      } else {
        // Connected to Ollama server, but user has 0 models pulled yet (total blobs: 0)
        setLocalStatus({
          tested: true,
          success: true,
          message: `Connected to Ollama! However, no models are downloaded yet (0 models found). Run 'ollama pull llama3.2:3b' in your terminal, then scan again.`,
        });
        setDiscoveredModels(['llama3.2:3b', 'llama3.1:8b', 'qwen2.5:3b']);
        onToast('Connected to Ollama! Please run "ollama pull llama3.2:3b" in terminal to download a model.', 'info');
      }
      setIsTestingLocal(false);
      return;
    }

    // 2. Fall back to backend connection test
    try {
      const res = await api.testConnection('ollama', '', cleanUrl);
      if (res.success) {
        setLocalStatus({
          tested: true,
          success: true,
          message: res.models && res.models.length > 0
            ? `Connected! Found ${res.models.length} local model(s).`
            : `Connected to Ollama! Please run 'ollama pull llama3.2:3b' in terminal to download a model.`,
        });
        if (res.models && res.models.length > 0) {
          setDiscoveredModels(res.models);
          if (!res.models.includes(localModel)) {
            setLocalModel(res.models[0]);
          }
        } else {
          setDiscoveredModels(['llama3.2:3b', 'llama3.1:8b', 'qwen2.5:3b']);
        }
        onToast('Successfully connected to local model endpoint.', 'success');
      } else {
        setLocalStatus({
          tested: true,
          success: false,
          message:
            res.message ||
            'Could not connect to local model endpoint. Try using http://127.0.0.1:11434/v1 and ensure OLLAMA_ORIGINS="*" is set.',
        });
        onToast(res.message || 'Local connection failed.', 'error');
      }
    } catch (err: any) {
      setLocalStatus({
        tested: true,
        success: false,
        message: err.message || 'Connection error. Check URL and CORS settings.',
      });
      onToast('Local connection error.', 'error');
    } finally {
      setIsTestingLocal(false);
    }
  };

  // Test Cloud BYOK key
  const handleTestCloud = async () => {
    if (!cloudKey.trim()) {
      onToast('Please enter an API key first.', 'warning');
      return;
    }
    setIsTestingCloud(true);
    setCloudStatus(null);
    try {
      const res = await api.testConnection(cloudProvider, cloudKey.trim());
      if (res.success) {
        let count = 0;
        if (res.models && res.models.length > 0) {
          const filtered = res.models.filter((m) => {
            const lower = m.toLowerCase();
            return (
              !lower.includes('whisper') &&
              !lower.includes('guard') &&
              !lower.includes('tts') &&
              !lower.includes('dall-e') &&
              !lower.includes('embed') &&
              !lower.includes('imagen') &&
              !lower.includes('aqa') &&
              !lower.includes('moderation')
            );
          });
          setDiscoveredCloudModels(filtered);
          count = filtered.length;
          if (!filtered.includes(cloudModel) && filtered.length > 0 && !isCustomCloudModel) {
            const preferred =
              filtered.find((m) => m.includes('llama-3.3') || m.includes('gpt-4o')) || filtered[0];
            setCloudModel(preferred);
          }
        }
        setCloudStatus({
          tested: true,
          success: true,
          message:
            count > 0
              ? `API Key verified (${count} live models available).`
              : 'API Key successfully verified.',
        });
        onToast(`Verified ${cloudProvider.toUpperCase()} key.`, 'success');
      } else {
        setCloudStatus({
          tested: true,
          success: false,
          message: res.message || 'Invalid API key or quota exceeded.',
        });
        onToast(res.message || 'Key validation failed.', 'error');
      }
    } catch (err: any) {
      setCloudStatus({
        tested: true,
        success: false,
        message: err.message || 'Validation error.',
      });
      onToast('Key validation error.', 'error');
    } finally {
      setIsTestingCloud(false);
    }
  };

  // Apply selection
  const handleApply = (tabToApply: ModelTab) => {
    if (tabToApply === 'default') {
      onChange(null);
      api.setVisitorKeys(null);
      const provName = defaultProvider ? defaultProvider.charAt(0).toUpperCase() + defaultProvider.slice(1) : 'Groq';
      onToast(`Switched to Cloud Default (${provName} ${formatModelDisplayName(defaultModel)}).`, 'info');
      setIsOpen(false);
      return;
    }

    if (tabToApply === 'local') {
      if (!isLocalVerified) {
        onToast('Please scan and verify your local Ollama connection before applying.', 'warning');
        return;
      }
      const newConfig: LLMConfig = {
        provider: 'ollama',
        model: localModel.trim() || 'llama3.1:8b',
        key: '',
        baseUrl: localUrl.trim() || 'http://localhost:11434/v1',
        isLocal: true,
      };
      onChange(newConfig);
      api.setVisitorKeys(newConfig);
      onToast(`Switched to Local Model: ${newConfig.model} via ${newConfig.baseUrl}`, 'success');
      setIsOpen(false);
      return;
    }

    if (tabToApply === 'byok') {
      if (!cloudKey.trim()) {
        onToast('Please enter an API key for cloud BYOK.', 'warning');
        return;
      }
      if (!isKeyVerified) {
        onToast('Please verify your API key before applying.', 'warning');
        return;
      }
      const modelToUse = isCustomCloudModel
        ? customCloudModelValue.trim() || cloudModel
        : cloudModel;

      if (!modelToUse) {
        onToast('Please specify a model.', 'warning');
        return;
      }
      const newConfig: LLMConfig = {
        provider: cloudProvider,
        model: modelToUse,
        key: cloudKey.trim(),
        isLocal: false,
      };
      onChange(newConfig);
      api.setVisitorKeys(newConfig);
      onToast(`Switched to ${cloudProvider.toUpperCase()} (${modelToUse}).`, 'success');
      setIsOpen(false);
      return;
    }
  };

  // Human-readable summary badge
  const renderCurrentModelSummary = () => {
    if (config?.isLocal) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 shrink min-w-0 max-w-[150px] sm:max-w-[220px]">
          <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse shrink-0" />
          <Laptop className="size-3 shrink-0" />
          <span className="truncate whitespace-nowrap">Local ({config.model})</span>
        </span>
      );
    }
    if (config?.key) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 shrink min-w-0 max-w-[150px] sm:max-w-[220px]">
          <Key className="size-3 shrink-0" />
          <span className="truncate whitespace-nowrap">BYOK ({config.provider.toUpperCase()}: {config.model})</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary border border-primary/20 shrink min-w-0 max-w-[160px] sm:max-w-[240px]">
        <Sparkles className="size-3 shrink-0" />
        <span className="truncate whitespace-nowrap">{formatDefaultModelLabel(defaultProvider, defaultModel)}</span>
      </span>
    );
  };

  return (
    <div className="w-full rounded-xl border border-border bg-card/60 backdrop-blur-sm overflow-hidden transition-all shadow-sm">
      {/* Header Bar / Summary Clickable */}
      <div
        className="px-3 py-2 sm:px-3.5 sm:py-2.5 flex items-center justify-between cursor-pointer hover:bg-muted/40 transition-colors select-none"
        onClick={() => setIsOpen((prev) => !prev)}
      >
        <div className="flex items-center gap-2 min-w-0 pr-2">
          <Cpu className="size-4 text-primary shrink-0" />
          <span className="text-xs font-semibold text-foreground truncate shrink-0">
            Inference Model
          </span>
          {renderCurrentModelSummary()}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-[11px] text-muted-foreground font-medium hidden sm:inline">
            {isOpen ? 'Close' : 'Change model'}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="size-6 text-muted-foreground"
            onClick={(e) => {
              e.stopPropagation();
              setIsOpen((prev) => !prev);
            }}
          >
            {isOpen ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          </Button>
        </div>
      </div>

      {/* Expanded Panel */}
      {isOpen && (
        <div className="p-2.5 sm:p-3.5 border-t border-border space-y-2.5 sm:space-y-3.5 bg-card/90">
          {/* Tabs (in production: 2 tabs, local Ollama hidden) */}
          <div className={`grid ${isProd ? 'grid-cols-2' : 'grid-cols-3'} gap-1.5 p-1 bg-muted/60 rounded-lg border border-border/50 text-xs font-medium`}>
            <button
              type="button"
              onClick={() => setActiveTab('default')}
              className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md transition-all ${activeTab === 'default'
                  ? 'bg-card text-foreground shadow-xs font-semibold'
                  : 'text-muted-foreground hover:text-foreground'
                }`}
            >
              <Sparkles className="size-3 text-primary" />
              <span>Included Cloud AI</span>
            </button>
            {!isProd && (
              <button
                type="button"
                onClick={() => setActiveTab('local')}
                className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md transition-all ${activeTab === 'local'
                    ? 'bg-card text-foreground shadow-xs font-semibold'
                    : 'text-muted-foreground hover:text-foreground'
                  }`}
              >
                <Laptop className="size-3 text-emerald-500" />
                <span>Local Ollama</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => setActiveTab('byok')}
              className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md transition-all ${activeTab === 'byok'
                  ? 'bg-card text-foreground shadow-xs font-semibold'
                  : 'text-muted-foreground hover:text-foreground'
                }`}
            >
              <Key className="size-3 text-purple-500" />
              <span>Personal API Key</span>
            </button>
          </div>

          {/* TAB 1: DEFAULT OWNER GROQ */}
          {activeTab === 'default' && (
            <div className="space-y-2.5 p-3 rounded-lg border border-border/60 bg-muted/20">
              <div className="flex items-start gap-2.5">
                <ShieldCheck className="size-4 text-primary shrink-0 mt-0.5" />
                <div className="text-xs space-y-1">
                  <div className="font-semibold text-foreground">
                    {defaultProvider ? defaultProvider.charAt(0).toUpperCase() + defaultProvider.slice(1) : 'Groq'} {formatModelDisplayName(defaultModel)} (Fast & Accurate)
                  </div>
                  <p className="text-muted-foreground leading-relaxed">
                    Pre-configured high-speed cloud AI. Included free for all questions with exact source citations and zero setup needed.
                  </p>
                </div>
              </div>
              <Button
                size="sm"
                className="w-full text-xs h-8"
                onClick={() => handleApply('default')}
              >
                Use Included Cloud AI
              </Button>
            </div>
          )}

          {/* TAB 2: LOCAL INFERENCE (OLLAMA / LM STUDIO / VLLM) — Dev/Self-Hosted Only */}
          {!isProd && activeTab === 'local' && (
            <div className="space-y-3 p-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5">
              <div className="flex items-start gap-2">
                <Laptop className="size-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
                <div className="text-xs space-y-0.5">
                  <div className="font-semibold text-foreground">Private Local AI (Ollama)</div>
                  <p className="text-muted-foreground text-[11px]">
                    Runs privately on your own computer. Your questions and document text never leave your machine.
                  </p>
                </div>
              </div>

              {/* Endpoint URL Input */}
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-muted-foreground flex items-center justify-between">
                  <span>Server URL (OpenAI-compatible)</span>
                  <span className="text-[10px] text-muted-foreground font-mono">Default: http://localhost:11434/v1</span>
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={localUrl}
                    onChange={(e) => {
                      setLocalUrl(e.target.value);
                      setLocalStatus(null);
                      setDiscoveredModels([]);
                    }}
                    placeholder="http://localhost:11434/v1"
                    className="flex-1 px-2.5 py-1.5 text-xs font-mono rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={isTestingLocal}
                    onClick={handleTestLocal}
                    className={`h-8 text-xs shrink-0 flex items-center gap-1.5 transition-colors ${
                      localStatus?.success
                        ? 'text-emerald-600 dark:text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
                        : ''
                    }`}
                  >
                    {isTestingLocal ? (
                      <Loader2 className="size-3 animate-spin" />
                    ) : localStatus?.success ? (
                      <Check className="size-3" strokeWidth={2.5} />
                    ) : (
                      <RefreshCw className="size-3" />
                    )}
                    <span>{isTestingLocal ? 'Scanning...' : localStatus?.success ? 'Verified' : 'Connect & Scan'}</span>
                  </Button>
                </div>
              </div>

              {/* Test Status Banner */}
              {localStatus && (
                <div
                  className={`p-2 rounded-md text-xs flex items-center gap-2 ${
                    localStatus.success
                      ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/20'
                      : 'bg-destructive/10 text-destructive border border-destructive/20'
                  }`}
                >
                  {localStatus.success ? (
                    <Check className="size-3.5 shrink-0" />
                  ) : (
                    <AlertTriangle className="size-3.5 shrink-0" />
                  )}
                  <span className="leading-tight">{localStatus.message}</span>
                </div>
              )}

              {/* ONLY SHOW MODELS & APPLY AFTER LOCAL CONNECTION IS VERIFIED */}
              {isLocalVerified ? (
                <div className="space-y-3 pt-1 border-t border-emerald-500/15">
                  {/* Model Input / Selection */}
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <label className="text-[11px] font-semibold text-muted-foreground block">
                        Installed Local Models
                      </label>
                      {discoveredModels.length > 0 && (
                        <span className="text-[9.5px] font-mono text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20 leading-none">
                          {discoveredModels.length} Local Models Found
                        </span>
                      )}
                    </div>
                    {discoveredModels.length > 0 ? (
                      <select
                        value={localModel}
                        onChange={(e) => setLocalModel(e.target.value)}
                        className="w-full px-2.5 py-1.5 text-xs rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                      >
                        <optgroup label="Discovered on your machine">
                          {discoveredModels.map((m) => (
                            <option key={m} value={m}>
                              {m}
                            </option>
                          ))}
                        </optgroup>
                      </select>
                    ) : (
                      <input
                        type="text"
                        value={localModel}
                        onChange={(e) => setLocalModel(e.target.value)}
                        placeholder="llama3.1:8b"
                        className="w-full px-2.5 py-1.5 text-xs font-mono rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                    )}

                    {/* Quick suggestions */}
                    <div className="flex flex-wrap gap-1 pt-1">
                      {POPULAR_LOCAL_MODELS.map((m) => (
                        <button
                          key={m}
                          type="button"
                          onClick={() => setLocalModel(m)}
                          className={`text-[10px] font-mono px-1.5 py-0.5 rounded border transition-colors ${
                            localModel === m
                              ? 'bg-primary text-primary-foreground border-primary'
                              : 'bg-muted/50 text-muted-foreground border-border hover:bg-muted'
                          }`}
                        >
                          {m}
                        </button>
                      ))}
                    </div>

                    {/* Dynamic Model Capability Tier Card */}
                    {(() => {
                      const tierInfo = getModelTierInfo(localModel);
                      return (
                        <div className={`p-2.5 rounded-md border text-xs space-y-1 ${tierInfo.colorClass}`}>
                          <div className="flex items-center justify-between font-semibold">
                            <span>{tierInfo.tier}</span>
                            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-background/50 border border-current/20">
                              {tierInfo.badge}
                            </span>
                          </div>
                          <p className="text-[11px] opacity-90 leading-relaxed">{tierInfo.desc}</p>
                        </div>
                      );
                    })()}
                  </div>

                  <Button
                    size="sm"
                    className="w-full text-xs h-8 bg-emerald-600 hover:bg-emerald-700 text-white font-medium"
                    onClick={() => handleApply('local')}
                  >
                    Apply Local Model ({localModel})
                  </Button>
                </div>
              ) : (
                /* INSTRUCTION CARD (MODELS LOCKED UNTIL CONNECTION IS VERIFIED) */
                <div className="p-3 rounded-lg border border-dashed border-emerald-500/30 bg-emerald-500/5 space-y-2.5">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                    <Laptop className="size-3.5" />
                    <span>How to enable browser access to your Ollama</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    By default, Ollama blocks requests from web browsers. Run one of the commands below in your terminal before scanning:
                  </p>

                  <div className="space-y-1.5 font-mono text-[10.5px]">
                    <div className="p-2 rounded bg-background border border-border/70 flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <span className="text-muted-foreground font-sans text-[10px] font-semibold block mb-0.5">Windows (PowerShell):</span>
                        <code className="text-foreground select-all break-all">$env:OLLAMA_ORIGINS="*" ; ollama serve</code>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard?.writeText('$env:OLLAMA_ORIGINS="*" ; ollama serve');
                          onToast('Copied PowerShell command to clipboard!', 'info');
                        }}
                        className="shrink-0 p-1 text-muted-foreground hover:text-foreground text-[10px] border rounded flex items-center gap-1"
                      >
                        <Copy className="size-3" />
                        <span>Copy</span>
                      </button>
                    </div>

                    <div className="p-2 rounded bg-background border border-border/70 flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <span className="text-muted-foreground font-sans text-[10px] font-semibold block mb-0.5">Windows (Command Prompt):</span>
                        <code className="text-foreground select-all break-all">set OLLAMA_ORIGINS=* && ollama serve</code>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard?.writeText('set OLLAMA_ORIGINS=* && ollama serve');
                          onToast('Copied CMD command to clipboard!', 'info');
                        }}
                        className="shrink-0 p-1 text-muted-foreground hover:text-foreground text-[10px] border rounded flex items-center gap-1"
                      >
                        <Copy className="size-3" />
                        <span>Copy</span>
                      </button>
                    </div>

                    <div className="p-2 rounded bg-background border border-border/70 flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <span className="text-muted-foreground font-sans text-[10px] font-semibold block mb-0.5">macOS / Linux:</span>
                        <code className="text-foreground select-all break-all">sudo systemctl stop ollama ; OLLAMA_ORIGINS="*" ollama serve</code>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard?.writeText('sudo systemctl stop ollama ; OLLAMA_ORIGINS="*" ollama serve');
                          onToast('Copied Linux/macOS command to clipboard!', 'info');
                        }}
                        className="shrink-0 p-1 text-muted-foreground hover:text-foreground text-[10px] border rounded flex items-center gap-1"
                      >
                        <Copy className="size-3" />
                        <span>Copy</span>
                      </button>
                    </div>
                  </div>

                  <p className="text-[10px] text-muted-foreground/80 leading-normal italic">
                    Tip: If you see "address already in use", Ollama is already running in the background. Stop the background service with <code>sudo systemctl stop ollama</code> (or Quit from system tray on Windows) before restarting with origins enabled.
                  </p>

                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={isTestingLocal}
                    onClick={handleTestLocal}
                    className="w-full h-8 text-xs font-medium text-emerald-700 dark:text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/10 gap-1.5"
                  >
                    {isTestingLocal ? <Loader2 className="size-3 animate-spin" /> : <RefreshCw className="size-3" />}
                    <span>{isTestingLocal ? 'Scanning for local models...' : 'Verify & Scan Local Models'}</span>
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: CLOUD BYOK */}
          {activeTab === 'byok' && (
            <div className="space-y-3 p-3 rounded-lg border border-purple-500/20 bg-purple-500/5">
              <div className="flex items-start gap-2">
                <Key className="size-4 text-purple-600 dark:text-purple-400 shrink-0 mt-0.5" />
                <div className="text-xs space-y-0.5">
                  <div className="font-semibold text-foreground">Use Your Own API Key</div>
                  <p className="text-muted-foreground text-[11px]">
                    Connect your personal API key for unlimited questions. Keys stay in your browser and are never saved on our servers.
                  </p>
                </div>
              </div>

              {/* Provider Selection */}
              <div className="grid grid-cols-5 gap-1 text-[11px]">
                {(['groq', 'openai', 'anthropic', 'gemini', 'mistral'] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => {
                      setCloudProvider(p);
                      setCloudModel(CLOUD_MODELS[p]?.[0]?.id || '');
                      setDiscoveredCloudModels([]);
                      setIsCustomCloudModel(false);
                      setCustomCloudModelValue('');
                      setCloudStatus(null);
                      if (config?.provider === p && config?.key) {
                        setCloudKey(config.key);
                      } else {
                        setCloudKey('');
                      }
                    }}
                    className={`py-1 rounded border font-medium capitalize text-center transition-colors ${cloudProvider === p
                        ? 'bg-primary text-primary-foreground border-primary font-semibold'
                        : 'bg-background text-muted-foreground border-border hover:bg-muted'
                      }`}
                  >
                    {p}
                  </button>
                ))}
              </div>

              {/* API Key Input */}
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-muted-foreground block">
                  {cloudProvider.toUpperCase()} API Key
                </label>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={cloudKey}
                    onChange={(e) => {
                      setCloudKey(e.target.value);
                      setCloudStatus(null);
                      setDiscoveredCloudModels([]);
                    }}
                    placeholder={`Enter ${cloudProvider.toUpperCase()} API key`}
                    className="w-full pr-20 pl-2.5 py-1.5 text-xs font-mono rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <div className="absolute right-1 top-1 flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => setShowKey(!showKey)}
                      className="p-1 text-muted-foreground hover:text-foreground"
                    >
                      {showKey ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                    </button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={isTestingCloud || !cloudKey.trim()}
                      onClick={handleTestCloud}
                      className={`h-6 px-2 text-[10px] gap-1 transition-colors ${
                        cloudStatus?.success
                          ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/15'
                          : ''
                      }`}
                    >
                      {isTestingCloud ? (
                        <Loader2 className="size-3 animate-spin" />
                      ) : cloudStatus?.success ? (
                        <>
                          <Check className="size-3" strokeWidth={2.5} />
                          <span>Verified</span>
                        </>
                      ) : (
                        'Verify'
                      )}
                    </Button>
                  </div>
                </div>
              </div>

              {/* Status Banner */}
              {cloudStatus && (
                <div
                  className={`p-2 rounded-md text-xs flex items-center gap-2 ${
                    cloudStatus.success
                      ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/20'
                      : 'bg-destructive/10 text-destructive border border-destructive/20'
                  }`}
                >
                  {cloudStatus.success ? (
                    <Check className="size-3.5 shrink-0" />
                  ) : (
                    <AlertTriangle className="size-3.5 shrink-0" />
                  )}
                  <span className="leading-tight">{cloudStatus.message}</span>
                </div>
              )}

              {/* ONLY SHOW MODELS & APPLY AFTER KEY IS VERIFIED */}
              {isKeyVerified ? (
                <div className="space-y-3 pt-1 border-t border-purple-500/15">
                  {/* Model Dropdown */}
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <label className="text-[11px] font-semibold text-muted-foreground block">
                        Available Models for Verified Key
                      </label>
                      {discoveredCloudModels.length > 0 && (
                        <span className="text-[9.5px] font-mono text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20 leading-none">
                          {discoveredCloudModels.length} Live Models
                        </span>
                      )}
                    </div>
                    <select
                      value={isCustomCloudModel ? '__custom__' : cloudModel}
                      onChange={(e) => {
                        if (e.target.value === '__custom__') {
                          setIsCustomCloudModel(true);
                        } else {
                          setIsCustomCloudModel(false);
                          setCloudModel(e.target.value);
                        }
                      }}
                      className="w-full px-2.5 py-1.5 text-xs rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                      {discoveredCloudModels.length > 0 ? (
                        <optgroup label={`Verified Available on this API Key (${discoveredCloudModels.length})`}>
                          {discoveredCloudModels.map((m) => {
                            const known = (CLOUD_MODELS[cloudProvider] || []).find((k) => k.id === m);
                            return (
                              <option key={`live-${m}`} value={m}>
                                {known ? `${known.label} (${m})` : m}
                              </option>
                            );
                          })}
                        </optgroup>
                      ) : (
                        <optgroup label={`Available Models for ${cloudProvider.toUpperCase()}`}>
                          {(CLOUD_MODELS[cloudProvider] || []).map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.label} ({m.desc})
                            </option>
                          ))}
                        </optgroup>
                      )}
                      <optgroup label="Custom Specification">
                        <option value="__custom__">Custom Model Name...</option>
                      </optgroup>
                    </select>
                  </div>

                  {/* Custom Model Text Input if '__custom__' selected */}
                  {isCustomCloudModel && (
                    <div className="space-y-1 p-2 rounded-md bg-muted/40 border border-border">
                      <label className="text-[11px] font-semibold flex items-center gap-1.5 text-foreground">
                        <Edit3 className="size-3 text-primary" />
                        <span>Custom Model Identifier</span>
                      </label>
                      <input
                        type="text"
                        value={customCloudModelValue}
                        onChange={(e) => setCustomCloudModelValue(e.target.value)}
                        placeholder="e.g. meta-llama/Llama-3-70b-chat-hf or custom-finetune"
                        className="w-full px-2.5 py-1.5 text-xs font-mono rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                      <p className="text-[10px] text-muted-foreground">
                        Directly passed to {cloudProvider.toUpperCase()} API endpoint.
                      </p>
                    </div>
                  )}

                  {/* Dynamic Model Capability Tier Card */}
                  {(() => {
                    const activeModelName = isCustomCloudModel
                      ? customCloudModelValue || cloudModel
                      : cloudModel;
                    const tierInfo = getModelTierInfo(activeModelName);
                    return (
                      <div className={`p-2.5 rounded-md border text-xs space-y-1 ${tierInfo.colorClass}`}>
                        <div className="flex items-center justify-between font-semibold">
                          <span>{tierInfo.tier}</span>
                          <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-background/50 border border-current/20">
                            {tierInfo.badge}
                          </span>
                        </div>
                        <p className="text-[11px] opacity-90 leading-relaxed">{tierInfo.desc}</p>
                      </div>
                    );
                  })()}

                  <Button
                    size="sm"
                    className="w-full text-xs h-8 bg-purple-600 hover:bg-purple-700 text-white font-medium"
                    onClick={() => handleApply('byok')}
                  >
                    Apply Model ({isCustomCloudModel ? customCloudModelValue || cloudModel : cloudModel})
                  </Button>
                </div>
              ) : (
                <div className="p-3 rounded-lg border border-dashed border-purple-500/30 bg-purple-500/5 text-center space-y-1.5">
                  <div className="flex items-center justify-center gap-1.5 text-xs font-medium text-purple-700 dark:text-purple-300">
                    <Key className="size-3.5 text-purple-600 dark:text-purple-400" />
                    <span>Verify your key to show available models</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-normal max-w-xs mx-auto">
                    Enter your {cloudProvider.toUpperCase()} API key above and click <strong>Verify</strong> to show the models available for this key.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
