import { AccessTier, UsageInfo, ExampleQuestion, UploadedDoc, CostEstimate, LLMConfig } from '../types';

const SESSION_STORAGE_KEY = 'provenance_active_session';

function readStoredToken(): string | null {
  try {
    return sessionStorage.getItem(SESSION_STORAGE_KEY) || localStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredToken(token: string) {
  try {
    sessionStorage.setItem(SESSION_STORAGE_KEY, token);
    localStorage.setItem(SESSION_STORAGE_KEY, token);
  } catch {
    // Private mode can throw; cookie + memory still carry the session.
  }
}

function clearStoredToken() {
  try {
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
    localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // ignore
  }
}

export class ApiClient {
  private sessionToken: string | null = readStoredToken();
  private tier: AccessTier = 'tier_a';
  private visitorKeys: LLMConfig = {
    provider: 'groq',
    model: 'llama-3.3-70b-versatile',
    key: '',
  };

  setSessionToken(token: string) {
    this.sessionToken = token;
  }

  setTier(tier: AccessTier) {
    this.tier = tier;
  }

  setVisitorKeys(keys: LLMConfig | null) {
    this.visitorKeys = keys ?? {
      provider: 'groq',
      model: 'llama-3.3-70b-versatile',
      key: '',
    };
  }

  getVisitorKeys(): LLMConfig {
    return this.visitorKeys;
  }

  private getHeaders(additional: Record<string, string> = {}): HeadersInit {
    const headers: Record<string, string> = {
      ...additional,
    };

    if (this.sessionToken) {
      headers['Authorization'] = `Bearer ${this.sessionToken}`;
    }

    // LLM BYOK is independent of parser=auto and of the session tier label.
    // If a visitor pasted a key on the upload tab, send it on chat.
    const llmKey = this.visitorKeys?.key?.trim();
    if (llmKey) {
      headers['X-LLM-Key'] = llmKey;
      headers['X-LLM-Provider'] = this.visitorKeys.provider;
      headers['X-LLM-Model'] = this.visitorKeys.model;
    }

    return headers;
  }

  private apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
    const extra = (init.headers as Record<string, string> | undefined) || {};
    return fetch(path, {
      ...init,
      credentials: 'include',
      headers: this.getHeaders(extra),
    });
  }

  getSessionToken(): string | null {
    return this.sessionToken;
  }

  private rememberToken(sessionId: string | undefined) {
    this.sessionToken = sessionId || this.sessionToken;
    if (this.sessionToken) {
      writeStoredToken(this.sessionToken);
    }
  }

  async ensureSession(tier: AccessTier = 'tier_a'): Promise<{ session_id: string; tier: string; scope: string }> {
    this.tier = tier;
    if (!this.sessionToken) {
      this.sessionToken = readStoredToken();
    }
    const resume = await this.apiFetch('/session', { method: 'GET' });
    if (resume.ok) {
      const data = await resume.json().catch(() => null);
      const token = data?.session_id || data?.session_token;
      if (token) {
        this.rememberToken(token);
        return data;
      }
    }
    return this.createSession(tier);
  }

  async createSession(tier: AccessTier): Promise<{ session_id: string; tier: string; scope: string }> {
    this.tier = tier;
    const res = await this.apiFetch('/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to initialize session');
    }

    const data = await res.json();
    this.rememberToken(data.session_id || data.session_token);
    return data;
  }

  async getUsage(): Promise<UsageInfo> {
    const res = await this.apiFetch('/usage');
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to fetch usage');
    }
    return res.json();
  }

  async getExamples(): Promise<ExampleQuestion[]> {
    const res = await this.apiFetch('/examples');
    if (!res.ok) return [];
    const data = await res.json();
    return data.examples || [];
  }

  async sendChat(question: string, history: Array<{ role: string; content: string }> = []): Promise<any> {
    const res = await this.apiFetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to execute query');
    }

    return res.json();
  }

  async estimateUpload(file: File, parser = 'auto', parserKey?: string): Promise<CostEstimate> {
    console.log(`%c[API Trace: /upload/estimate]%c Validating ${file.name} with ${parser}...`, 'color: #3b82f6; font-weight: bold;', 'color: inherit;');
    const formData = new FormData();
    formData.append('file', file);
    formData.append('parser', parser);
    if (parserKey) formData.append('parser_key', parserKey);

    const extra: Record<string, string> = {};
    if (parserKey) extra['X-Parser-Key'] = parserKey;

    const res = await this.apiFetch('/upload/estimate', {
      method: 'POST',
      headers: extra,
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      console.error(`%c[API Trace: /upload/estimate FAILED]%c`, 'color: #ef4444; font-weight: bold;', 'color: inherit;', err);
      throw new Error(err.detail || 'Validation failed');
    }
    const data = await res.json();
    console.log(`%c[API Trace: /upload/estimate SUCCESS]%c`, 'color: #10b981; font-weight: bold;', 'color: inherit;', data);
    return data;
  }

  async uploadFile(file: File, parser = 'auto', parserKey?: string): Promise<{ job_id: string }> {
    console.log(`%c[API Trace: /upload POST]%c Uploading ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB) with parser: ${parser}`, 'color: #3b82f6; font-weight: bold;', 'color: inherit;');
    const formData = new FormData();
    formData.append('file', file);
    formData.append('parser', parser);
    formData.append('terms_accepted', 'true');
    if (parserKey) formData.append('parser_key', parserKey);

    const extra: Record<string, string> = {};
    if (parserKey) extra['X-Parser-Key'] = parserKey;

    const res = await this.apiFetch('/upload', {
      method: 'POST',
      headers: extra,
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      console.error(`%c[API Trace: /upload FAILED]%c`, 'color: #ef4444; font-weight: bold;', 'color: inherit;', err);
      throw new Error(err.detail || 'Upload failed');
    }
    const data = await res.json();
    console.log(`%c[API Trace: /upload ACCEPTED]%c Job created:`, 'color: #10b981; font-weight: bold;', 'color: inherit;', data);
    return data;
  }

  async pollJob(jobId: string): Promise<any> {
    const res = await this.apiFetch(`/jobs/${jobId}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      console.error(`%c[API Trace: /jobs/${jobId} ERROR]%c`, 'color: #ef4444; font-weight: bold;', 'color: inherit;', err);
      throw new Error(err.detail || 'Failed to check job status');
    }
    const data = await res.json();
    console.log(`%c[API Trace: /jobs/${jobId}]%c status="${data.status}" pages=${data.pages || 0} chunks=${data.chunks || 0}`, 'color: #8b5cf6; font-weight: bold;', 'color: inherit;', data);
    return data;
  }

  async getDocuments(): Promise<UploadedDoc[]> {
    const res = await this.apiFetch('/session/documents');
    if (!res.ok) return [];
    const data = await res.json();
    const list = Array.isArray(data) ? data : data.documents || [];
    return list.map((d: Record<string, unknown>) => {
      const docId = String(d.doc_id || '');
      const filename = String(d.filename || d.title || 'Document');
      return {
        doc_id: docId,
        filename,
        chunk_count: Number(d.chunk_count ?? d.chunks ?? 0),
        token_count: Number(d.token_count ?? 0),
        parser_tier: String(d.parser_tier || d.parser_used || 'auto'),
        uploaded_at: String(d.uploaded_at || d.ingested_at || ''),
        page_count: Number(d.page_count ?? 0),
        degraded: Boolean(d.degraded),
        quality_warnings: Array.isArray(d.quality_warnings)
          ? (d.quality_warnings as string[])
          : undefined,
      };
    });
  }

  async deleteSession(): Promise<void> {
    const res = await this.apiFetch('/session', {
      method: 'DELETE',
    });
    clearStoredToken();
    this.sessionToken = null;
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to delete session');
    }
  }

  async purgeSession(customToken?: string): Promise<void> {
    const tokenToPurge = customToken || this.sessionToken || readStoredToken();
    if (!tokenToPurge) return;
    try {
      await fetch('/session/purge', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${tokenToPurge}`,
        },
        body: JSON.stringify({ session_id: tokenToPurge }),
        keepalive: true,
      });
    } catch {
      // Best-effort cleanup
    }
    clearStoredToken();
    this.sessionToken = null;
  }

  purgeOnUnload(): void {
    const token = this.sessionToken || readStoredToken();
    if (!token) return;
    const payload = JSON.stringify({ session_id: token });
    if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
      const blob = new Blob([payload], { type: 'application/json' });
      navigator.sendBeacon('/session/purge', blob);
    } else {
      fetch('/session/purge', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: payload,
        keepalive: true,
      }).catch(() => {});
    }
    clearStoredToken();
    this.sessionToken = null;
  }

  async testConnection(provider: string, key: string): Promise<{ success: boolean; message: string; models?: string[] }> {
    const res = await this.apiFetch('/connections/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, key }),
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false || data.status === 'error') {
      return {
        success: false,
        message: data.error || data.hint || data.message || data.detail || 'Key validation failed',
      };
    }
    return {
      success: true,
      message: 'Key verified successfully',
      models: data.models || undefined,
    };
  }
}

export const api = new ApiClient();
