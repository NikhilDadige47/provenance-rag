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
} from 'lucide-react';
import { Button } from './ui/button';
import { LLMConfig } from '../types';
import { api } from '../lib/api';

export interface ModelSelectorProps {
  config: LLMConfig | null;
  onChange: (config: LLMConfig | null) => void;
  onToast: (msg: string, type: 'info' | 'success' | 'warning' | 'error') => void;
  sectionContext?: 'demo' | 'upload';
}

interface ModelItem {
  id: string;
  label: string;
  desc: string;
}

const CLOUD_MODELS: Record<string, ModelItem[]> = {
  groq: [
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
      tier: 'Micro Model (≤3B)',
      badge: '⚡ Ultra-Fast • Top 2 Passages',
      desc: 'Context pruned to top 2 passages for sub-second prefill TTFT and 1-shot grounding directive.',
      colorClass: 'text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20',
    };
  }

  const isMid =
    /7b|8b|9b|10b|11b|12b|13b|14b|mistral|gemma/.test(m) ||
    ['7b', '8b', '9b', '12b', '14b'].some((t) => m.includes(t));

  if (isMid) {
    return {
      tier: 'Mid-Sized Model (7B–14B)',
      badge: '⚖️ Balanced • Top 3 Passages',
      desc: 'Balanced context expansion (top 3 passages) for fast local CPU/GPU inference and high precision.',
      colorClass: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    };
  }

  return {
    tier: 'Frontier / High-Capacity (70B+)',
    badge: '🧠 Full Reasoning • Top 5 Passages',
    desc: 'Full context expansion (top 5 passages) and multi-header markdown synthesis.',
    colorClass: 'text-blue-600 dark:text-blue-400 bg-blue-500/10 border-blue-500/20',
  };
}

type ModelTab = 'default' | 'local' | 'byok';

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  config,
  onChange,
  onToast,
  sectionContext = 'demo',
}) => {
  const [isOpen, setIsOpen] = useState(false);

  // Tab state
  const initialTab: ModelTab = config?.isLocal
    ? 'local'
    : config?.key
      ? 'byok'
      : 'default';
  const [activeTab, setActiveTab] = useState<ModelTab>(initialTab);

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
  const [isTestingCloud, setIsTestingCloud] = useState(false);
  const [cloudStatus, setCloudStatus] = useState<{
    tested: boolean;
    success: boolean;
    message: string;
  } | null>(null);

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
      if (config.model) setCloudModel(config.model);
    } else {
      setActiveTab('default');
    }
  }, [config]);

  // Test local Ollama connection and auto-fetch tags
  const handleTestLocal = async () => {
    setIsTestingLocal(true);
    setLocalStatus(null);
    try {
      const res = await api.testConnection('ollama', '', localUrl.trim());
      if (res.success) {
        setLocalStatus({
          tested: true,
          success: true,
          message: `Connected! Found ${res.models?.length || 0} local model(s).`,
        });
        if (res.models && res.models.length > 0) {
          setDiscoveredModels(res.models);
          if (!res.models.includes(localModel)) {
            setLocalModel(res.models[0]);
          }
        }
        onToast('Successfully connected to local model endpoint.', 'success');
      } else {
        setLocalStatus({
          tested: true,
          success: false,
          message: res.message || 'Could not connect to local model endpoint.',
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
        setCloudStatus({
          tested: true,
          success: true,
          message: 'API Key successfully verified.',
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
      onToast('Switched to Cloud Default (Groq Llama 3.3 70B).', 'info');
      setIsOpen(false);
      return;
    }

    if (tabToApply === 'local') {
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
      const newConfig: LLMConfig = {
        provider: cloudProvider,
        model: cloudModel,
        key: cloudKey.trim(),
        isLocal: false,
      };
      onChange(newConfig);
      api.setVisitorKeys(newConfig);
      onToast(`Switched to ${cloudProvider.toUpperCase()} (${cloudModel}).`, 'success');
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
        <span className="truncate whitespace-nowrap">Default (Groq Llama 3.3 70B)</span>
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
          {/* Tabs */}
          <div className="grid grid-cols-3 gap-1.5 p-1 bg-muted/60 rounded-lg border border-border/50 text-xs font-medium">
            <button
              type="button"
              onClick={() => setActiveTab('default')}
              className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md transition-all ${
                activeTab === 'default'
                  ? 'bg-card text-foreground shadow-xs font-semibold'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Sparkles className="size-3 text-primary" />
              <span>Default Cloud</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('local')}
              className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md transition-all ${
                activeTab === 'local'
                  ? 'bg-card text-foreground shadow-xs font-semibold'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Laptop className="size-3 text-emerald-500" />
              <span>Local Model</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('byok')}
              className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md transition-all ${
                activeTab === 'byok'
                  ? 'bg-card text-foreground shadow-xs font-semibold'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Key className="size-3 text-purple-500" />
              <span>Cloud BYOK</span>
            </button>
          </div>

          {/* TAB 1: DEFAULT OWNER GROQ */}
          {activeTab === 'default' && (
            <div className="space-y-2.5 p-3 rounded-lg border border-border/60 bg-muted/20">
              <div className="flex items-start gap-2.5">
                <ShieldCheck className="size-4 text-primary shrink-0 mt-0.5" />
                <div className="text-xs space-y-1">
                  <div className="font-semibold text-foreground">Groq Llama 3.3 70B Versatile</div>
                  <p className="text-muted-foreground leading-relaxed">
                    Pre-configured high-speed inference. Included in your daily session queries with 100% citation tracking and zero configuration required.
                  </p>
                </div>
              </div>
              <Button
                size="sm"
                className="w-full text-xs h-8"
                onClick={() => handleApply('default')}
              >
                Use Cloud Default
              </Button>
            </div>
          )}

          {/* TAB 2: LOCAL INFERENCE (OLLAMA / LM STUDIO / VLLM) */}
          {activeTab === 'local' && (
            <div className="space-y-3 p-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5">
              <div className="flex items-start gap-2">
                <Laptop className="size-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
                <div className="text-xs space-y-0.5">
                  <div className="font-semibold text-foreground">Self-Hosted Local Inference</div>
                  <p className="text-muted-foreground text-[11px]">
                    Connects directly to Ollama, LM Studio, or vLLM. No prompt text leaves your machine.
                  </p>
                </div>
              </div>

              {/* Endpoint URL Input */}
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-muted-foreground flex items-center justify-between">
                  <span>Server URL (OpenAI-compatible)</span>
                  <span className="text-[10px] text-muted-foreground font-mono">e.g. Ollama: :11434, LM Studio: :1234</span>
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={localUrl}
                    onChange={(e) => setLocalUrl(e.target.value)}
                    placeholder="http://localhost:11434/v1"
                    className="flex-1 px-2.5 py-1.5 text-xs font-mono rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={isTestingLocal}
                    onClick={handleTestLocal}
                    className="h-8 text-xs shrink-0 flex items-center gap-1.5"
                  >
                    {isTestingLocal ? (
                      <Loader2 className="size-3 animate-spin" />
                    ) : (
                      <RefreshCw className="size-3" />
                    )}
                    <span>{isTestingLocal ? 'Connecting...' : 'Test & Discover'}</span>
                  </Button>
                </div>
                <p className="text-[10.5px] text-muted-foreground leading-normal">
                  Running on your laptop? Use <code className="font-mono text-[10px] bg-muted/60 px-1 py-0.5 rounded">http://localhost:11434/v1</code>. Accessing from Render cloud? Use an ngrok or Cloudflare tunnel URL (e.g. <code className="font-mono text-[10px] bg-muted/60 px-1 py-0.5 rounded">https://xyz.ngrok-free.app/v1</code>).
                </p>
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

              {/* Model Input / Selection */}
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-muted-foreground block">
                  Model Tag
                </label>
                {discoveredModels.length > 0 ? (
                  <select
                    value={localModel}
                    onChange={(e) => setLocalModel(e.target.value)}
                    className="w-full px-2.5 py-1.5 text-xs rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    {discoveredModels.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
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

                <div className="text-[10px] text-muted-foreground flex items-center gap-1.5 pt-0.5">
                  <span className="shrink-0">💡</span>
                  <span>Ensure your local runner is active (e.g. <code className="font-mono bg-muted/60 px-1 py-0.5 rounded">ollama serve</code>) before testing.</span>
                </div>
              </div>

              <Button
                size="sm"
                className="w-full text-xs h-8 bg-emerald-600 hover:bg-emerald-700 text-white font-medium"
                onClick={() => handleApply('local')}
              >
                Apply Local Model ({localModel})
              </Button>
            </div>
          )}

          {/* TAB 3: CLOUD BYOK */}
          {activeTab === 'byok' && (
            <div className="space-y-3 p-3 rounded-lg border border-purple-500/20 bg-purple-500/5">
              <div className="flex items-start gap-2">
                <Key className="size-4 text-purple-600 dark:text-purple-400 shrink-0 mt-0.5" />
                <div className="text-xs space-y-0.5">
                  <div className="font-semibold text-foreground">Bring Your Own Key (BYOK)</div>
                  <p className="text-muted-foreground text-[11px]">
                    Pass your own API key to bypass question quotas. Keys are held in volatile memory only.
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
                      setCloudStatus(null);
                    }}
                    className={`py-1 rounded border font-medium capitalize text-center transition-colors ${
                      cloudProvider === p
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
                    }}
                    placeholder={`Enter ${cloudProvider.toUpperCase()} API key`}
                    className="w-full pr-16 pl-2.5 py-1.5 text-xs font-mono rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
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
                      className="h-6 px-1.5 text-[10px]"
                    >
                      {isTestingCloud ? <Loader2 className="size-3 animate-spin" /> : 'Verify'}
                    </Button>
                  </div>
                </div>
              </div>

              {/* Model Dropdown */}
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-muted-foreground block">
                  Model
                </label>
                <select
                  value={cloudModel}
                  onChange={(e) => setCloudModel(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  {(CLOUD_MODELS[cloudProvider] || []).map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label} ({m.desc})
                    </option>
                  ))}
                </select>
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

              <Button
                size="sm"
                className="w-full text-xs h-8 bg-purple-600 hover:bg-purple-700 text-white"
                onClick={() => handleApply('byok')}
              >
                Apply BYOK Key
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
