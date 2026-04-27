import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Database,
  FileText,
  Activity,
  BrainCircuit,
  ArrowLeft,
  Tag,
  XCircle,
  RefreshCw,
  X,
  Loader2,
  Send,
} from 'lucide-react';
import { api } from '../api/client';
import type { RunDetail, TaxonomyLabel, AnnotationRecord } from '../api/types';

// --- 本地辅助函数 ---

// taxonomy ID → 中文名映射
const TAXONOMY_ID_TO_NAME: Record<string, string> = {
  ride_hailing: '网约车',
  freight_logistics: '货运物流',
  entertainment_services: '娱乐服务',
  cultural_media: '文化传媒',
  domestic_services: '家政服务',
  property_management: '物业管理',
  gig_platform: '接单类平台',
  security_services: '安保服务',
  construction: '建筑类',
  rider_delivery: '骑手配送',
  food_services: '餐饮服务',
  other: '其他',
};

function resolveLabelName(raw: string, taxonomyLabels?: TaxonomyLabel[]): string {
  if (!raw) return raw;
  if (TAXONOMY_ID_TO_NAME[raw]) return TAXONOMY_ID_TO_NAME[raw];
  if (taxonomyLabels) {
    const found = taxonomyLabels.find(tl => tl.id === raw);
    if (found) return found.displayName;
  }
  return raw;
}

const confidenceLevelMap: Record<string, { num: number; label: string; color: string }> = {
  high: { num: 0.95, label: '高', color: 'text-emerald-600' },
  medium: { num: 0.70, label: '中', color: 'text-amber-600' },
  low: { num: 0.40, label: '低', color: 'text-red-500' },
  human_review: { num: 1.0, label: '人工审核', color: 'text-blue-600' },
};

const getConfidenceBadgeClass = (score: number) => (
  score >= 0.8
    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : score >= 0.5
      ? 'bg-amber-50 text-amber-700 border-amber-200'
      : 'bg-red-50 text-red-600 border-red-200'
);

function normalizeTimestamp(value?: string): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(trimmed)) {
    return `${trimmed.replace(' ', 'T')}Z`;
  }
  return trimmed;
}

function formatDateTime(value?: string): string {
  const normalized = normalizeTimestamp(value);
  if (!normalized) return '-';
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) return value ?? '-';
  return parsed.toLocaleString('zh-CN', { hour12: false });
}

const Skeleton = ({ className = '' }: { className?: string }) => (
  <div className={`animate-pulse bg-slate-200 rounded ${className}`} />
);

const ErrorBox = ({ message, onRetry }: { message: string; onRetry: () => void }) => (
  <div className="flex flex-col items-center justify-center py-12 text-center">
    <XCircle size={40} className="text-red-400 mb-3" />
    <p className="text-sm text-red-600 mb-4">{message}</p>
    <button onClick={onRetry} className="flex items-center gap-2 px-4 py-2 bg-blue-50 text-blue-600 hover:bg-blue-100 rounded-lg text-sm font-medium transition-colors">
      <RefreshCw size={14} /> 重试
    </button>
  </div>
);

// --- 标注对话框 ---
const AnnotationDialog = ({
  open,
  onClose,
  runId,
  currentLabel,
  currentNotes = '',
  reviewerName = '',
  taxonomyLabels,
  showToast,
  pt,
}: {
  open: boolean;
  onClose: (submitted?: boolean) => void;
  runId: string;
  currentLabel: string;
  currentNotes?: string;
  reviewerName?: string;
  taxonomyLabels: TaxonomyLabel[];
  showToast: (msg: string, isError?: boolean) => void;
  pt?: string | null;
}) => {
  const [selectedLabel, setSelectedLabel] = useState(currentLabel || '');
  const [reviewerNotes, setReviewerNotes] = useState(currentNotes);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setSelectedLabel(currentLabel || '');
    setReviewerNotes(currentNotes || '');
  }, [currentLabel, currentNotes, open]);

  if (!open) return null;

  const handleSubmit = async () => {
    if (!selectedLabel) return;
    setSubmitting(true);
    try {
      await api.submitAnnotation(runId, { annotatedLabel: selectedLabel, reviewerNotes, reviewerName }, pt ?? undefined);
      showToast('标注提交成功');
      onClose(true);
    } catch (e: any) {
      showToast(e.message || '标注提交失败', true);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={() => onClose()}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-md p-6"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-bold text-slate-900">标注审核</h3>
          <button onClick={() => onClose()} className="p-1 text-slate-400 hover:text-slate-600"><X size={20} /></button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">当前标签</label>
            <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-700">{currentLabel || '未知'}</div>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">选择新标签</label>
            <select
              value={selectedLabel}
              onChange={e => setSelectedLabel(e.target.value)}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none bg-white"
            >
              <option value="">选择行业标签...</option>
              {taxonomyLabels.map(tl => (
                <option key={tl.id} value={tl.displayName}>{tl.displayName}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">审核备注</label>
            <textarea
              value={reviewerNotes}
              onChange={e => setReviewerNotes(e.target.value)}
              placeholder="可选备注..."
              rows={3}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none resize-none"
            />
          </div>
        </div>
        <div className="flex gap-3 mt-6">
          <button onClick={() => onClose()} className="flex-1 py-2.5 border border-slate-200 text-slate-700 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors">取消</button>
          <button onClick={handleSubmit} disabled={submitting || !selectedLabel} className="flex-1 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:bg-slate-400 transition-colors flex items-center justify-center gap-2">
            {submitting ? <><Loader2 size={14} className="animate-spin" /> 提交中...</> : <><Send size={14} /> 提交标注</>}
          </button>
        </div>
      </motion.div>
    </div>
  );
};

// --- Props ---
export interface DetailViewProps {
  runId: string;
  onBack: () => void;
  showToast?: (msg: string, isError?: boolean) => void;
  taxonomyLabels?: TaxonomyLabel[];
  currentUserName?: string;
  pt?: string | null;
  /** 自定义数据获取函数，默认使用 api.getRunDetail */
  fetchDetailFn?: (runId: string, pt?: string) => Promise<RunDetail>;
  /** 是否显示标注按钮，默认 true */
  showAnnotation?: boolean;
}

// --- DetailView 组件 ---
const DetailView = ({
  runId,
  onBack,
  showToast,
  taxonomyLabels = [],
  currentUserName = '',
  pt,
  fetchDetailFn,
  showAnnotation = true,
}: DetailViewProps) => {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [annotationOpen, setAnnotationOpen] = useState(false);

  const noopToast = (_msg: string, _isError?: boolean) => {};
  const toast = showToast ?? noopToast;

  const fetchDetail = useCallback(() => {
    setLoading(true);
    setError(null);
    const fetcher = fetchDetailFn ?? ((rid: string, p?: string) => api.getRunDetail(rid, p));
    fetcher(runId, pt ?? undefined)
      .then(setRun)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [runId, pt, fetchDetailFn]);

  useEffect(() => { fetchDetail(); }, [fetchDetail]);

  if (loading) {
    return (
      <div className="space-y-6 pb-20">
        <Skeleton className="h-16 w-full rounded-2xl" />
        <div className="grid grid-cols-2 gap-6">
          <Skeleton className="h-96 rounded-2xl" />
          <Skeleton className="h-96 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (error || !run) {
    return <ErrorBox message={error || '无法加载运行详情'} onRetry={fetchDetail} />;
  }

  const dr = run.decisionRecord || {} as Record<string, unknown>;
  const annotations = (run.annotations || []) as Array<Record<string, unknown> | AnnotationRecord>;
  const latestAnnotation = annotations.length > 0 ? annotations[annotations.length - 1] : null;
  const latestAnnotationRecord = (latestAnnotation || {}) as Record<string, unknown>;
  const modelConfLevel = (dr.confidenceLevel || dr.confidence_level || '') as string;
  const confInfo = confidenceLevelMap[modelConfLevel] || { num: 0, label: modelConfLevel || '未知', color: 'text-slate-500' };
  const modelLabel = (dr.finalLabel || dr.final_label || '未知') as string;
  const resolveLabel = (raw: string) => resolveLabelName(raw, taxonomyLabels);
  const resolvedModelLabel = resolveLabel(modelLabel);
  const annotatedLabelRaw = ((latestAnnotationRecord.annotatedLabel || latestAnnotationRecord.annotated_label) || '') as string;
  const resolvedAnnotatedLabel = annotatedLabelRaw ? resolveLabel(annotatedLabelRaw) : '';
  const finalLabel = resolvedAnnotatedLabel || resolvedModelLabel || '未知';
  const decisionReason = (dr.decisionReason || dr.decision_reason || '') as string;
  const evidence = (dr.supportingEvidence || dr.supporting_evidence || []) as string[];
  const wide = run.wideRow || {} as Record<string, unknown>;
  const topJobs = (wide.topJobNames || wide.top_job_names || []) as Array<Record<string, unknown>>;
  const recentJobs = (wide.jobsRecent_20 || wide.jobs_recent_20 || wide.jobsRecent20 || []) as Array<Record<string, unknown>>;
  const totalJobCount = (wide.totalJobPostCnt_90d || wide.total_job_post_cnt_90d || wide.totalJobPostCnt90d || 0) as number;
  const distinctJobCount = (wide.distinctJobNameCnt_90d || wide.distinct_job_name_cnt_90d || wide.distinctJobNameCnt90d || 0) as number;
  const authenticationTime = (wide.authenticationTime || wide.authentication_time || '') as string;
  const latestPublishTime = (wide.latestPublishTime || wide.latest_publish_time || '') as string;
  const latestPublishJobNames = (wide.latestPublishJobNames || wide.latest_publish_job_names || []) as string[];
  const sp = run.staticProfile as Record<string, unknown> | null;
  const dp = run.dynamicProfile as Record<string, unknown> | null;
  const timing = (run.timingMs || {}) as Record<string, number>;
  const fmtMs = (key: string) => { const v = timing[key]; return v != null ? `${Math.round(v)}ms` : ''; };

  const pipelineNodes = [
    { id: 'load', icon: Database, color: 'bg-blue-500', label: '数据加载', summary: '企业宽表数据 + 版本元信息', timingKey: '' },
    { id: 'static', icon: FileText, color: 'bg-indigo-500', label: '静态画像', summary: sp ? (sp.summary || '已生成') as string : '暂无数据', timingKey: 'static_profile' },
    { id: 'dynamic', icon: Activity, color: 'bg-purple-500', label: '动态画像', summary: dp ? (dp.summary || '已生成') as string : '暂无数据', timingKey: 'dynamic_profile' },
    { id: 'decision', icon: BrainCircuit, color: 'bg-amber-500', label: '最终裁决', summary: `${finalLabel} · ${confInfo.label}`, timingKey: 'final_decision' },
  ];

  const handleAnnotationClose = (submitted?: boolean) => {
    setAnnotationOpen(false);
    if (submitted) fetchDetail();
  };

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }} className="relative">
      {/* Header */}
      <div className="flex items-center justify-between bg-white p-4 rounded-2xl border border-slate-200 shadow-sm mb-6 sticky top-0 z-10">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="flex items-center gap-2 text-blue-600 hover:text-blue-700 font-medium px-3 py-1.5 rounded-lg hover:bg-blue-50 transition-colors">
            <ArrowLeft size={18} /> 返回列表
          </button>
          <div className="w-px h-6 bg-slate-200" />
          <h2 className="text-lg font-bold text-slate-900 flex items-center gap-3 flex-wrap">
            {run.enterpriseName}
            <span className="px-2.5 py-0.5 rounded-lg text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200">{finalLabel}</span>
            <span className={`px-2.5 py-0.5 rounded-lg text-xs font-bold border ${getConfidenceBadgeClass(confInfo.num)}`}>{confInfo.label}</span>
            {annotations.length > 0 && (
              <span className="px-2.5 py-0.5 rounded-lg text-xs font-bold bg-sky-50 text-sky-700 border border-sky-200">人工标注</span>
            )}
          </h2>
        </div>
        {showAnnotation && (
          <button
            onClick={() => setAnnotationOpen(true)}
            className="px-5 py-2.5 bg-slate-900 text-white text-sm font-medium rounded-xl hover:bg-slate-800 transition-colors flex items-center gap-2 shadow-sm"
          >
            <Tag size={16} /> 标注
          </button>
        )}
      </div>

      {/* Split Panel */}
      <div className="grid grid-cols-2 gap-6">
        {/* Left Panel - Enterprise Info */}
        <div className="space-y-6">
          {/* Basic Info */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
              <h3 className="text-sm font-bold text-slate-800">企业基本信息</h3>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs text-slate-400 mb-1">企业名称</div>
                  <div className="text-sm font-semibold text-slate-900">{run.enterpriseName}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-400 mb-1">信用代码</div>
                  <div className="text-sm font-mono text-slate-700">{run.entityKey}</div>
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-400 mb-1">经营范围</div>
                <div className="text-sm text-slate-600 leading-relaxed">{run.businessScope || '暂无数据'}</div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs text-slate-400 mb-1">企业认证时间</div>
                  <div className="text-sm text-slate-700">{authenticationTime || '暂无数据'}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-400 mb-1">最新发布时间</div>
                  <div className="text-sm text-slate-700">{latestPublishTime || '暂无数据'}</div>
                </div>
              </div>
              {latestPublishJobNames.length > 0 && (
                <div>
                  <div className="text-xs text-slate-400 mb-1">最新发布工种</div>
                  <div className="flex flex-wrap gap-1.5">
                    {latestPublishJobNames.map((name, i) => (
                      <span key={i} className="px-2 py-0.5 text-xs rounded-md bg-slate-100 text-slate-700">{name}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* 90天岗位统计 */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
            <h3 className="text-sm font-bold text-slate-800 mb-4">90天岗位统计</h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-blue-50 rounded-lg p-4">
                <div className="text-xs text-blue-500 mb-1">岗位总数</div>
                <div className="text-2xl font-bold text-slate-900">{totalJobCount}</div>
              </div>
              <div className="bg-indigo-50 rounded-lg p-4">
                <div className="text-xs text-indigo-500 mb-1">去重工种数</div>
                <div className="text-2xl font-bold text-slate-900">{distinctJobCount}</div>
              </div>
            </div>
          </div>

          {/* Top 工种分布 */}
          {topJobs.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
                <h3 className="text-sm font-bold text-slate-800">Top 工种分布</h3>
              </div>
              <div className="p-6 space-y-3">
                {topJobs.map((job, i) => {
                  const name = (job.jobName || job.job_name || '') as string;
                  const cnt = (job.cnt || 0) as number;
                  const ratio = (job.ratio || 0) as number;
                  const pct = Math.round(ratio * 100);
                  return (
                    <div key={i} className="flex items-center gap-3">
                      <span className="text-xs font-mono text-slate-400 w-5">{i + 1}</span>
                      <span className="text-sm text-slate-800 w-32 truncate">{name}</span>
                      <div className="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-indigo-500" style={{ width: `${Math.max(pct, 3)}%` }} />
                      </div>
                      <span className="text-xs font-mono text-slate-500 w-10 text-right">{pct}%</span>
                      <span className="text-xs text-slate-400 w-10 text-right">{cnt}次</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 近期招聘记录 */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-800">近期招聘记录</h3>
              <span className="text-xs text-slate-400">{recentJobs.length > 0 ? `最近 ${recentJobs.length} 条` : ''}</span>
            </div>
            {recentJobs.length > 0 ? (
              <div className="divide-y divide-slate-100 max-h-72 overflow-y-auto">
                {recentJobs.map((job, i) => {
                  const name = (job.jobName || job.job_name || '') as string;
                  const desc = (job.desc || '') as string;
                  const addTime = (job.addTime || job.add_time || '') as string;
                  return (
                    <div key={i} className="px-6 py-3 flex items-start gap-4 hover:bg-slate-50/50">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-slate-800">{name}</div>
                        {desc && <div className="text-xs text-slate-500 mt-0.5 truncate">{desc}</div>}
                      </div>
                      <div className="text-xs text-slate-400 whitespace-nowrap">{addTime}</div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="p-8 text-center text-sm text-slate-400">暂无近期招聘记录</div>
            )}
          </div>
        </div>

        {/* Right Panel - 推理流程 */}
        <div className="space-y-6">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
              <h3 className="text-sm font-bold text-slate-800">推理流程</h3>
            </div>
            <div className="p-6">
              <div className="relative">
                {/* Vertical connecting line */}
                <div className="absolute left-5 top-6 bottom-6 w-0.5 bg-slate-200" />
                <div className="space-y-1">
                  {pipelineNodes.map((node) => (
                    <div key={node.id}>
                      <div className="flex items-center gap-4 py-3 relative z-10">
                        <div className={`w-10 h-10 rounded-full ${node.color} text-white flex items-center justify-center shadow-md ring-4 ring-white shrink-0`}>
                          <node.icon size={18} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-bold text-slate-700">{node.label}</span>
                            {node.timingKey && fmtMs(node.timingKey) && (
                              <span className="text-[10px] font-mono text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">{fmtMs(node.timingKey)}</span>
                            )}
                          </div>
                          <div className="text-xs text-slate-500 truncate">{node.summary}</div>
                        </div>
                      </div>
                      {/* Always-expanded node detail */}
                      <div className="ml-14 mb-3">
                        <div className="bg-slate-50 rounded-lg p-4 border border-slate-100">
                          {node.id === 'load' && (
                            <div className="grid grid-cols-2 gap-3">
                              <div className="bg-blue-50 rounded-lg p-2">
                                <div className="text-[10px] text-blue-500">数据来源</div>
                                <div className="text-xs font-medium text-slate-800">企业宽表 (WideRow)</div>
                              </div>
                              <div className="bg-blue-50 rounded-lg p-2">
                                <div className="text-[10px] text-blue-500">运行 ID</div>
                                <div className="text-xs font-mono text-slate-700">{run.runId}</div>
                              </div>
                              {run.audit?.featureSchemaVersion && (
                                <div className="bg-slate-100 rounded-lg p-2">
                                  <div className="text-[10px] text-slate-400">特征版本</div>
                                  <div className="text-xs font-mono text-slate-700">{String(run.audit.featureSchemaVersion || run.audit.feature_schema_version || '-')}</div>
                                </div>
                              )}
                              {run.audit?.taxonomyVersion && (
                                <div className="bg-slate-100 rounded-lg p-2">
                                  <div className="text-[10px] text-slate-400">标签版本</div>
                                  <div className="text-xs font-mono text-slate-700">{String(run.audit.taxonomyVersion || run.audit.taxonomy_version || '-')}</div>
                                </div>
                              )}
                              {run.audit?.graphVersion && (
                                <div className="bg-slate-100 rounded-lg p-2">
                                  <div className="text-[10px] text-slate-400">图版本</div>
                                  <div className="text-xs font-mono text-slate-700">{String(run.audit.graphVersion || run.audit.graph_version || '-')}</div>
                                </div>
                              )}
                            </div>
                          )}
                          {node.id === 'static' && (
                            sp ? (
                              <div className="space-y-3">
                                {sp.summary && <div className="text-sm text-slate-700">{sp.summary as string}</div>}
                                {(sp.top3Labels || sp.top3_labels) && (
                                  <div className="space-y-1.5">
                                    {((sp.top3Labels || sp.top3_labels || []) as Array<Record<string, unknown>>).map((item, i) => (
                                      <div key={i} className="flex items-start gap-2 text-xs">
                                        <span className="px-1.5 py-0.5 bg-indigo-100 text-indigo-700 font-bold rounded shrink-0">{item.label as string}</span>
                                        <span className="text-slate-600">{item.reason as string}</span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            ) : <div className="text-xs text-slate-400">暂无静态画像数据</div>
                          )}
                          {node.id === 'dynamic' && (
                            dp ? (
                              <div className="space-y-3">
                                {dp.summary && <div className="text-sm text-slate-700">{dp.summary as string}</div>}
                                {(dp.coreJobs || dp.core_jobs) && (
                                  <div className="flex flex-wrap gap-1">
                                    {((dp.coreJobs || dp.core_jobs || []) as string[]).map((j, i) => (
                                      <span key={i} className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded-md">{j}</span>
                                    ))}
                                  </div>
                                )}
                                <div className="flex gap-4 text-xs">
                                  {dp.scene && <span><span className="text-slate-400">场景：</span><span className="text-slate-700">{dp.scene as string}</span></span>}
                                  {dp.continuity && <span><span className="text-slate-400">持续性：</span><span className="text-slate-700">{dp.continuity as string}</span></span>}
                                </div>
                              </div>
                            ) : <div className="text-xs text-slate-400">暂无动态画像数据</div>
                          )}
                          {node.id === 'decision' && (
                            <div className="space-y-3">
                              <div className="flex gap-3">
                                <div className="bg-amber-50 rounded-lg p-3 flex-1"><div className="text-[10px] text-amber-500">最终标签</div><div className="text-sm font-bold text-slate-900">{finalLabel}</div></div>
                                <div className="bg-amber-50 rounded-lg p-3 flex-1"><div className="text-[10px] text-amber-500">置信度</div><div className={`text-sm font-bold ${confInfo.color}`}>{confInfo.label}</div></div>
                              </div>
                              {annotations.length > 0 && (
                                <div className="text-xs text-sky-700 bg-sky-50 border border-sky-200 rounded-lg px-3 py-2">
                                  模型预测：{resolveLabel(modelLabel)}，人工标注：{resolvedAnnotatedLabel}
                                </div>
                              )}
                              {decisionReason && <div className="text-xs text-slate-700 leading-relaxed">{decisionReason}</div>}
                              {evidence.length > 0 && (
                                <div className="space-y-1">
                                  {evidence.map((ev, i) => (
                                    <div key={i} className="flex items-start gap-1.5 text-xs text-slate-600"><span className="text-amber-500">•</span>{ev}</div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Timing summary */}
              {Object.keys(timing).length > 0 && (
                <div className="mt-4 pt-4 border-t border-slate-100 flex items-center gap-3 flex-wrap">
                  <span className="text-xs text-slate-400">耗时:</span>
                  {Object.entries(timing).map(([k, v]) => (
                    <span key={k} className="text-xs font-mono text-slate-500">
                      <span className="text-slate-400">{k === 'static_profile' ? '静态' : k === 'dynamic_profile' ? '动态' : k === 'final_decision' ? '裁决' : k}:</span> {Math.round(v)}ms
                    </span>
                  ))}
                  <span className="text-xs font-mono font-bold text-blue-600">
                    总计: {Math.round(Object.values(timing).reduce((a, b) => a + b, 0))}ms
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* 人工标注历史 */}
          <div className="bg-white rounded-2xl border border-sky-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-sky-100 bg-sky-50/50 flex items-center justify-between">
              <h3 className="text-sm font-bold text-sky-800 flex items-center gap-2"><Tag size={14} /> 人工标注记录</h3>
              <span className="text-xs text-slate-400">{annotations.length}/3</span>
            </div>
            <div className="p-6">
              {annotations.length > 0 ? (
                <div className="space-y-3">
                  {annotations.map((ann, i) => {
                    const annRecord = ann as Record<string, unknown>;
                    const label = resolveLabel((annRecord.annotatedLabel || annRecord.annotated_label || '') as string);
                    const notes = (annRecord.reviewerNotes || annRecord.reviewer_notes || '') as string;
                    const createdAt = (annRecord.createdAt || annRecord.created_at || '') as string;
                    const reviewer = (annRecord.reviewerName || annRecord.reviewer_name || '') as string;
                    return (
                      <div key={i} className="bg-sky-50/60 border border-sky-100 rounded-lg p-3 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-slate-400">第 {i + 1} 次标注</span>
                            <span className="px-2 py-0.5 rounded-md text-xs font-bold bg-sky-100 text-sky-700 border border-sky-200">{label}</span>
                            {reviewer && <span className="text-xs text-slate-500">by {reviewer}</span>}
                          </div>
                          <span className="text-[10px] text-slate-400 font-mono">{formatDateTime(createdAt)}</span>
                        </div>
                        {notes && <div className="text-xs text-slate-600 leading-relaxed">{notes}</div>}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-center text-sm text-slate-400 py-4">暂无标注记录，点击右上角「标注」按钮添加</div>
              )}
              {annotations.length >= 3 && (
                <div className="mt-3 text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-center">
                  已达到最大标注次数 (3次)
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Annotation Dialog */}
      {showAnnotation && (
        <AnimatePresence>
          {annotationOpen && (
            <AnnotationDialog
              open={annotationOpen}
              onClose={handleAnnotationClose}
              runId={run.runId}
              currentLabel={finalLabel}
              currentNotes={''}
              reviewerName={currentUserName}
              taxonomyLabels={taxonomyLabels}
              showToast={toast}
              pt={pt}
            />
          )}
        </AnimatePresence>
      )}
    </motion.div>
  );
};

export default DetailView;
