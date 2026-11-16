/**
 * Utility functions for formatting and displaying LLM model names dynamically
 * based on server environment configuration and user selections.
 */

export function formatModelDisplayName(modelId?: string): string {
  if (!modelId) return 'Cloud AI';
  const raw = modelId.trim();

  // Known clean display names
  if (/gpt-oss-120b/i.test(raw)) return 'GPT-OSS 120B';
  if (/llama-3\.3-70b/i.test(raw)) return 'Llama 3.3 70B';
  if (/llama-3\.1-70b/i.test(raw)) return 'Llama 3.1 70B';
  if (/llama-3\.1-8b/i.test(raw)) return 'Llama 3.1 8B';
  if (/llama-3\.2-3b/i.test(raw)) return 'Llama 3.2 3B';
  if (/deepseek-r1/i.test(raw)) return 'DeepSeek R1';
  if (/mixtral-8x7b/i.test(raw)) return 'Mixtral 8x7B';
  if (/claude-3-5-sonnet/i.test(raw)) return 'Claude 3.5 Sonnet';
  if (/claude-3-5-haiku/i.test(raw)) return 'Claude 3.5 Haiku';
  if (/gemini-2\.0-flash/i.test(raw)) return 'Gemini 2.0 Flash';
  if (/gemini-1\.5-pro/i.test(raw)) return 'Gemini 1.5 Pro';
  if (/gpt-4o-mini/i.test(raw)) return 'GPT-4o Mini';
  if (/gpt-4o\b/i.test(raw)) return 'GPT-4o';

  // Strip organization prefix if present (e.g. "openai/gpt-oss-120b" -> "gpt-oss-120b")
  const stripped = raw.includes('/') ? raw.split('/')[1] : raw;
  return stripped;
}

export function formatDefaultModelLabel(provider?: string, model?: string): string {
  const p = (provider || 'Groq').trim();
  const provCapitalized = p.charAt(0).toUpperCase() + p.slice(1);
  const m = formatModelDisplayName(model || 'openai/gpt-oss-120b');
  return `Included (${provCapitalized} ${m})`;
}
