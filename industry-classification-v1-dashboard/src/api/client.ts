import type {
  AdminAuthAudit,
  AdminOverview,
  AccessSettings,
  AnnotationRequest,
  AnnotationResponse,
  AuthSession,
  StatsResponse,
  PaginatedResponse,
  RunSummary,
  RunDetail,
  SearchResult,
  BatchRequest,
  BatchAccepted,
  FallbackRecord,
  ReviewRequest,
  ReviewResponse,
  TaxonomyResponse,
  SettingsResponse,
  SettingsUpdate,
} from './types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';
const TIMEOUT_MS = 10_000;

// snake_case → camelCase deep converter
function toCamelCase(obj: unknown): unknown {
  if (Array.isArray(obj)) return obj.map(toCamelCase);
  if (obj !== null && typeof obj === 'object') {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => [
        k.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase()),
        toCamelCase(v),
      ])
    );
  }
  return obj;
}

// camelCase → snake_case deep converter (for request bodies)
function toSnakeCase(obj: unknown): unknown {
  if (Array.isArray(obj)) return obj.map(toSnakeCase);
  if (obj !== null && typeof obj === 'object') {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => [
        k.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`),
        toSnakeCase(v),
      ])
    );
  }
  return obj;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const resp = await fetch(`${BASE_URL}${path}`, {
      ...options,
      credentials: 'include',
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new ApiError(resp.status, body.detail || resp.statusText);
    }

    const json = await resp.json();
    return toCamelCase(json) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if ((err as Error).name === 'AbortError') {
      throw new ApiError(0, 'Request timed out');
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  getAuthSession: () => request<AuthSession>('/auth/session'),

  getAdminOverview: () => request<AdminOverview>('/admin/overview'),

  getAdminAuthAudit: () => request<AdminAuthAudit>('/admin/auth-audit'),

  getAccessSettings: () => request<AccessSettings>('/admin/access-settings'),

  updateAccessSettings: (settings: AccessSettings) =>
    request<AccessSettings>('/admin/access-settings', {
      method: 'PUT',
      body: JSON.stringify(toSnakeCase(settings)),
    }),

  getLoginUrl: (next = '/') => `${BASE_URL}/auth/login?next=${encodeURIComponent(next)}`,

  logout: () =>
    request<{ status: string }>('/auth/logout', {
      method: 'POST',
    }),

  getStats: () => request<StatsResponse>('/stats'),

  getAnnotations: () => request<Record<string, unknown>[]>('/annotations'),

  getRuns: (offset = 0, limit = 20) =>
    request<PaginatedResponse<RunSummary>>(
      `/runs?offset=${offset}&limit=${limit}`
    ),

  getRunDetail: (runId: string) =>
    request<RunDetail>(`/runs/${encodeURIComponent(runId)}`),

  search: (query: string) =>
    request<SearchResult[]>(`/search?query=${encodeURIComponent(query)}`),

  triggerBatch: (params: BatchRequest) =>
    request<BatchAccepted>('/batch', {
      method: 'POST',
      body: JSON.stringify(toSnakeCase(params)),
    }),

  getFallbacks: (offset = 0, limit = 20) =>
    request<PaginatedResponse<FallbackRecord>>(
      `/fallbacks?offset=${offset}&limit=${limit}`
    ),

  submitAnnotation: (runId: string, annotation: AnnotationRequest) =>
    request<AnnotationResponse>(
      `/runs/${encodeURIComponent(runId)}/annotation`,
      {
        method: 'PUT',
        body: JSON.stringify(toSnakeCase(annotation)),
      }
    ),

  submitReview: (entityKey: string, review: ReviewRequest) =>
    request<ReviewResponse>(
      `/fallbacks/${encodeURIComponent(entityKey)}/review`,
      {
        method: 'PUT',
        body: JSON.stringify(toSnakeCase(review)),
      }
    ),

  getTaxonomy: () => request<TaxonomyResponse>('/taxonomy'),

  getSettings: () => request<SettingsResponse>('/settings'),

  getPrompts: () => request<Record<string, { version: string; systemPrompt: string; userTemplate: string } | null>>('/prompts'),

  updateSettings: (settings: SettingsUpdate) =>
    request<SettingsResponse>('/settings', {
      method: 'PUT',
      body: JSON.stringify(toSnakeCase(settings)),
    }),

  classifySingle: (query: string, pt?: string) =>
    request<{ taskId: string; message: string; status: string }>('/classify/single', {
      method: 'POST',
      body: JSON.stringify({ query, pt: pt || '' }),
    }),

  classifyByJobName: (jobName: string, pt?: string) =>
    request<{ taskId: string; message: string; status: string }>('/classify/by-job-name', {
      method: 'POST',
      body: JSON.stringify({ job_name: jobName, pt: pt || '' }),
    }),

  getClassifyStatus: (taskId: string) =>
    request<{ taskId: string; status: string; stages: Array<{ name: string; status: string; elapsedMs: number | null; message: string }>; resultRunId: string | null; error: string | null }>(
      `/classify/status/${encodeURIComponent(taskId)}`
    ),

  classifyUploadCsv: async (file: File): Promise<{ taskId: string; message: string; totalRows: number; status: string }> => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 60_000);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const resp = await fetch(`${BASE_URL}/classify/upload`, {
        method: 'POST',
        body: formData,
        credentials: 'include',
        signal: controller.signal,
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new ApiError(resp.status, body.detail || resp.statusText);
      }
      const json = await resp.json();
      return toCamelCase(json) as any;
    } catch (err) {
      if (err instanceof ApiError) throw err;
      if ((err as Error).name === 'AbortError') throw new ApiError(0, 'Upload timed out');
      throw err;
    } finally {
      clearTimeout(timer);
    }
  },
};
