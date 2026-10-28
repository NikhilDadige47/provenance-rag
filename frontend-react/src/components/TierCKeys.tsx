import React, { useEffect, useState } from 'react';
import {
  Check,
  AlertTriangle,
  Eye,
  EyeOff,
  Loader2,
  Cpu,
  Edit3,
} from 'lucide-react';
import { Button } from './ui/button';
import { LLMConfig, UploadedDoc } from '../types';
import { api } from '../lib/api';

interface TierCKeysProps {
  documents?: UploadedDoc[];
  onUploadSuccess?: () => void;
  onRequestDelete?: () => void;
  onToast: (msg: string, type: 'info' | 'success' | 'warning' | 'error') => void;
  onKeyConfigChange: (config: LLMConfig) => void;
}

interface ModelItem {
  id: string;
  label: string;
  desc: string;
}

const SUITABLE_MODELS: Record<string, ModelItem[]> = {
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

export const TierCKeys: React.FC<TierCKeysProps> = ({
  documents,
  onUploadSuccess,
  onRequestDelete,
  onToast,
  onKeyConfigChange,
}) => {
  const [provider, setProvider] = useState<'groq' | 'openai' | 'anthropic' | 'gemini' | 'mistral'>('groq');
  const [model, setModel] = useState('llama-3.3-70b-versatile');
  const [isCustomModel, setIsCustomModel] = useState(false);
  const [customModelValue, setCustomModelValue] = useState('');
  const [key, setKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; modelCount?: number } | null>(null);
  const [liveModels, setLiveModels] = useState<string[]>([]);

  const suitableList = SUITABLE_MODELS[provider] || [];

  useEffect(() => {
    onKeyConfigChange({ provider, model, key });
    // Push the currently selected provider/model into the chat header on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleProviderChange = (p: any) => {
    setProvider(p);
    setLiveModels([]);
    setIsCustomModel(false);
    setCustomModelValue('');
    const defaultM = SUITABLE_MODELS[p]?.[0]?.id || 'llama-3.3-70b-versatile';
    setModel(defaultM);
    setTestResult(null);
    onKeyConfigChange({ provider: p, model: defaultM, key });
  };

  const handleModelSelect = (selectedVal: string) => {
    if (selectedVal === '__custom__') {
      setIsCustomModel(true);
      const val = customModelValue || model;
      onKeyConfigChange({ provider, model: val, key });
    } else {
      setIsCustomModel(false);
      setModel(selectedVal);
      onKeyConfigChange({ provider, model: selectedVal, key });
    }
  };

  const handleCustomModelChange = (val: string) => {
    setCustomModelValue(val);
    setModel(val);
    onKeyConfigChange({ provider, model: val, key });
  };

  const handleKeyChange = (val: string) => {
    setKey(val);
    setTestResult(null);
    onKeyConfigChange({ provider, model, key: val });
  };

  const handleTestKey = async () => {
    if (!key.trim()) {
      onToast('Please enter an API key first.', 'warning');
      return;
    }

    setIsTesting(true);
    setTestResult(null);

    try {
      const res = await api.testConnection(provider, key.trim());
      if (res.success) {
        let count = 0;
        if (res.models && res.models.length > 0) {
          // Filter suitable models (exclude whisper, guard, audio models for Groq / OpenAI)
          const filtered = res.models.filter((m) => {
            const lower = m.toLowerCase();
            return !lower.includes('whisper') && !lower.includes('guard') && !lower.includes('tts') && !lower.includes('dall-e');
          });
          setLiveModels(filtered);
          count = filtered.length;

          // If current model is not in the live models, pick a recommended one
          if (!filtered.includes(model) && filtered.length > 0) {
            const preferred = filtered.find((m) => m.includes('llama-3.3') || m.includes('gpt-4o')) || filtered[0];
            setModel(preferred);
            onKeyConfigChange({ provider, model: preferred, key: key.trim() });
          }
        }

        setTestResult({
          success: true,
          message: `Connected to ${provider.toUpperCase()}! ${count > 0 ? `${count} models verified and available in dropdown.` : 'Key verified successfully.'}`,
          modelCount: count,
        });
        onToast(`Connection verified for ${provider.toUpperCase()}!`, 'success');
      } else {
        setTestResult({ success: false, message: res.message });
        onToast(res.message, 'error');
      }
    } catch (err: any) {
      setTestResult({ success: false, message: err.message || 'Verification request failed' });
      onToast(err.message || 'Connection failed', 'error');
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Key Config Card */}
      <div className="border border-border rounded-lg p-5 surface-inset shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">Bring Your Own LLM Key</h3>
          <span className="text-xs font-mono bg-amber-500/10 text-amber-600 border border-amber-500/20 px-2 py-0.5 rounded-full">
            Unlimited BYOK Queries
          </span>
        </div>

        <p className="text-xs text-muted-foreground">
          Provide your personal key for unlimited queries. Held in volatile RAM only; never persisted to disk.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-end">
          {/* Provider Selection */}
          <div className="space-y-1.5 flex-1">
            <div className="h-5 flex items-center">
              <label className="text-xs font-semibold text-foreground">LLM Provider</label>
            </div>
            <select
              value={provider}
              onChange={(e) => handleProviderChange(e.target.value)}
              className="w-full h-9 text-xs px-2.5 rounded-md border border-border bg-card focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="groq">Groq</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Claude</option>
              <option value="gemini">Gemini</option>
              <option value="mistral">Mistral</option>
            </select>
          </div>

          {/* Model Identifier Dropdown */}
          <div className="space-y-1.5 flex-1">
            <div className="h-5 flex items-center justify-between">
              <label className="text-xs font-semibold flex items-center gap-1.5 text-foreground">
                <Cpu className="size-3.5 text-primary" />
                <span>Model Identifier</span>
              </label>
              {liveModels.length > 0 && (
                <span className="text-[10px] font-mono text-emerald-600 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20 leading-none">
                  {liveModels.length} Live Models
                </span>
              )}
            </div>

            <select
              value={isCustomModel ? '__custom__' : model}
              onChange={(e) => handleModelSelect(e.target.value)}
              className="w-full h-9 text-xs px-2.5 rounded-md border border-border bg-card focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {/* If verified live models were discovered */}
              {liveModels.length > 0 && (
                <optgroup label={`Verified Live on ${provider.toUpperCase()}`}>
                  {liveModels.map((m) => (
                    <option key={`live-${m}`} value={m}>
                      {m}
                    </option>
                  ))}
                </optgroup>
              )}

              {/* Pre-configured suitable models */}
              <optgroup label={`Suitable Models for ${provider.toUpperCase()}`}>
                {suitableList.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </optgroup>

              {/* Custom Model Option */}
              <optgroup label="Custom Specification">
                <option value="__custom__">Custom</option>
              </optgroup>
            </select>
          </div>
        </div>

        {/* Custom Model Input if selected */}
        {isCustomModel && (
          <div className="space-y-1.5 p-3 rounded-md bg-muted/30 border border-border">
            <label className="text-xs font-semibold flex items-center gap-1.5">
              <Edit3 className="size-3 text-primary" />
              <span>Enter Custom Model Name</span>
            </label>
            <input
              type="text"
              placeholder="e.g. meta-llama/Llama-3-70b-chat-hf or custom-finetune-v1"
              value={customModelValue}
              onChange={(e) => handleCustomModelChange(e.target.value)}
              className="w-full text-xs font-mono p-2 rounded-md border border-border bg-card focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <p className="text-[10px] text-muted-foreground">
              Passes this custom model name directly to {provider.toUpperCase()}'s API endpoint.
            </p>
          </div>
        )}

        {/* Key Input & Verification */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold block">API Secret Key</label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type={showKey ? 'text' : 'password'}
                placeholder={provider === 'groq' ? 'gsk_...' : 'sk-...'}
                value={key}
                onChange={(e) => handleKeyChange(e.target.value)}
                className="w-full text-xs font-mono p-2 pr-8 rounded-md border border-border bg-card focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                aria-label={showKey ? 'Hide API key' : 'Show API key'}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors p-0.5"
              >
                {showKey ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
              </button>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleTestKey}
              disabled={isTesting || !key.trim() || testResult?.success === true}
              className={`h-9 min-w-[5.5rem] gap-1.5 shrink-0 ${
                testResult?.success
                  ? 'text-emerald-600 border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/10 hover:text-emerald-600'
                  : ''
              }`}
            >
              {isTesting ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : testResult?.success ? (
                <>
                  <Check className="size-3.5" strokeWidth={2.5} />
                  <span>Verified</span>
                </>
              ) : (
                <span>Verify</span>
              )}
            </Button>
          </div>
        </div>

        {testResult && !testResult.success && (
          <div className="p-2.5 rounded-md text-xs flex items-center gap-2 bg-destructive/10 text-destructive border border-destructive/20">
            <AlertTriangle className="size-4 shrink-0" />
            <span>{testResult.message}</span>
          </div>
        )}
      </div>
    </div>
  );
};
