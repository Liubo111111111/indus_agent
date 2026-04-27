/**
 * TypeScript type definitions corresponding to backend Pydantic models.
 * Field names use camelCase; the API client handles snake_case → camelCase conversion.
 */

// --- 统计 ---

export interface StatsResponse {
  totalProcessed: number;
  annotatedCount: number;
  unannotatedCount: number;
  labelDistribution: Record<string, number>;
}

// --- 日期分区 ---

export interface DateEntry {
  pt: string;
  recordCount: number;
}

export interface DatesResponse {
  dates: DateEntry[];
  latestPt: string | null;
}

export interface DailySummaryEntry {
  pt: string;
  totalCount: number;
  formalCount: number;
  fallbackCount: number;
}

export interface DailySummaryResponse {
  summaries: DailySummaryEntry[];
}

// --- 运行记录 ---

export interface RunSummary {
  runId: string;
  entityKey: string;
  enterpriseName: string;
  finalLabel: string | null;
  annotatedLabel: string | null;
  confidenceLevel: string | null;
  route: 'formal' | 'fallback';
  errorType: string | null;
  timestamp: string | null;
  annotations: AnnotationRecord[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export interface RunDetail {
  runId: string;
  entityKey: string;
  enterpriseName: string;
  businessScope: string;
  wideRow: Record<string, unknown>;
  staticProfile: Record<string, unknown> | null;
  dynamicProfile: Record<string, unknown> | null;
  decisionRecord: Record<string, unknown> | null;
  route: string;
  errorType: string | null;
  audit: Record<string, unknown>;
  timingMs: Record<string, number> | null;
  annotations: AnnotationRecord[];
}

// --- 搜索 ---

export interface SearchResult {
  entityKey: string;
  enterpriseName: string;
  finalLabel: string | null;
  route: string;
  runId: string;
}

// --- 批量任务 ---

export interface BatchRequest {
  pt: string;
  inputPath: string;
  workerCount?: number;
  providerRateLimitPerMinute?: number;
  maxInFlight?: number;
}

export interface BatchAccepted {
  taskId: string;
  message: string;
  status: string;
}

// --- Fallback / 审核 ---

export interface FallbackRecord {
  entityKey: string;
  enterpriseName: string;
  finalLabel: string | null;
  confidenceLevel: string | null;
  errorType: string | null;
  decisionRecord: Record<string, unknown> | null;
  audit: Record<string, unknown>;
}

export interface ReviewRequest {
  approvedLabel: string;
  reviewerNotes?: string;
}

export interface ReviewResponse {
  entityKey: string;
  approvedLabel: string;
  status: string;
}

export interface AnnotationRecord {
  annotatedLabel: string;
  reviewerNotes?: string;
  reviewerName?: string;
  createdAt?: string;
}

export interface AnnotationRequest {
  annotatedLabel: string;
  reviewerNotes?: string;
  reviewerName?: string;
}

export interface AnnotationResponse {
  runId: string;
  annotatedLabel: string;
  status: string;
}

// --- Auth ---

export interface AuthUser {
  openId: string;
  name: string;
  enName?: string;
  avatarUrl?: string;
  email?: string;
  enterpriseEmail?: string;
  userId?: string;
  tenantKey?: string;
  isAdmin?: boolean;
}

export interface AuthSession {
  enabled: boolean;
  authenticated: boolean;
  accessDenied?: boolean;
  requestStatus?: string | null;
  user: AuthUser | null;
  loginUrl: string | null;
}

export interface AdminOverview {
  authEnabled: boolean;
  adminMode: string;
  accessScope: string;
  frontendBaseUrl: string;
  redirectUri: string;
  hostConsistent: boolean;
  allowedOpenIdCount: number;
  allowedEmailCount: number;
  adminOpenIdCount: number;
  adminEmailCount: number;
  warnings: string[];
}

export interface AccessSettings {
  allowedOpenIds: string[];
  allowedEmails: string[];
  adminOpenIds: string[];
  adminEmails: string[];
}

export interface AdminAuthAuditEvent {
  eventType: string;
  openId: string;
  name: string;
  email?: string;
  enterpriseEmail?: string;
  userId?: string;
  tenantKey?: string;
  isAdmin: boolean;
  createdAt: string;
}

export interface AdminAuthAuditUser {
  openId: string;
  name: string;
  email?: string;
  enterpriseEmail?: string;
  userId?: string;
  tenantKey?: string;
  isAdmin: boolean;
  lastEventType: string;
  lastEventAt: string;
  eventCount: number;
}

export interface AdminAuthAudit {
  events: AdminAuthAuditEvent[];
  users: AdminAuthAuditUser[];
}

// --- Taxonomy ---

export interface TaxonomyLabel {
  id: string;
  displayName: string;
  shortDescription: string;
  promptText: string;
  enabled: boolean;
}

export interface TaxonomyResponse {
  version: string;
  labels: TaxonomyLabel[];
}

// --- 系统配置 ---

export interface SettingsResponse {
  llmModel: string;
  llmTimeoutSec: number;
  llmMaxRetry: number;
  workerCount: number;
  providerRateLimitPerMinute: number;
  maxInFlight: number;
  batchMaxRows: number;
}

export interface SettingsUpdate {
  llmModel?: string;
  llmTimeoutSec?: number;
  llmMaxRetry?: number;
  workerCount?: number;
  providerRateLimitPerMinute?: number;
  maxInFlight?: number;
  batchMaxRows?: number;
}


// --- 分类任务 ---

export interface ClassifySingleRequest {
  query: string;
}

export interface ClassifyAccepted {
  taskId: string;
  message: string;
  status: string;
  totalRows?: number;
}

// --- 回溯测试 ---

export interface BacktestRunRequest {
  ptDates: string[];
  promptVersionStatic?: string;
  promptVersionDynamic?: string;
  promptVersionFinal?: string;
}

export interface BacktestRunAccepted {
  backtestRunId: string;
  message: string;
  datasetSize: number;
}

export interface BacktestStatus {
  backtestRunId: string;
  status: string;
  datasetSize: number;
  completedCount: number;
  errorCount: number;
  currentEntity: string | null;
  accuracy: number | null;
}

export interface LabelMetrics {
  label: string;
  precision: number;
  recall: number;
  f1: number;
  support: number;
}

export interface MisclassifiedItem {
  entityKey: string;
  enterpriseName: string;
  annotatedLabel: string;
  predictedLabel: string;
  confidenceLevel: string | null;
}

export interface AccuracyReport {
  backtestRunId: string;
  accuracy: number;
  originalAccuracy: number | null;
  total: number;
  correct: number;
  errorCount: number;
  labelMetrics: LabelMetrics[];
  confusionMatrix: Record<string, Record<string, number>>;
  misclassified: MisclassifiedItem[];
  details: BacktestResultDetail[];
}

export interface BacktestResultDetail {
  entityKey: string;
  enterpriseName: string;
  originalLabel: string | null;
  annotatedLabel: string;
  predictedLabel: string | null;
  confidenceLevel: string | null;
  errorType: string | null;
  match: boolean;
}

export interface BacktestRunSummary {
  backtestRunId: string;
  promptVersionStatic: string;
  promptVersionDynamic: string;
  promptVersionFinal: string;
  ptDates: string[];
  datasetSize: number;
  accuracy: number | null;
  status: string;
  createdAt: string;
}

export interface FlipItem {
  entityKey: string;
  enterpriseName: string;
  annotatedLabel: string;
  labelA: string;
  labelB: string;
  direction: string;
}

export interface ComparisonResult {
  runA: BacktestRunSummary;
  runB: BacktestRunSummary;
  accuracyDiff: number;
  labelMetricsDiff: Record<string, unknown>[];
  flips: FlipItem[];
  confusionMatrixA: Record<string, Record<string, number>>;
  confusionMatrixB: Record<string, Record<string, number>>;
}

export interface AvailableDate {
  date: string;
  count: number;
}

export interface AnnotationDatasetSummary {
  total: number;
  labelDistribution: Record<string, number>;
  entities: Record<string, unknown>[];
}

export interface BaselineReportDetail {
  entityKey: string;
  enterpriseName: string;
  annotatedLabel: string;
  originalLabel: string | null;
  match: boolean;
}

export interface BaselineReport {
  total: number;
  accuracy: number;
  correct: number;
  errorCount: number;
  labelMetrics: LabelMetrics[];
  confusionMatrix: Record<string, Record<string, number>>;
  details: BaselineReportDetail[];
}
