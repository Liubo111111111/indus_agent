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
  DatesResponse,
  DailySummaryResponse,
  AvailableDate,
  AnnotationDatasetSummary,
  BacktestRunRequest,
  BacktestRunAccepted,
  BacktestStatus,
  AccuracyReport,
  BacktestRunSummary,
  ComparisonResult,
  BaselineReport,
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

  requestAccess: (reason?: string) =>
    request<{ status: string }>('/auth/request-access', {
      method: 'POST',
      body: JSON.stringify({ reason: reason || '' }),
    }),

  getAccessRequests: (status?: string) =>
    request<Array<{ openId: string; name: string; email: string; enterpriseEmail: string; tenantKey: string; reason: string; status: string; reviewerNote: string; createdAt: string; updatedAt: string }>>(
      `/admin/access-requests${status ? `?status=${status}` : ''}`
    ),

  reviewAccessRequest: (openId: string, action: 'approve' | 'reject' | 'revoke', reviewerNote?: string) =>
    request<{ openId: string; status: string }>(`/admin/access-requests/${encodeURIComponent(openId)}`, {
      method: 'PUT',
      body: JSON.stringify({ action, reviewer_note: reviewerNote || '' }),
    }),

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

  getStats: (pt?: string) => {
    const params = new URLSearchParams();
    if (pt) params.set('pt', pt);
    const qs = params.toString();
    return request<StatsResponse>(`/stats${qs ? `?${qs}` : ''}`);
  },

  getAnnotations: (pt?: string) => {
    const params = new URLSearchParams();
    if (pt) params.set('pt', pt);
    const qs = params.toString();
    return request<Record<string, unknown>[]>(`/annotations${qs ? `?${qs}` : ''}`);
  },

  getRuns: (offset = 0, limit = 20, pt?: string, label?: string, annotationStatus?: string) => {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (pt) params.set('pt', pt);
    if (label) params.set('label', label);
    if (annotationStatus) params.set('annotation_status', annotationStatus);
    return request<PaginatedResponse<RunSummary>>(`/runs?${params}`);
  },

  getRunDetail: (runId: string, pt?: string) => {
    const params = new URLSearchParams();
    if (pt) params.set('pt', pt);
    const qs = params.toString();
    return request<RunDetail>(`/runs/${encodeURIComponent(runId)}${qs ? `?${qs}` : ''}`);
  },

  search: (query: string, pt?: string) => {
    const params = new URLSearchParams({ query });
    if (pt) params.set('pt', pt);
    return request<SearchResult[]>(`/search?${params}`);
  },

  triggerBatch: (params: BatchRequest) =>
    request<BatchAccepted>('/batch', {
      method: 'POST',
      body: JSON.stringify(toSnakeCase(params)),
    }),

  getFallbacks: (offset = 0, limit = 20, pt?: string) => {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (pt) params.set('pt', pt);
    return request<PaginatedResponse<FallbackRecord>>(`/fallbacks?${params}`);
  },

  submitAnnotation: (runId: string, annotation: AnnotationRequest, pt?: string) => {
    const params = new URLSearchParams();
    if (pt) params.set('pt', pt);
    const qs = params.toString();
    return request<AnnotationResponse>(
      `/runs/${encodeURIComponent(runId)}/annotation${qs ? `?${qs}` : ''}`,
      { method: 'PUT', body: JSON.stringify(toSnakeCase(annotation)) }
    );
  },

  submitReview: (entityKey: string, review: ReviewRequest, pt?: string) => {
    const params = new URLSearchParams();
    if (pt) params.set('pt', pt);
    const qs = params.toString();
    return request<ReviewResponse>(
      `/fallbacks/${encodeURIComponent(entityKey)}/review${qs ? `?${qs}` : ''}`,
      { method: 'PUT', body: JSON.stringify(toSnakeCase(review)) }
    );
  },

  getDates: () => request<DatesResponse>('/dates'),

  getStatsRange: (ptStart: string, ptEnd: string) =>
    request<StatsResponse>(`/stats?pt_start=${ptStart}&pt_end=${ptEnd}`),

  getDailySummary: (ptStart: string, ptEnd: string) =>
    request<DailySummaryResponse>(`/daily-summary?pt_start=${ptStart}&pt_end=${ptEnd}`),

  getTaxonomy: () => request<TaxonomyResponse>('/taxonomy'),

  getSettings: () => request<SettingsResponse>('/settings'),

  getBatchConfig: () => request<{ batchMaxRows: number }>('/settings/batch-config'),

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

  // --- 回溯测试 ---
  getBacktestPromptVersions: () =>
    request<Record<string, string[]>>('/backtest/prompt-versions'),

  getBacktestAvailableDates: () =>
    request<AvailableDate[]>('/backtest/available-dates'),

  getPromptVersions: () =>
    request<{ nodes: Record<string, { displayName: string; default: string; versions: string[] }> }>('/backtest/prompt-versions'),

  getBacktestAnnotationSummary: (ptDates: string[]) =>
    request<AnnotationDatasetSummary>(`/backtest/annotations?pt_dates=${ptDates.join(',')}`),

  getBaselineReport: (ptDates: string[]) =>
    request<BaselineReport>(`/backtest/baseline-report?pt_dates=${ptDates.join(',')}`),

  startBacktestRun: (params: BacktestRunRequest) =>
    request<BacktestRunAccepted>('/backtest/run', {
      method: 'POST',
      body: JSON.stringify(toSnakeCase(params)),
    }),

  getBacktestStatus: (backtestRunId: string) =>
    request<BacktestStatus>(`/backtest/run/${encodeURIComponent(backtestRunId)}/status`),

  getBacktestReport: (backtestRunId: string) =>
    request<AccuracyReport>(`/backtest/run/${encodeURIComponent(backtestRunId)}/report`),

  getBacktestRuns: () =>
    request<BacktestRunSummary[]>('/backtest/runs'),

  compareBacktestRuns: (runA: string, runB: string) =>
    request<ComparisonResult>(`/backtest/compare?run_a=${encodeURIComponent(runA)}&run_b=${encodeURIComponent(runB)}`),

  deleteBacktestRun: (backtestRunId: string) =>
    request<{ message: string }>(`/backtest/run/${encodeURIComponent(backtestRunId)}`, {
      method: 'DELETE',
    }),

  getBacktestResultDetail: (backtestRunId: string, entityKey: string) =>
    request<Record<string, unknown>>(`/backtest/run/${encodeURIComponent(backtestRunId)}/result/${encodeURIComponent(entityKey)}`),

  getOriginalRunDetail: (runId: string) =>
    request<Record<string, unknown>>(`/backtest/original-detail/${encodeURIComponent(runId)}`),

  classifyUploadCsv: async (file: File, pt?: string): Promise<{ taskId: string; message: string; totalRows: number; status: string }> => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 60_000);
    try {
      const formData = new FormData();
      formData.append('file', file);
      if (pt) formData.append('pt', pt);
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
