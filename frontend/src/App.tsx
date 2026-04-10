import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  LayoutDashboard,
  ClipboardList,
  AlertCircle,
  Settings,
  Search,
  Bell,
  Building2,
  CheckCircle2,
  Clock,
  Database,
  Activity,
  ChevronRight,
  FileText,
  ShieldAlert,
  Zap,
  Loader2,
  Car,
  Truck,
  Music,
  Video,
  Home,
  Building,
  Smartphone,
  Shield,
  HardHat,
  Bike,
  Utensils,
  HelpCircle,
  BookOpen,
  ArrowLeft,
  X,
  RefreshCw,
  Save,
  Send,
  XCircle,
  BrainCircuit,
  Tag,
  LogOut,
  ChevronDown,
} from 'lucide-react';
import { api } from './api/client';
import type {
  AdminAuthAudit,
  AdminOverview,
  AccessSettings,
  AnnotationRecord,
  AuthSession,
  StatsResponse,
  RunSummary,
  PaginatedResponse,
  RunDetail,
  SearchResult,
  FallbackRecord,
  TaxonomyLabel,
  TaxonomyResponse,
  SettingsResponse,
} from './api/types';
import { JOB_NAMES } from './job_names';

// --- Taxonomy Icon Map ---
const TAXONOMY_ICON_MAP: Record<string, { icon: any; color: string; bg: string }> = {
  ride_hailing: { icon: Car, color: 'text-blue-500', bg: 'bg-blue-50' },
  freight_logistics: { icon: Truck, color: 'text-sky-600', bg: 'bg-sky-50' },
  entertainment_services: { icon: Music, color: 'text-purple-500', bg: 'bg-purple-50' },
  cultural_media: { icon: Video, color: 'text-pink-500', bg: 'bg-pink-50' },
  domestic_services: { icon: Home, color: 'text-teal-500', bg: 'bg-teal-50' },
  property_management: { icon: Building, color: 'text-indigo-500', bg: 'bg-indigo-50' },
  gig_platform: { icon: Smartphone, color: 'text-cyan-500', bg: 'bg-cyan-50' },
  security_services: { icon: Shield, color: 'text-slate-700', bg: 'bg-slate-100' },
  construction: { icon: HardHat, color: 'text-amber-600', bg: 'bg-amber-50' },
  rider_delivery: { icon: Bike, color: 'text-orange-500', bg: 'bg-orange-50' },
  food_services: { icon: Utensils, color: 'text-red-500', bg: 'bg-red-50' },
  other: { icon: HelpCircle, color: 'text-slate-400', bg: 'bg-slate-50' },
};

const TAXONOMY_NAME_ICON_MAP: Record<string, { icon: any; color: string; bg: string }> = {
  '网约车': { icon: Car, color: 'text-blue-500', bg: 'bg-blue-50' },
  '货运物流': { icon: Truck, color: 'text-sky-600', bg: 'bg-sky-50' },
  '娱乐服务': { icon: Music, color: 'text-purple-500', bg: 'bg-purple-50' },
  '文化传媒': { icon: Video, color: 'text-pink-500', bg: 'bg-pink-50' },
  '家政服务': { icon: Home, color: 'text-teal-500', bg: 'bg-teal-50' },
  '物业管理': { icon: Building, color: 'text-indigo-500', bg: 'bg-indigo-50' },
  '接单类平台': { icon: Smartphone, color: 'text-cyan-500', bg: 'bg-cyan-50' },
  '安保服务': { icon: Shield, color: 'text-slate-700', bg: 'bg-slate-100' },
  '建筑类': { icon: HardHat, color: 'text-amber-600', bg: 'bg-amber-50' },
  '骑手配送': { icon: Bike, color: 'text-orange-500', bg: 'bg-orange-50' },
  '餐饮服务': { icon: Utensils, color: 'text-red-500', bg: 'bg-red-50' },
  '其他': { icon: HelpCircle, color: 'text-slate-400', bg: 'bg-slate-50' },
};

function getTaxonomyIcon(label: TaxonomyLabel) {
  return TAXONOMY_ICON_MAP[label.id] || TAXONOMY_NAME_ICON_MAP[label.displayName] || { icon: HelpCircle, color: 'text-slate-400', bg: 'bg-slate-50' };
}

// taxonomy ID → 中文名映射（用于将英文ID转为中文显示）
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
  // 先查静态映射
  if (TAXONOMY_ID_TO_NAME[raw]) return TAXONOMY_ID_TO_NAME[raw];
  // 再查动态 taxonomy
  if (taxonomyLabels) {
    const found = taxonomyLabels.find(tl => tl.id === raw);
    if (found) return found.displayName;
  }
  return raw;
}

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

// --- Pipeline Nodes ---
const PIPELINE_NODES = [
  { id: 'loader', name: '批量加载器', status: 'active' },
  { id: 'static', name: '静态画像', status: 'active' },
  { id: 'dynamic', name: '动态画像', status: 'active' },
  { id: 'decision', name: '最终裁决', status: 'active' },
];

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

// --- Small Components ---
const Skeleton = ({ className = '' }: { className?: string }) => (
  <div className={`animate-pulse bg-slate-200 rounded ${className}`} />
);

const SidebarItem = ({ icon: Icon, label, active = false, onClick }: { icon: any; label: string; active?: boolean; onClick?: () => void }) => (
  <div
    onClick={onClick}
    className={`flex items-center gap-3 px-4 py-3 rounded-xl cursor-pointer transition-all duration-200 ${active ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`}
  >
    <Icon size={20} className={active ? 'text-white' : 'text-slate-400'} />
    <span className="font-medium text-sm">{label}</span>
  </div>
);

const StatusBadge = ({ status }: { status: string }) => {
  const isFormal = status === 'formal';
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
      isFormal
        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
        : 'bg-amber-50 text-amber-700 border-amber-200'
    }`}>
      {isFormal ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
      {isFormal ? '正式输出' : '待审核'}
    </span>
  );
};

const ErrorBox = ({ message, onRetry }: { message: string; onRetry: () => void }) => (
  <div className="flex flex-col items-center justify-center py-12 text-center">
    <XCircle size={40} className="text-red-400 mb-3" />
    <p className="text-sm text-red-600 mb-4">{message}</p>
    <button onClick={onRetry} className="flex items-center gap-2 px-4 py-2 bg-blue-50 text-blue-600 hover:bg-blue-100 rounded-lg text-sm font-medium transition-colors">
      <RefreshCw size={14} /> 重试
    </button>
  </div>
);

const FullScreenState = ({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) => (
  <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.14),_transparent_50%),linear-gradient(180deg,#f8fbff_0%,#eef4ff_100%)] flex items-center justify-center p-6">
    <div className="w-full max-w-lg rounded-[28px] border border-slate-200 bg-white/90 backdrop-blur-xl shadow-[0_30px_80px_-40px_rgba(15,23,42,0.45)] p-10 text-center">
      <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 shadow-lg shadow-blue-500/25">
        <Building2 size={26} className="text-white" />
      </div>
      <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
      <p className="mt-3 text-sm leading-6 text-slate-600">{description}</p>
      {action ? <div className="mt-8">{action}</div> : null}
    </div>
  </div>
);


// --- Batch Confirm Dialog ---
const BatchConfirmDialog = ({ open, onClose, onSuccess, showToast }: { open: boolean; onClose: () => void; onSuccess: () => void; showToast: (msg: string, isError?: boolean) => void }) => {
  const [pt, setPt] = useState(() => {
    const d = new Date(); return `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`;
  });
  const [inputPath, setInputPath] = useState('');
  const [workerCount, setWorkerCount] = useState(4);
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const handleConfirm = async () => {
    setSubmitting(true);
    try {
      const result = await api.triggerBatch({ pt, inputPath, workerCount });
      showToast(`批量任务已提交: ${result.taskId}`);
      onSuccess();
      onClose();
    } catch (e: any) {
      showToast(e.message || '批量任务触发失败', true);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-md p-6"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-bold text-slate-900">确认触发批量分类</h3>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600"><X size={20} /></button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">业务日期 (pt)</label>
            <input value={pt} onChange={e => setPt(e.target.value)} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none" placeholder="yyyymmdd" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">数据源路径 (input_path)</label>
            <input value={inputPath} onChange={e => setInputPath(e.target.value)} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none" placeholder="/path/to/input.csv" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">并发工作线程数 (worker_count)</label>
            <input type="number" value={workerCount} onChange={e => setWorkerCount(Number(e.target.value))} min={1} max={32} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none" />
          </div>
        </div>
        <div className="flex gap-3 mt-6">
          <button onClick={onClose} className="flex-1 py-2.5 border border-slate-200 text-slate-700 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors">取消</button>
          <button onClick={handleConfirm} disabled={submitting || !pt || !inputPath} className="flex-1 py-2.5 bg-slate-900 text-white rounded-xl text-sm font-medium hover:bg-slate-800 disabled:bg-slate-400 transition-colors flex items-center justify-center gap-2">
            {submitting ? <><Loader2 size={14} className="animate-spin" /> 提交中...</> : <><Send size={14} /> 确认执行</>}
          </button>
        </div>
      </motion.div>
    </div>
  );
};

// --- Annotation Dialog (标注对话框) ---
const AnnotationDialog = ({
  open,
  onClose,
  runId,
  currentLabel,
  currentNotes = '',
  reviewerName = '',
  taxonomyLabels,
  showToast,
}: {
  open: boolean;
  onClose: (submitted?: boolean) => void;
  runId: string;
  currentLabel: string;
  currentNotes?: string;
  reviewerName?: string;
  taxonomyLabels: TaxonomyLabel[];
  showToast: (msg: string, isError?: boolean) => void;
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
      await api.submitAnnotation(runId, { annotatedLabel: selectedLabel, reviewerNotes, reviewerName });
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


// --- Access Requests Panel (Admin) ---
const AccessRequestsPanel = ({ showToast, onApproved }: { showToast: (msg: string, isError?: boolean) => void; onApproved?: () => void }) => {
  const [requests, setRequests] = useState<Array<{ openId: string; name: string; email: string; enterpriseEmail: string; tenantKey: string; reason: string; status: string; reviewerNote: string; createdAt: string; updatedAt: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('pending');

  const fetchRequests = useCallback(() => {
    setLoading(true);
    api.getAccessRequests(filter)
      .then(setRequests)
      .catch(() => setRequests([]))
      .finally(() => setLoading(false));
  }, [filter]);

  useEffect(() => { fetchRequests(); }, [fetchRequests]);

  const handleReview = async (openId: string, action: 'approve' | 'reject' | 'revoke') => {
    try {
      await api.reviewAccessRequest(openId, action);
      showToast(action === 'approve' ? '已批准' : action === 'revoke' ? '已撤销权限' : '已拒绝');
      fetchRequests();
      if ((action === 'approve' || action === 'revoke') && onApproved) onApproved();
    } catch (e: any) {
      showToast(e.message || '操作失败', true);
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
        <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
          <Bell size={14} className="text-amber-500" /> 权限申请审批
        </h3>
        <div className="flex gap-2">
          {(['pending', 'approved', 'rejected', ''] as const).map(f => (
            <button
              key={f || 'all'}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                filter === f ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {f === 'pending' ? '待审批' : f === 'approved' ? '已批准' : f === 'rejected' ? '已拒绝' : '全部'}
            </button>
          ))}
        </div>
      </div>
      {loading ? (
        <div className="p-6 space-y-3">
          {Array.from({ length: 3 }).map((_, i) => <div key={i}><Skeleton className="h-10 w-full rounded-lg" /></div>)}
        </div>
      ) : requests.length > 0 ? (
        <div className="divide-y divide-slate-100">
          {requests.map(req => (
            <div key={req.openId} className="px-6 py-4 flex items-center gap-4">
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-slate-900">{req.name || req.openId}</div>
                <div className="text-xs text-slate-500 mt-0.5">
                  {req.enterpriseEmail || req.email || '-'} · 企业: {req.tenantKey || '-'}
                </div>
                {req.reason && <div className="text-xs text-slate-400 mt-1">理由: {req.reason}</div>}
                <div className="text-[10px] text-slate-400 mt-1">{formatDateTime(req.createdAt)}</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {req.status === 'pending' ? (
                  <>
                    <button
                      onClick={() => handleReview(req.openId, 'approve')}
                      className="px-3 py-1.5 bg-emerald-50 text-emerald-700 rounded-lg text-xs font-medium hover:bg-emerald-100 transition-colors"
                    >
                      批准
                    </button>
                    <button
                      onClick={() => handleReview(req.openId, 'reject')}
                      className="px-3 py-1.5 bg-red-50 text-red-600 rounded-lg text-xs font-medium hover:bg-red-100 transition-colors"
                    >
                      拒绝
                    </button>
                  </>
                ) : req.status === 'approved' ? (
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700">
                      已批准
                    </span>
                    <button
                      onClick={() => handleReview(req.openId, 'revoke')}
                      className="px-3 py-1.5 bg-amber-50 text-amber-700 rounded-lg text-xs font-medium hover:bg-amber-100 transition-colors"
                    >
                      撤销权限
                    </button>
                  </div>
                ) : (
                  <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${
                    req.status === 'revoked' ? 'bg-amber-50 text-amber-700' : 'bg-red-50 text-red-600'
                  }`}>
                    {req.status === 'revoked' ? '已撤销' : '已拒绝'}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="p-8 text-center text-sm text-slate-400">暂无权限申请</div>
      )}
    </div>
  );
};

// --- Detail View (Split Panel) ---
const DetailView = ({
  runId,
  onBack,
  showToast,
  taxonomyLabels,
  currentUserName = '',
}: {
  runId: string;
  onBack: () => void;
  showToast: (msg: string, isError?: boolean) => void;
  taxonomyLabels: TaxonomyLabel[];
  currentUserName?: string;
}) => {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [annotationOpen, setAnnotationOpen] = useState(false);

  const fetchDetail = useCallback(() => {
    setLoading(true);
    setError(null);
    api.getRunDetail(runId)
      .then(setRun)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [runId]);

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
  // 将 taxonomy ID 转为中文 displayName
  const resolveLabel = (raw: string) => resolveLabelName(raw, taxonomyLabels);
  const resolvedModelLabel = resolveLabel(modelLabel);
  const annotatedLabelRaw = ((latestAnnotationRecord.annotatedLabel || latestAnnotationRecord.annotated_label) || '') as string;
  const resolvedAnnotatedLabel = annotatedLabelRaw ? resolveLabel(annotatedLabelRaw) : '';
  const finalLabel = resolvedAnnotatedLabel || resolvedModelLabel || '未知';
  const decisionReason = (dr.decisionReason || dr.decision_reason || '') as string;
  const evidence = (dr.supportingEvidence || dr.supporting_evidence || []) as string[];
  const route = run.route || 'unknown';
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
        <button
          onClick={() => setAnnotationOpen(true)}
          className="px-5 py-2.5 bg-slate-900 text-white text-sm font-medium rounded-xl hover:bg-slate-800 transition-colors flex items-center gap-2 shadow-sm"
        >
          <Tag size={16} /> 标注
        </button>
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

          {/* 人工标注历史 - 放在推理流程之后 */}
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
            showToast={showToast}
          />
        )}
      </AnimatePresence>
    </motion.div>
  );
};


// --- Main App Component ---
export default function App() {
  // Navigation: classify | review-list | dashboard | admin-home | taxonomy | settings
  const [activeTab, setActiveTab] = useState('classify');
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [toastIsError, setToastIsError] = useState(false);
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [accessRequestReason, setAccessRequestReason] = useState('');
  const [accessRequestSubmitting, setAccessRequestSubmitting] = useState(false);
  const [localReqStatus, setLocalReqStatus] = useState<string | null | undefined>(null);

  // Dashboard stats
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState<string | null>(null);

  // Annotation archive
  const [annotationArchive, setAnnotationArchive] = useState<Record<string, unknown>[]>([]);
  const [archiveLoading, setArchiveLoading] = useState(false);

  // Runs (used by 分类审核台)
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsOffset, setRunsOffset] = useState(0);
  const [runsLoading, setRunsLoading] = useState(true);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [runsLoadingMore, setRunsLoadingMore] = useState(false);
  const [runsFilter, setRunsFilter] = useState<'all' | 'annotated' | 'unannotated'>('all');
  const [labelFilter, setLabelFilter] = useState<string | null>(null);
  const RUNS_LIMIT = 20;

  // Search
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchNoResults, setSearchNoResults] = useState(false);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);

  // Batch dialog
  const [batchDialogOpen, setBatchDialogOpen] = useState(false);

  // Classify (发起分类)
  const [classifyMode, setClassifyMode] = useState<'single' | 'batch'>('single');
  const [classifyQuery, setClassifyQuery] = useState('');
  const [classifyJobName, setClassifyJobName] = useState('');
  const [jobNameDropdownOpen, setJobNameDropdownOpen] = useState(false);
  const [classifyBatchMode, setClassifyBatchMode] = useState<'job' | 'csv'>('job');
  const [classifyPt, setClassifyPt] = useState('20260402');
  const [classifyCsvFile, setClassifyCsvFile] = useState<File | null>(null);
  const [classifySubmitting, setClassifySubmitting] = useState(false);
  const [classifyTaskId, setClassifyTaskId] = useState<string | null>(null);
  const [classifyTaskStatus, setClassifyTaskStatus] = useState<string>('');
  const [classifyStages, setClassifyStages] = useState<Array<{ name: string; status: string; elapsedMs: number | null; message: string }>>([]);
  const [classifyResultRunId, setClassifyResultRunId] = useState<string | null>(null);
  const [classifyError, setClassifyError] = useState<string | null>(null);
  const classifyPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [batchMaxRows, setBatchMaxRows] = useState(5);

  // Taxonomy
  const [taxonomy, setTaxonomy] = useState<TaxonomyResponse | null>(null);
  const [taxonomyLabels, setTaxonomyLabels] = useState<TaxonomyLabel[]>([]);
  const [taxonomyLoading, setTaxonomyLoading] = useState(true);
  const [taxonomyError, setTaxonomyError] = useState<string | null>(null);

  // Settings
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsForm, setSettingsForm] = useState<Record<string, string>>({});
  const [settingsValidation, setSettingsValidation] = useState<Record<string, string>>({});
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [prompts, setPrompts] = useState<Record<string, any> | null>(null);
  const [promptsLoading, setPromptsLoading] = useState(true);
  const [adminOverview, setAdminOverview] = useState<AdminOverview | null>(null);
  const [adminOverviewLoading, setAdminOverviewLoading] = useState(false);
  const [adminOverviewError, setAdminOverviewError] = useState<string | null>(null);
  const [accessSettings, setAccessSettings] = useState<AccessSettings | null>(null);
  const [accessSettingsLoading, setAccessSettingsLoading] = useState(false);
  const [accessSettingsError, setAccessSettingsError] = useState<string | null>(null);
  const [accessSettingsSaving, setAccessSettingsSaving] = useState(false);
  const [accessSettingsForm, setAccessSettingsForm] = useState<Record<string, string>>({
    allowedOpenIds: '',
    allowedEmails: '',
    adminOpenIds: '',
    adminEmails: '',
  });
  const [authAudit, setAuthAudit] = useState<AdminAuthAudit | null>(null);
  const [authAuditLoading, setAuthAuditLoading] = useState(false);
  const [authAuditError, setAuthAuditError] = useState<string | null>(null);

  const showToast = (msg: string, isError = false) => {
    setToastMessage(msg);
    setToastIsError(isError);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const fetchAuthSession = useCallback(() => {
    setAuthLoading(true);
    setAuthError(null);
    api.getAuthSession()
      .then(setAuthSession)
      .catch(e => setAuthError(e.message || '无法获取登录状态'))
      .finally(() => setAuthLoading(false));
  }, []);

  useEffect(() => {
    fetchAuthSession();
  }, [fetchAuthSession]);

  const authReady = !authLoading && !!authSession?.enabled && authSession.authenticated;
  const isAdmin = !!authSession?.user?.isAdmin;

  // Sync localReqStatus when authSession changes
  useEffect(() => {
    if (authSession?.requestStatus !== undefined) {
      setLocalReqStatus(authSession.requestStatus);
    }
  }, [authSession?.requestStatus]);

  // --- Data Fetching ---
  const fetchStats = useCallback(() => {
    setStatsLoading(true); setStatsError(null);
    api.getStats().then(setStats).catch(e => setStatsError(e.message)).finally(() => setStatsLoading(false));
    setArchiveLoading(true);
    api.getAnnotations().then(setAnnotationArchive).catch(() => {}).finally(() => setArchiveLoading(false));
  }, []);

  const fetchRuns = useCallback((offset = 0, append = false) => {
    if (!append) { setRunsLoading(true); setRunsError(null); } else { setRunsLoadingMore(true); }
    api.getRuns(offset, RUNS_LIMIT)
      .then((data: PaginatedResponse<RunSummary>) => {
        if (append) { setRuns(prev => [...prev, ...data.items]); }
        else { setRuns(data.items); }
        setRunsTotal(data.total);
        setRunsOffset(offset + data.items.length);
      })
      .catch(e => setRunsError(e.message))
      .finally(() => { setRunsLoading(false); setRunsLoadingMore(false); });
  }, []);

  const fetchTaxonomy = useCallback(() => {
    setTaxonomyLoading(true); setTaxonomyError(null);
    api.getTaxonomy()
      .then(data => { setTaxonomy(data); setTaxonomyLabels(data.labels); })
      .catch(e => setTaxonomyError(e.message))
      .finally(() => setTaxonomyLoading(false));
  }, []);

  const fetchSettings = useCallback(() => {
    setSettingsLoading(true); setSettingsError(null);
    api.getSettings()
      .then(data => {
        setSettings(data);
        setSettingsForm({
          llmModel: data.llmModel,
          llmTimeoutSec: String(data.llmTimeoutSec),
          llmMaxRetry: String(data.llmMaxRetry),
          workerCount: String(data.workerCount),
          providerRateLimitPerMinute: String(data.providerRateLimitPerMinute),
          maxInFlight: String(data.maxInFlight),
          batchMaxRows: String(data.batchMaxRows),
        });
        setSettingsValidation({});
      })
      .catch(e => setSettingsError(e.message))
      .finally(() => setSettingsLoading(false));
  }, []);

  const fetchAdminOverview = useCallback(() => {
    setAdminOverviewLoading(true);
    setAdminOverviewError(null);
    api.getAdminOverview()
      .then(setAdminOverview)
      .catch(e => setAdminOverviewError(e.message || '无法加载管理后台概览'))
      .finally(() => setAdminOverviewLoading(false));
  }, []);

  const toTextareaValue = (items: string[]) => items.join('\n');

  const fetchAccessSettings = useCallback(() => {
    setAccessSettingsLoading(true);
    setAccessSettingsError(null);
    api.getAccessSettings()
      .then((data) => {
        setAccessSettings(data);
        setAccessSettingsForm({
          allowedOpenIds: toTextareaValue(data.allowedOpenIds),
          allowedEmails: toTextareaValue(data.allowedEmails),
          adminOpenIds: toTextareaValue(data.adminOpenIds),
          adminEmails: toTextareaValue(data.adminEmails),
        });
      })
      .catch(e => setAccessSettingsError(e.message || '无法加载权限配置'))
      .finally(() => setAccessSettingsLoading(false));
  }, []);

  const fetchAuthAudit = useCallback(() => {
    setAuthAuditLoading(true);
    setAuthAuditError(null);
    api.getAdminAuthAudit()
      .then(setAuthAudit)
      .catch(e => setAuthAuditError(e.message || '无法加载登录审计'))
      .finally(() => setAuthAuditLoading(false));
  }, []);

  // Load data on tab change
  useEffect(() => {
    if (!authReady) return;
    if (activeTab === 'classify') { api.getBatchConfig().then(c => setBatchMaxRows(c.batchMaxRows)).catch(() => {}); }
    if (activeTab === 'dashboard') { fetchStats(); }
    if (activeTab === 'review-list') { fetchRuns(0); fetchTaxonomy(); }
    if (isAdmin && activeTab === 'admin-home') { fetchAdminOverview(); fetchAccessSettings(); fetchAuthAudit(); fetchTaxonomy(); }
    if (isAdmin && activeTab === 'settings') { fetchSettings(); api.getPrompts().then(setPrompts).catch(() => {}).finally(() => setPromptsLoading(false)); }
  }, [activeTab, authReady, fetchAccessSettings, fetchAdminOverview, fetchAuthAudit, fetchStats, fetchRuns, fetchTaxonomy, fetchSettings, isAdmin]);

  useEffect(() => {
    if (!authReady || isAdmin) return;
    if (activeTab === 'admin-home' || activeTab === 'settings') {
      setActiveTab('dashboard');
    }
  }, [activeTab, authReady, isAdmin]);

  // Search debounce
  useEffect(() => {
    if (!authReady) return;
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    if (!searchQuery.trim()) { setSearchResults([]); setSearchOpen(false); setSearchNoResults(false); return; }
    setSearchLoading(true);
    searchTimerRef.current = setTimeout(() => {
      api.search(searchQuery.trim())
        .then(results => { setSearchResults(results); setSearchOpen(true); setSearchNoResults(results.length === 0); })
        .catch(() => { setSearchResults([]); setSearchNoResults(true); })
        .finally(() => setSearchLoading(false));
    }, 300);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [authReady, searchQuery]);

  // Close search dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) setSearchOpen(false);
      if (accountMenuRef.current && !accountMenuRef.current.contains(e.target as Node)) setAccountMenuOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Poll classify task status
  useEffect(() => {
    if (!authReady) return;
    if (!classifyTaskId) return;
    const poll = () => {
      api.getClassifyStatus(classifyTaskId).then(data => {
        setClassifyStages(data.stages);
        setClassifyTaskStatus(data.status);
        setClassifyResultRunId(data.resultRunId || null);
        setClassifyError(data.error || null);
        if (data.status === 'done' || data.status === 'error') {
          if (classifyPollRef.current) { clearInterval(classifyPollRef.current); classifyPollRef.current = null; }
        }
      }).catch(() => {});
    };
    poll();
    classifyPollRef.current = setInterval(poll, 1000);
    return () => { if (classifyPollRef.current) clearInterval(classifyPollRef.current); };
  }, [authReady, classifyTaskId]);

  const handleSearchResultClick = (result: SearchResult) => {
    setSelectedRun(result.runId);
    setActiveTab('review-list');
    setSearchOpen(false);
    setSearchQuery('');
  };

  const handleLoadMore = () => { fetchRuns(runsOffset, true); };

  // Filtered runs for 分类审核台
  const filteredRuns = (() => {
    let result = runsFilter === 'all' ? runs
      : runsFilter === 'annotated' ? runs.filter(r => (r.annotations || []).length > 0)
      : runs.filter(r => (r.annotations || []).length === 0);
    if (labelFilter) {
      result = result.filter(r => {
        const raw = r.finalLabel || '';
        return raw === labelFilter || resolveLabelName(raw) === labelFilter;
      });
    }
    return result;
  })();

  // Settings validation + save
  const validateSettings = (): boolean => {
    const errors: Record<string, string> = {};
    const timeout = Number(settingsForm.llmTimeoutSec);
    const retry = Number(settingsForm.llmMaxRetry);
    const workers = Number(settingsForm.workerCount);
    const rateLimit = Number(settingsForm.providerRateLimitPerMinute);
    const maxFlight = Number(settingsForm.maxInFlight);
    const batchMax = Number(settingsForm.batchMaxRows);
    if (!settingsForm.llmModel?.trim()) errors.llmModel = '模型名称不能为空';
    if (isNaN(timeout) || timeout <= 0) errors.llmTimeoutSec = '超时时间必须大于 0';
    if (isNaN(retry) || retry < 0) errors.llmMaxRetry = '重试次数不能为负数';
    if (isNaN(workers) || workers < 1 || workers > 32) errors.workerCount = '工作线程数必须在 1-32 之间';
    if (isNaN(rateLimit) || rateLimit < 1) errors.providerRateLimitPerMinute = '限流次数必须大于 0';
    if (isNaN(maxFlight) || maxFlight < 1) errors.maxInFlight = '最大并发数必须大于 0';
    if (isNaN(batchMax) || batchMax < 1 || batchMax > 100) errors.batchMaxRows = '单次最大条数必须在 1-100 之间';
    setSettingsValidation(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSaveSettings = async () => {
    if (!validateSettings()) return;
    setSettingsSaving(true);
    try {
      const updated = await api.updateSettings({
        llmModel: settingsForm.llmModel,
        llmTimeoutSec: Number(settingsForm.llmTimeoutSec),
        llmMaxRetry: Number(settingsForm.llmMaxRetry),
        workerCount: Number(settingsForm.workerCount),
        providerRateLimitPerMinute: Number(settingsForm.providerRateLimitPerMinute),
        maxInFlight: Number(settingsForm.maxInFlight),
        batchMaxRows: Number(settingsForm.batchMaxRows),
      });
      setSettings(updated);
      setSettingsForm({
        llmModel: updated.llmModel,
        llmTimeoutSec: String(updated.llmTimeoutSec),
        llmMaxRetry: String(updated.llmMaxRetry),
        workerCount: String(updated.workerCount),
        providerRateLimitPerMinute: String(updated.providerRateLimitPerMinute),
        maxInFlight: String(updated.maxInFlight),
        batchMaxRows: String(updated.batchMaxRows),
      });
      showToast('配置保存成功');
    } catch (e: any) {
      showToast(e.message || '配置保存失败', true);
    } finally {
      setSettingsSaving(false);
    }
  };

  const parseTextareaItems = (value: string) =>
    value
      .split('\n')
      .map(item => item.trim())
      .filter(Boolean);

  const handleSaveAccessSettings = async () => {
    setAccessSettingsSaving(true);
    try {
      const updated = await api.updateAccessSettings({
        allowedOpenIds: parseTextareaItems(accessSettingsForm.allowedOpenIds),
        allowedEmails: parseTextareaItems(accessSettingsForm.allowedEmails),
        adminOpenIds: parseTextareaItems(accessSettingsForm.adminOpenIds),
        adminEmails: parseTextareaItems(accessSettingsForm.adminEmails),
      });
      const session = await api.getAuthSession();
      setAccessSettings(updated);
      setAuthSession(session);
      setAccessSettingsForm({
        allowedOpenIds: toTextareaValue(updated.allowedOpenIds),
        allowedEmails: toTextareaValue(updated.allowedEmails),
        adminOpenIds: toTextareaValue(updated.adminOpenIds),
        adminEmails: toTextareaValue(updated.adminEmails),
      });
      fetchAdminOverview();
      showToast('权限配置已更新并立即生效');
    } catch (e: any) {
      showToast(e.message || '权限配置保存失败', true);
    } finally {
      setAccessSettingsSaving(false);
    }
  };

  const statsCards = stats ? [
    { label: '已处理总数', value: stats.totalProcessed.toLocaleString(), icon: Database, color: 'text-blue-600', bg: 'bg-blue-100' },
    { label: '未标注', value: stats.unannotatedCount.toLocaleString(), icon: Clock, color: 'text-amber-600', bg: 'bg-amber-100' },
    { label: '已标注', value: stats.annotatedCount.toLocaleString(), icon: Tag, color: 'text-sky-600', bg: 'bg-sky-100' },
  ] : [];

  const settingsFields = [
    { key: 'llmModel', label: 'LLM 模型名称', desc: '用于分类推理的大语言模型标识', type: 'text' },
    { key: 'llmTimeoutSec', label: '请求超时时间 (秒)', desc: '单次 LLM 请求的最大等待时间', type: 'number' },
    { key: 'llmMaxRetry', label: '最大重试次数', desc: 'LLM 请求失败后的最大重试次数', type: 'number' },
    { key: 'workerCount', label: '并发工作线程数', desc: '批量处理时的并行工作线程数 (1-32)', type: 'number' },
    { key: 'providerRateLimitPerMinute', label: '每分钟限流次数', desc: 'LLM Provider 每分钟最大请求数', type: 'number' },
    { key: 'maxInFlight', label: '最大并发任务数', desc: '同时进行中的最大 LLM 请求数', type: 'number' },
    { key: 'batchMaxRows', label: '单次最大条数', desc: '按工种/CSV 批量分类时单次最大企业数 (1-100)', type: 'number' },
  ];

  const handleLogout = async () => {
    try {
      await api.logout();
      setAuthSession(prev => prev ? { ...prev, authenticated: false, user: null } : prev);
      setSelectedRun(null);
      setSearchQuery('');
      setSearchResults([]);
      setAccountMenuOpen(false);
      await fetchAuthSession();
      showToast('已退出登录');
    } catch (e: any) {
      showToast(e.message || '退出登录失败', true);
    }
  };

  if (authLoading) {
    return (
      <FullScreenState
        title="正在检查登录状态"
        description="系统会先确认你的飞书会话，再决定是否进入行业分类操作台。"
      />
    );
  }

  if (authError) {
    return (
      <div className="min-h-screen bg-slate-50 p-8">
        <div className="mx-auto max-w-xl rounded-3xl border border-slate-200 bg-white px-8 py-10 shadow-sm">
          <ErrorBox message={authError} onRetry={fetchAuthSession} />
        </div>
      </div>
    );
  }

  if (authSession && !authSession.enabled) {
    return (
      <FullScreenState
        title="飞书认证未配置"
        description="当前环境没有启用飞书企业登录，所以系统不会放行进入操作台。请先在后端 .env 中补齐 FEISHU_AUTH_ENABLED、FEISHU_APP_ID、FEISHU_APP_SECRET、FEISHU_REDIRECT_URI、FEISHU_SESSION_SECRET 和 FRONTEND_BASE_URL。"
      />
    );
  }

  if (authSession?.enabled && !authSession.authenticated) {
    const currentPath = typeof window !== 'undefined'
      ? `${window.location.pathname}${window.location.search}`
      : '/';
    const loginUrl = api.getLoginUrl(currentPath);
    return (
      <FullScreenState
        title="飞书企业登录"
        description="请先使用飞书企业账号完成认证，认证通过后才能进入操作台查看分类结果、审核记录和运行详情。"
        action={(
          <a
            href={loginUrl}
            className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-slate-800"
          >
            使用飞书登录
            <ChevronRight size={16} />
          </a>
        )}
      />
    );
  }

  if (authSession?.accessDenied) {
    const userName = authSession?.user?.name || '未知用户';
    const tenantKey = authSession?.user?.tenantKey || '';

    const handleRequestAccess = async () => {
      setAccessRequestSubmitting(true);
      try {
        const result = await api.requestAccess(accessRequestReason);
        if (result.status === 'already_pending') {
          setLocalReqStatus('pending');
        } else if (result.status === 'already_approved') {
          await fetchAuthSession();
        } else {
          setLocalReqStatus('pending');
        }
        showToast('权限申请已提交，请等待管理员审批');
      } catch (e: any) {
        showToast(e.message || '申请提交失败', true);
      } finally {
        setAccessRequestSubmitting(false);
      }
    };

    if (localReqStatus === 'pending') {
      return (
        <FullScreenState
          title="权限申请已提交"
          description={`${userName}，你的访问权限申请正在等待管理员审批，请耐心等待。`}
          action={(
            <div className="flex gap-3 justify-center">
              <button
                onClick={fetchAuthSession}
                className="inline-flex items-center gap-2 rounded-2xl bg-blue-600 px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-blue-700"
              >
                <RefreshCw size={16} /> 刷新状态
              </button>
              <button
                onClick={handleLogout}
                className="inline-flex items-center gap-2 rounded-2xl bg-slate-200 px-6 py-3 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-300"
              >
                <LogOut size={16} /> 退出登录
              </button>
            </div>
          )}
        />
      );
    }

    if (localReqStatus === 'rejected') {
      return (
        <FullScreenState
          title="权限申请被拒绝"
          description={`${userName}，你的访问权限申请未通过审批。如有疑问请联系管理员。`}
          action={(
            <div className="flex gap-3 justify-center">
              <button
                onClick={() => setLocalReqStatus(null)}
                className="inline-flex items-center gap-2 rounded-2xl bg-blue-600 px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-blue-700"
              >
                重新申请
              </button>
              <button
                onClick={handleLogout}
                className="inline-flex items-center gap-2 rounded-2xl bg-slate-200 px-6 py-3 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-300"
              >
                <LogOut size={16} /> 退出登录
              </button>
            </div>
          )}
        />
      );
    }

    return (
      <FullScreenState
        title="申请访问权限"
        description={`${userName}，你的账号尚未获得授权。请填写申请理由，提交后等待管理员审批。${tenantKey ? `\n企业标识: ${tenantKey}` : ''}`}
        action={(
          <div className="space-y-4 w-full max-w-sm mx-auto">
            <textarea
              value={accessRequestReason}
              onChange={e => setAccessRequestReason(e.target.value)}
              placeholder="请简要说明申请理由（可选）"
              rows={3}
              className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none resize-none"
            />
            <div className="flex gap-3 justify-center">
              <button
                onClick={handleRequestAccess}
                disabled={accessRequestSubmitting}
                className="inline-flex items-center gap-2 rounded-2xl bg-blue-600 px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:bg-slate-400"
              >
                {accessRequestSubmitting ? <><Loader2 size={16} className="animate-spin" /> 提交中...</> : <><Send size={16} /> 提交申请</>}
              </button>
              <button
                onClick={handleLogout}
                className="inline-flex items-center gap-2 rounded-2xl bg-slate-200 px-6 py-3 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-300"
              >
                <LogOut size={16} /> 退出登录
              </button>
            </div>
          </div>
        )}
      />
    );
  }

  const authUserName = authSession?.user?.name || '已登录用户';
  const authInitials = authUserName.slice(0, 2).toUpperCase();
  const authAvatarUrl = authSession?.user?.avatarUrl || '';
  const authOpenId = authSession?.user?.openId || '';
  const authUserId = authSession?.user?.userId || '';
  const authEmail = authSession?.user?.enterpriseEmail || authSession?.user?.email || '';
  const authTenantKey = authSession?.user?.tenantKey || '';
  const authRoleLabel = isAdmin ? '管理员' : '业务账号';
  const authRoleBadgeClass = isAdmin
    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : 'bg-slate-100 text-slate-600 border-slate-200';
  const adminModeLabel = adminOverview?.adminMode === 'allowlist' ? '白名单管理员' : '默认管理员';
  const accessScopeLabel = adminOverview?.accessScope === 'restricted' ? '访问受限' : '所有登录用户可访问';
  const formatAuditTime = (value?: string) => {
      return formatDateTime(value);
    };

  return (
    <div className="flex h-screen bg-slate-50 font-sans overflow-hidden selection:bg-blue-200 selection:text-blue-900">
      {/* Toast */}
      <AnimatePresence>
        {toastMessage && (
          <motion.div
            initial={{ opacity: 0, y: 50, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 ${toastIsError ? 'bg-red-600' : 'bg-slate-900'} text-white px-5 py-3 rounded-xl shadow-xl border ${toastIsError ? 'border-red-500' : 'border-slate-800'}`}
          >
            {toastIsError ? <XCircle size={18} className="text-red-200" /> : <CheckCircle2 size={18} className="text-emerald-400" />}
            <span className="text-sm font-medium">{toastMessage}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Batch Dialog */}
      <AnimatePresence>
        {batchDialogOpen && (
          <BatchConfirmDialog open={batchDialogOpen} onClose={() => setBatchDialogOpen(false)} onSuccess={() => {}} showToast={showToast} />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <motion.aside initial={{ x: -250 }} animate={{ x: 0 }} className="w-64 bg-slate-950 text-slate-50 flex flex-col border-r border-slate-800 relative z-20">
        <div className="p-6 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/30">
            <Building2 size={18} className="text-white" />
          </div>
          <span className="font-bold text-lg tracking-tight">行业分类 V1.5</span>
        </div>

        <div className="px-4 py-2 flex-1 space-y-1">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4 px-4 mt-4">概览</div>
          <SidebarItem icon={Zap} label="发起分类" active={activeTab === 'classify'} onClick={() => { setActiveTab('classify'); setSelectedRun(null); }} />
          <SidebarItem icon={ClipboardList} label="分类审核台" active={activeTab === 'review-list' || !!selectedRun} onClick={() => { setActiveTab('review-list'); setSelectedRun(null); }} />
          <SidebarItem icon={LayoutDashboard} label="数据汇总" active={activeTab === 'dashboard' && !selectedRun} onClick={() => { setActiveTab('dashboard'); setSelectedRun(null); }} />

          {isAdmin && (
            <>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4 px-4 mt-8">管理后台</div>
              <SidebarItem icon={ShieldAlert} label="后台总览" active={activeTab === 'admin-home' || activeTab === 'settings'} onClick={() => { setActiveTab('admin-home'); setSelectedRun(null); }} />
              <SidebarItem icon={Settings} label="系统设置" active={activeTab === 'settings'} onClick={() => { setActiveTab('settings'); setSelectedRun(null); }} />
            </>
          )}
        </div>

        <div className="p-4 border-t border-slate-800">
          <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-900 border border-slate-800">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-sm font-medium text-slate-300">系统在线</span>
          </div>
        </div>
      </motion.aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden relative z-10">
        {/* Header */}
        <header className="h-20 bg-white/80 backdrop-blur-md border-b border-slate-200 flex items-center justify-between px-8 sticky top-0 z-30">
          <div className="flex items-center gap-4">
            <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
              {selectedRun ? '运行详情' :
               activeTab === 'dashboard' ? '数据汇总' :
               activeTab === 'review-list' ? '分类审核台' :
               activeTab === 'classify' ? '发起分类' :
               activeTab === 'admin-home' ? '管理后台' :
               '系统设置'}
            </h1>
            <span className="px-2.5 py-1 bg-slate-100 text-slate-600 text-xs font-semibold rounded-md border border-slate-200">v1.5.0</span>
          </div>

          <div className="flex items-center gap-6">
            {/* Search */}
            <div className="relative group" ref={searchRef}>
              {searchLoading ? (
                <Loader2 size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-blue-500 animate-spin" />
              ) : (
                <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-500 transition-colors" />
              )}
              <input
                type="text"
                placeholder="按企业名称或信用代码搜索..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                onFocus={() => { if (searchResults.length > 0 || searchNoResults) setSearchOpen(true); }}
                className="w-80 pl-10 pr-4 py-2.5 bg-slate-100 border-transparent focus:bg-white focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 rounded-xl text-sm transition-all outline-none"
              />
              {searchOpen && (
                <div className="absolute top-full left-0 right-0 mt-2 bg-white rounded-xl border border-slate-200 shadow-xl max-h-80 overflow-y-auto z-50">
                  {searchNoResults ? (
                    <div className="p-4 text-center text-sm text-slate-500">未找到匹配的企业</div>
                  ) : (
                    searchResults.map(r => (
                      <div key={r.runId} onClick={() => handleSearchResultClick(r)} className="px-4 py-3 hover:bg-slate-50 cursor-pointer border-b border-slate-100 last:border-0">
                        <div className="text-sm font-medium text-slate-900">{r.enterpriseName}</div>
                        <div className="flex items-center gap-3 mt-1">
                          <span className="text-xs text-slate-500 font-mono">{r.entityKey}</span>
                          {r.finalLabel && <span className="text-xs px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded">{resolveLabelName(r.finalLabel)}</span>}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
            <button onClick={() => showToast('暂无新通知')} className="relative p-2 text-slate-400 hover:text-slate-600 transition-colors">
              <Bell size={20} />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border-2 border-white" />
            </button>
            <div className="relative" ref={accountMenuRef}>
              <button
                onClick={() => setAccountMenuOpen(prev => !prev)}
                className={`flex items-center gap-3 rounded-2xl border bg-white px-3 py-2 shadow-sm transition-all ${
                  accountMenuOpen
                    ? 'border-blue-300 shadow-md shadow-blue-100'
                    : 'border-slate-200 hover:border-slate-300 hover:shadow-md'
                }`}
              >
                {authAvatarUrl ? (
                  <img
                    src={authAvatarUrl}
                    alt={authUserName}
                    className="h-10 w-10 rounded-full border border-blue-200 object-cover"
                  />
                ) : (
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-tr from-indigo-100 to-blue-100 border border-blue-200 text-blue-700 font-semibold text-sm">
                    {authInitials}
                  </div>
                )}
                <div className="min-w-0 text-left">
                  <div className="flex items-center gap-2">
                    <div className="truncate text-sm font-semibold text-slate-800">{authUserName}</div>
                    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${authRoleBadgeClass}`}>
                      {authRoleLabel}
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-slate-400">
                    {authOpenId ? `飞书ID ${authOpenId}` : (authEmail || '飞书企业账号')}
                  </div>
                </div>
                <ChevronDown
                  size={16}
                  className={`shrink-0 text-slate-400 transition-transform ${accountMenuOpen ? 'rotate-180' : ''}`}
                />
              </button>

              <AnimatePresence>
                {accountMenuOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 8, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 8, scale: 0.98 }}
                    className="absolute right-0 top-full z-50 mt-3 w-[360px] overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl shadow-slate-900/10"
                  >
                    <div className="bg-[linear-gradient(135deg,#eff6ff_0%,#ffffff_65%)] px-5 py-5">
                      <div className="flex items-start gap-4">
                        {authAvatarUrl ? (
                          <img
                            src={authAvatarUrl}
                            alt={authUserName}
                            className="h-14 w-14 rounded-2xl border border-blue-200 object-cover shadow-sm"
                          />
                        ) : (
                          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-indigo-100 to-blue-100 border border-blue-200 text-blue-700 font-bold">
                            {authInitials}
                          </div>
                        )}
                        <div className="min-w-0 flex-1">
                          <div className="text-base font-semibold text-slate-900">{authUserName}</div>
                          <div className="mt-1 text-xs text-slate-500">飞书企业登录会话</div>
                          <div className="mt-3">
                            <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${authRoleBadgeClass}`}>
                              {authRoleLabel}
                            </span>
                          </div>
                          {authEmail && (
                            <div className="mt-3 inline-flex max-w-full rounded-xl bg-white/80 px-2.5 py-1 text-xs text-blue-700 ring-1 ring-blue-100">
                              <span className="truncate">{authEmail}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-3 px-5 py-4">
                      <div className="rounded-2xl border border-slate-100 bg-slate-50 px-3 py-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">权限角色</div>
                        <div className="mt-1 text-xs font-semibold text-slate-700">{authRoleLabel}</div>
                      </div>
                      <div className="rounded-2xl border border-slate-100 bg-slate-50 px-3 py-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">飞书 ID</div>
                        <div className="mt-1 break-all font-mono text-xs text-slate-700">{authOpenId || '-'}</div>
                      </div>
                      <div className="rounded-2xl border border-slate-100 bg-slate-50 px-3 py-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">用户 ID</div>
                        <div className="mt-1 break-all font-mono text-xs text-slate-700">{authUserId || '-'}</div>
                      </div>
                      <div className="rounded-2xl border border-slate-100 bg-slate-50 px-3 py-3">
                        <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">租户标识</div>
                        <div className="mt-1 break-all font-mono text-xs text-slate-700">{authTenantKey || '-'}</div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between border-t border-slate-100 px-5 py-4">
                      <button
                        onClick={() => setAccountMenuOpen(false)}
                        className="rounded-xl px-3 py-2 text-xs font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
                      >
                        关闭
                      </button>
                      <button
                        onClick={handleLogout}
                        className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 px-3.5 py-2 text-xs font-medium text-white transition-colors hover:bg-slate-800"
                      >
                        <LogOut size={14} />
                        退出登录
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </header>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-8">
          <AnimatePresence mode="wait">
            {selectedRun ? (
              <div key="detail-view">
                <DetailView
                  runId={selectedRun}
                  onBack={() => { fetchRuns(0); setSelectedRun(null); }}
                  showToast={showToast}
                  taxonomyLabels={taxonomyLabels}
                  currentUserName={authUserName}
                />
              </div>
            ) : (
              <motion.div key="main-content" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }} className="max-w-7xl mx-auto space-y-8">

                {activeTab === 'admin-home' && isAdmin && (
                  <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                    {/* 管理员信息 + 快捷入口 */}
                    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                            <ShieldAlert size={16} className="text-blue-600" />
                            管理员：{authUserName}
                          </div>
                          <div className="text-xs font-mono text-slate-500 mt-1">{authOpenId || authEmail || '-'}</div>
                        </div>
                        <div className="flex gap-3">
                          <button onClick={() => setActiveTab('settings')} className="px-4 py-2 bg-emerald-50 text-emerald-700 rounded-lg text-sm font-medium hover:bg-emerald-100 transition-colors flex items-center gap-2">
                            <Settings size={14} /> 系统设置
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* 权限配置 */}
                    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
                        <h3 className="text-sm font-bold text-slate-800">权限配置</h3>
                        <button
                          onClick={handleSaveAccessSettings}
                          disabled={accessSettingsSaving || accessSettingsLoading}
                          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-xs font-medium text-white hover:bg-slate-800 disabled:bg-slate-300 transition-colors"
                        >
                          {accessSettingsSaving ? <><Loader2 size={14} className="animate-spin" /> 保存中...</> : <><Save size={14} /> 保存</>}
                        </button>
                      </div>
                      {accessSettingsLoading ? (
                        <div className="grid grid-cols-2 gap-4 p-6">
                          {Array.from({ length: 4 }).map((_, idx) => <div key={idx}><Skeleton className="h-32 rounded-lg" /></div>)}
                        </div>
                      ) : accessSettingsError ? (
                        <div className="p-6"><ErrorBox message={accessSettingsError} onRetry={fetchAccessSettings} /></div>
                      ) : (
                        <div className="grid grid-cols-2 gap-4 p-6">
                          {[
                            { key: 'allowedOpenIds', label: '允许登录 Open ID' },
                            { key: 'allowedEmails', label: '允许登录邮箱' },
                            { key: 'adminOpenIds', label: '管理员 Open ID' },
                            { key: 'adminEmails', label: '管理员邮箱' },
                          ].map(field => (
                            <div key={field.key}>
                              <label className="block text-xs font-medium text-slate-600 mb-1">{field.label}</label>
                              <textarea
                                rows={4}
                                value={accessSettingsForm[field.key] || ''}
                                onChange={e => setAccessSettingsForm(prev => ({ ...prev, [field.key]: e.target.value }))}
                                className="w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15"
                                placeholder="每行一个值，留空不限制"
                              />
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* 权限申请审批 */}
                    <AccessRequestsPanel showToast={showToast} onApproved={fetchAccessSettings} />
                  </motion.div>
                )}

                {/* ===== 数据汇总 ===== */}
                {activeTab === 'dashboard' && (
                  <>
                    {/* Stats Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                      {statsLoading ? (
                        Array.from({ length: 3 }).map((_, idx) => (
                          <div key={idx} className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
                            <div className="flex items-center justify-between mb-4">
                              <Skeleton className="w-12 h-12 rounded-xl" />
                              <Skeleton className="w-5 h-5 rounded" />
                            </div>
                            <Skeleton className="h-8 w-24 mb-2" />
                            <Skeleton className="h-4 w-32" />
                          </div>
                        ))
                      ) : statsError ? (
                        <div className="col-span-3"><ErrorBox message={statsError} onRetry={fetchStats} /></div>
                      ) : (
                        statsCards.map((stat, idx) => (
                          <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: idx * 0.1 }}
                            key={stat.label}
                            className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow"
                          >
                            <div className="flex items-center justify-between mb-4">
                              <div className={`w-12 h-12 rounded-xl ${stat.bg} flex items-center justify-center`}>
                                <stat.icon size={24} className={stat.color} />
                              </div>
                              <Activity size={20} className="text-slate-300" />
                            </div>
                            <h3 className="text-3xl font-bold text-slate-900 mb-1">{stat.value}</h3>
                            <p className="text-sm font-medium text-slate-500">{stat.label}</p>
                          </motion.div>
                        ))
                      )}
                    </div>

                    {/* 行业类别分布 */}
                    {stats && Object.keys(stats.labelDistribution || {}).length > 0 && (
                      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden mt-6">
                        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
                          <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2"><Activity size={14} className="text-blue-500" /> 模型打标行业分布</h3>
                        </div>
                        <div className="p-6 space-y-3">
                          {(Object.entries(stats.labelDistribution) as [string, number][])
                            .sort(([, a], [, b]) => b - a)
                            .map(([label, count]) => {
                              const values = Object.values(stats.labelDistribution) as number[];
                              const maxCount = Math.max(...values);
                              const pct = maxCount > 0 ? Math.round((count / maxCount) * 100) : 0;
                              const totalPct = stats.totalProcessed > 0 ? ((count / stats.totalProcessed) * 100).toFixed(1) : '0';
                              const iconInfo = TAXONOMY_NAME_ICON_MAP[resolveLabelName(label)] || { icon: HelpCircle, color: 'text-slate-400', bg: 'bg-slate-50' };
                              const IconComp = iconInfo.icon;
                              return (
                                <div key={label} className="flex items-center gap-3">
                                  <div className={`w-7 h-7 rounded-lg ${iconInfo.bg} flex items-center justify-center shrink-0`}>
                                    <IconComp size={14} className={iconInfo.color} />
                                  </div>
                                  <span className="text-sm text-slate-700 w-24 truncate shrink-0">{resolveLabelName(label)}</span>
                                  <div className="flex-1 h-6 bg-slate-100 rounded-full overflow-hidden">
                                    <div
                                      className="h-full rounded-full bg-gradient-to-r from-blue-500 to-indigo-500 flex items-center justify-end pr-2 transition-all duration-500"
                                      style={{ width: `${Math.max(pct, 5)}%` }}
                                    >
                                      {pct > 20 && <span className="text-[10px] text-white font-bold">{count}</span>}
                                    </div>
                                  </div>
                                  <span className="text-xs font-mono text-slate-500 w-12 text-right shrink-0">{totalPct}%</span>
                                  <span className="text-xs text-slate-400 w-10 text-right shrink-0">{count}家</span>
                                </div>
                              );
                            })}
                        </div>
                      </div>
                    )}

                    {/* 标注归档 */}
                    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden mt-6">
                      <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
                        <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2"><Tag size={14} className="text-sky-500" /> 标注归档</h3>
                        <span className="text-xs text-slate-400">{annotationArchive.length} 条已标注</span>
                      </div>
                      {archiveLoading ? (
                        <div className="p-6 space-y-3">
                          {Array.from({ length: 3 }).map((_, i) => <div key={i}><Skeleton className="h-10 w-full rounded-lg" /></div>)}
                        </div>
                      ) : annotationArchive.length > 0 ? (
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b border-slate-100 bg-slate-50/30">
                                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500">企业名称</th>
                                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500">模型标签</th>
                                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500">标注标签</th>
                                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500">标注次数</th>
                                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500">标注人</th>
                                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500">最新备注</th>
                                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500">最新时间</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {annotationArchive.map((item, idx) => {
                                const name = (item.enterpriseName || item.enterprise_name || '') as string;
                                const mLabel = resolveLabelName((item.modelLabel || item.model_label || '') as string);
                                const aLabel = resolveLabelName((item.annotatedLabel || item.annotated_label || '') as string);
                                const count = (item.annotationCount || item.annotation_count || 0) as number;
                                const notes = (item.latestNotes || item.latest_notes || '') as string;
                                const reviewer = (item.latestReviewer || item.latest_reviewer || '') as string;
                                const time = (item.latestTime || item.latest_time || '') as string;
                                const runId = (item.runId || item.run_id || '') as string;
                                const isSame = mLabel === aLabel;
                                return (
                                  <tr key={idx} className="hover:bg-slate-50/80 transition-colors cursor-pointer" onClick={() => { setSelectedRun(runId); setActiveTab('review-list'); }}>
                                    <td className="px-6 py-3 font-medium text-slate-900">{name}</td>
                                    <td className="px-6 py-3"><span className="px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-600">{mLabel || '-'}</span></td>
                                    <td className="px-6 py-3"><span className={`px-2 py-0.5 rounded text-xs font-medium ${isSame ? 'bg-emerald-50 text-emerald-700' : 'bg-sky-50 text-sky-700'}`}>{aLabel}</span></td>
                                    <td className="px-6 py-3 text-slate-500">{count}/3</td>
                                    <td className="px-6 py-3 text-sm text-slate-700">{reviewer || '-'}</td>
                                    <td className="px-6 py-3 text-slate-500 max-w-48 truncate">{notes || '-'}</td>
                                    <td className="px-6 py-3 text-xs text-slate-400 font-mono">{time}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <div className="p-8 text-center text-sm text-slate-400">暂无标注记录</div>
                      )}
                    </div>

                    {/* 行业标签一览 */}
                    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden mt-6">
                      <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2"><BookOpen size={14} className="text-blue-500" /> 行业标签体系</h3>
                          {taxonomy && (
                            <span className="px-2 py-0.5 bg-blue-50 text-blue-700 text-xs font-semibold rounded-md border border-blue-200">
                              {taxonomy.version}
                            </span>
                          )}
                        </div>
                      </div>
                      {taxonomyLoading ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-6">
                          {Array.from({ length: 6 }).map((_, idx) => (
                            <div key={idx} className="p-4 rounded-xl border border-slate-100">
                              <div className="flex items-center gap-3 mb-2">
                                <Skeleton className="w-10 h-10 rounded-lg" />
                                <div className="flex-1"><Skeleton className="h-4 w-20" /></div>
                              </div>
                              <Skeleton className="h-3 w-full" />
                            </div>
                          ))}
                        </div>
                      ) : taxonomyError ? (
                        <ErrorBox message={taxonomyError} onRetry={fetchTaxonomy} />
                      ) : taxonomy ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-6">
                          {taxonomy.labels.map((label) => {
                            const iconInfo = getTaxonomyIcon(label);
                            const IconComp = iconInfo.icon;
                            return (
                              <div key={label.id} className="p-4 rounded-xl border border-slate-100 hover:border-slate-200 hover:shadow-sm transition-all group">
                                <div className="flex items-center gap-3 mb-2">
                                  <div className={`w-10 h-10 rounded-lg ${iconInfo.bg} flex items-center justify-center shrink-0 group-hover:scale-110 transition-transform`}>
                                    <IconComp size={20} className={iconInfo.color} />
                                  </div>
                                  <div>
                                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{label.id}</span>
                                    <h4 className="text-sm font-bold text-slate-900">{label.displayName}</h4>
                                  </div>
                                </div>
                                <p className="text-xs text-slate-500 leading-relaxed">{label.shortDescription}</p>
                              </div>
                            );
                          })}
                        </div>
                      ) : null}
                    </div>

                  </>
                )}

                {/* ===== 分类审核台 ===== */}
                {activeTab === 'review-list' && (
                  <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
                    <div className="p-6 border-b border-slate-200">
                      <h2 className="text-lg font-semibold text-slate-900">全部分类记录</h2>
                      <p className="text-sm text-slate-500 mt-1">点击任意行查看详细执行轨迹与标注</p>
                    </div>

                    {/* Filter Bar */}
                    <div className="px-6 pt-4 flex items-center gap-2 border-b border-slate-100 pb-4">
                      {([
                        { key: 'all' as const, label: '全部' },
                        { key: 'annotated' as const, label: '已标注' },
                        { key: 'unannotated' as const, label: '待标注' },
                      ]).map(tab => (
                        <button
                          key={tab.key}
                          onClick={() => setRunsFilter(tab.key)}
                          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                            runsFilter === tab.key
                              ? 'bg-blue-600 text-white shadow-sm'
                              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                          }`}
                        >
                          {tab.label}
                        </button>
                      ))}
                      <span className="ml-auto text-xs text-slate-400">共 {filteredRuns.length} 条 / 总 {runsTotal} 条</span>
                    </div>

                    {/* Label Filter Chips */}
                    <div className="px-6 py-3 flex items-center gap-2 flex-wrap border-b border-slate-100">
                      <span className="text-xs text-slate-400 shrink-0">行业:</span>
                      <button
                        onClick={() => setLabelFilter(null)}
                        className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                          !labelFilter ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        }`}
                      >全部</button>
                      {Object.keys(TAXONOMY_NAME_ICON_MAP).map(name => {
                        const info = TAXONOMY_NAME_ICON_MAP[name];
                        const IconComp = info.icon;
                        const isActive = labelFilter === name;
                        return (
                          <button
                            key={name}
                            onClick={() => setLabelFilter(isActive ? null : name)}
                            className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                              isActive ? `${info.bg} ${info.color} ring-1 ring-current` : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                            }`}
                          >
                            <IconComp size={12} />
                            {name}
                          </button>
                        );
                      })}
                    </div>

                    {runsLoading ? (
                      <div className="p-6 space-y-4">
                        {Array.from({ length: 5 }).map((_, i) => (
                          <div key={i} className="flex items-center gap-4">
                            <Skeleton className="h-10 flex-1 rounded-lg" />
                            <Skeleton className="h-6 w-20 rounded" />
                            <Skeleton className="h-4 w-16 rounded" />
                            <Skeleton className="h-6 w-16 rounded-full" />
                          </div>
                        ))}
                      </div>
                    ) : runsError ? (
                      <ErrorBox message={runsError} onRetry={() => fetchRuns(0)} />
                    ) : (
                      <>
                        <div className="overflow-x-auto">
                          <table className="w-full text-left border-collapse">
                            <thead>
                              <tr className="bg-slate-50/50 border-b border-slate-200">
                                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">企业名称</th>
                                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">信用代码</th>
                                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">行业标签</th>
                                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">标注状态</th>
                                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">置信度</th>
                                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">错误类型</th>
                                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">创建日期</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {filteredRuns.map(item => {
                                const hasAnnotation = (item.annotations || []).length > 0;
                                const latestAnn = hasAnnotation ? (item.annotations || [])[item.annotations.length - 1] : null;
                                const confInfo = confidenceLevelMap[item.confidenceLevel || ''] || { num: 0, label: item.confidenceLevel || '未知', color: 'text-slate-500' };
                                return (
                                  <tr key={item.runId} className="hover:bg-slate-50/80 transition-colors group cursor-pointer" onClick={() => setSelectedRun(item.runId)}>
                                    <td className="px-6 py-4">
                                      <span className="font-medium text-slate-900 group-hover:text-blue-600 transition-colors">{item.enterpriseName}</span>
                                    </td>
                                    <td className="px-6 py-4">
                                      <span className="text-xs text-slate-500 font-mono">{item.entityKey}</span>
                                    </td>
                                    <td className="px-6 py-4">
                                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-800 border border-slate-200">
                                        {resolveLabelName(item.finalLabel || '') || '未知'}
                                      </span>
                                    </td>
                                    <td className="px-6 py-4">
                                      {hasAnnotation ? (
                                        <span
                                          title={latestAnn?.reviewerNotes || '人工标注已生效'}
                                          className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-sky-50 text-sky-700 border border-sky-200"
                                        >
                                          {resolveLabelName((item.annotatedLabel || (latestAnn as any)?.annotatedLabel || (latestAnn as any)?.annotated_label || '') as string) || '人工标注'}
                                        </span>
                                      ) : (
                                        <span className="text-xs text-slate-400">-</span>
                                      )}
                                    </td>
                                    <td className="px-6 py-4">
                                      <div className="flex items-center gap-2">
                                        <div className="w-16 h-2 bg-slate-100 rounded-full overflow-hidden">
                                          <div
                                            className={`h-full rounded-full ${
                                              confInfo.num > 0.8
                                                ? 'bg-emerald-500'
                                                : confInfo.num > 0.4
                                                  ? 'bg-amber-500'
                                                  : 'bg-red-500'
                                            }`}
                                            style={{ width: `${confInfo.num * 100}%` }}
                                          />
                                        </div>
                                        <span className={`text-xs font-medium ${confInfo.color}`}>{confInfo.label}</span>
                                      </div>
                                    </td>
                                    <td className="px-6 py-4">
                                      {item.errorType ? <span className="text-xs text-red-500 font-medium">{{
                                        parse_error: 'JSON 解析失败',
                                        schema_validation_error: '结构校验失败',
                                        unknown_static_profile_error: '静态画像异常',
                                        unknown_dynamic_profile_error: '动态画像异常',
                                        unknown_final_decision_error: '最终裁决异常',
                                      }[item.errorType] ?? item.errorType}</span> : <span className="text-xs text-slate-400">-</span>}
                                    </td>
                                    <td className="px-6 py-4">
                                      <span className="text-xs text-slate-500 font-mono">{formatDateTime(item.timestamp)}</span>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                        {/* Load More */}
                        {runsOffset < runsTotal && (
                          <div className="p-4 border-t border-slate-100 flex justify-center">
                            <button
                              onClick={handleLoadMore}
                              disabled={runsLoadingMore}
                              className="px-6 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50"
                            >
                              {runsLoadingMore ? <><Loader2 size={14} className="animate-spin" /> 加载中...</> : <>加载更多 (剩余 {runsTotal - runsOffset} 条)</>}
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </motion.div>
                )}

                {/* ===== 发起分类 ===== */}
                {activeTab === 'classify' && (
                  <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                    {/* Tab 切换 */}
                    <div className="flex gap-2">
                      <button
                        onClick={() => { setClassifyMode('single'); setClassifyTaskId(null); setClassifyStages([]); setClassifyTaskStatus(''); setClassifyResultRunId(null); setClassifyError(null); }}
                        className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-colors ${classifyMode === 'single' ? 'bg-blue-600 text-white shadow-sm' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                      >
                        单条查询
                      </button>
                      <button
                        onClick={() => { setClassifyMode('batch'); setClassifyTaskId(null); setClassifyStages([]); setClassifyTaskStatus(''); setClassifyResultRunId(null); setClassifyError(null); }}
                        className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-colors ${classifyMode === 'batch' ? 'bg-blue-600 text-white shadow-sm' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                      >
                        批量导入
                      </button>
                    </div>

                    {classifyMode === 'single' ? (
                      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
                        <div className="grid grid-cols-3 gap-4">
                          <div className="col-span-2">
                            <label className="block text-sm font-medium text-slate-800 mb-2">企业名称或统一社会信用代码</label>
                            <input
                              value={classifyQuery}
                              onChange={e => setClassifyQuery(e.target.value)}
                              placeholder="例如：邯郸峤博建筑工程有限公司 或 91130424MA0DBFEM9B"
                              className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-slate-800 mb-2">业务日期 (pt)</label>
                            <input
                              value={classifyPt}
                              onChange={e => setClassifyPt(e.target.value)}
                              placeholder="yyyymmdd"
                              className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
                            />
                          </div>
                        </div>
                        <button
                          onClick={async () => {
                            if (!classifyQuery.trim()) return;
                            setClassifySubmitting(true);
                            setClassifyTaskId(null);
                            setClassifyStages([]);
                            setClassifyTaskStatus('');
                            setClassifyResultRunId(null);
                            setClassifyError(null);
                            try {
                              const res = await api.classifySingle(classifyQuery.trim(), classifyPt);
                              showToast(res.message);
                              setClassifyTaskId(res.taskId);
                              setClassifyQuery('');
                            } catch (e: any) {
                              showToast(e.message || '提交失败', true);
                            } finally {
                              setClassifySubmitting(false);
                            }
                          }}
                          disabled={classifySubmitting || !classifyQuery.trim()}
                          className="px-6 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 disabled:bg-slate-300 transition-colors flex items-center gap-2"
                        >
                          {classifySubmitting ? <><Loader2 size={14} className="animate-spin" /> 提交中...</> : <><Zap size={14} /> 开始分类</>}
                        </button>
                      </div>
                    ) : (
                      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
                        {/* 批量方式切换 */}
                        <div className="flex gap-2 mb-2">
                          <button
                            onClick={() => setClassifyBatchMode('job')}
                            className={`px-4 py-2 rounded-lg text-xs font-medium transition-colors ${classifyBatchMode === 'job' ? 'bg-indigo-600 text-white shadow-sm' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                          >按工种搜索</button>
                          <button
                            onClick={() => setClassifyBatchMode('csv')}
                            className={`px-4 py-2 rounded-lg text-xs font-medium transition-colors ${classifyBatchMode === 'csv' ? 'bg-indigo-600 text-white shadow-sm' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                          >上传 CSV</button>
                        </div>

                        {classifyBatchMode === 'job' ? (
                          <div className="space-y-4">
                            <div className="grid grid-cols-3 gap-4">
                              <div className="col-span-2 relative">
                                <label className="block text-sm font-medium text-slate-800 mb-2">工种名称</label>
                                <input
                                  value={classifyJobName}
                                  onChange={e => { setClassifyJobName(e.target.value); setJobNameDropdownOpen(true); }}
                                  onFocus={() => setJobNameDropdownOpen(true)}
                                  onBlur={() => setTimeout(() => setJobNameDropdownOpen(false), 200)}
                                  placeholder="输入工种名称模糊搜索，如：保安、保洁、厨师..."
                                  className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
                                />
                                {classifyJobName && (
                                  <button onClick={() => { setClassifyJobName(''); setJobNameDropdownOpen(false); }} className="absolute right-3 top-[42px] text-slate-400 hover:text-slate-600">
                                    <X size={14} />
                                  </button>
                                )}
                                {jobNameDropdownOpen && classifyJobName.length > 0 && (() => {
                                  const q = classifyJobName.toLowerCase();
                                  const matches = JOB_NAMES.filter(n => n.toLowerCase().includes(q)).slice(0, 20);
                                  if (matches.length === 0) return null;
                                  return (
                                    <div className="absolute z-50 mt-1 w-full bg-white border border-slate-200 rounded-xl shadow-lg max-h-60 overflow-y-auto">
                                      {matches.map(name => (
                                        <div
                                          key={name}
                                          onClick={() => { setClassifyJobName(name); setJobNameDropdownOpen(false); }}
                                          className="px-4 py-2 text-sm text-slate-700 hover:bg-blue-50 hover:text-blue-700 cursor-pointer"
                                        >{name}</div>
                                      ))}
                                    </div>
                                  );
                                })()}
                              </div>
                              <div>
                                <label className="block text-sm font-medium text-slate-800 mb-2">业务日期 (pt)</label>
                                <input
                                  value={classifyPt}
                                  onChange={e => setClassifyPt(e.target.value)}
                                  placeholder="yyyymmdd"
                                  className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
                                />
                              </div>
                            </div>
                            <p className="text-xs text-slate-400">按工种名称从 ODPS 模糊匹配拉取企业，单次最多 {batchMaxRows} 条</p>
                            <button
                              onClick={async () => {
                                if (!classifyJobName.trim()) return;
                                setClassifySubmitting(true);
                                setClassifyTaskId(null);
                                setClassifyStages([]);
                                setClassifyTaskStatus('');
                                setClassifyResultRunId(null);
                                setClassifyError(null);
                                try {
                                  const res = await api.classifyByJobName(classifyJobName.trim(), classifyPt);
                                  showToast(res.message);
                                  setClassifyTaskId(res.taskId);
                                } catch (e: any) {
                                  showToast(e.message || '提交失败', true);
                                } finally {
                                  setClassifySubmitting(false);
                                }
                              }}
                              disabled={classifySubmitting || !classifyJobName.trim()}
                              className="px-6 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 disabled:bg-slate-300 transition-colors flex items-center gap-2"
                            >
                              {classifySubmitting ? <><Loader2 size={14} className="animate-spin" /> 搜索中...</> : <><Search size={14} /> 按工种批量分类</>}
                            </button>
                          </div>
                        ) : (
                          <div className="space-y-4">
                            <div className="flex gap-4 items-end">
                              <div className="flex-1">
                                <label className="block text-sm font-medium text-slate-800 mb-2">上传 CSV 文件</label>
                                <p className="text-xs text-slate-500 mb-3">CSV 需包含 social_credit_code 列，单次最多 {batchMaxRows} 条</p>
                              </div>
                              <div className="w-48">
                                <label className="block text-sm font-medium text-slate-800 mb-2">业务日期 (pt)</label>
                                <input
                                  value={classifyPt}
                                  onChange={e => setClassifyPt(e.target.value)}
                                  placeholder="yyyymmdd"
                                  className="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
                                />
                              </div>
                            </div>
                            <div
                              className="border-2 border-dashed border-slate-300 rounded-xl p-8 text-center hover:border-blue-400 hover:bg-blue-50/30 transition-colors cursor-pointer"
                              onClick={() => document.getElementById('csv-upload')?.click()}
                              onDragOver={e => { e.preventDefault(); e.stopPropagation(); }}
                              onDrop={e => {
                                e.preventDefault(); e.stopPropagation();
                                const f = e.dataTransfer.files[0];
                                if (f && f.name.endsWith('.csv')) setClassifyCsvFile(f);
                              }}
                            >
                              <Database size={32} className="mx-auto text-slate-400 mb-3" />
                              {classifyCsvFile ? (
                                <div>
                                  <div className="text-sm font-medium text-slate-900">{classifyCsvFile.name}</div>
                                  <div className="text-xs text-slate-500 mt-1">{(classifyCsvFile.size / 1024).toFixed(1)} KB</div>
                                </div>
                              ) : (
                                <div>
                                  <div className="text-sm text-slate-600">点击选择或拖拽 CSV 文件到此处</div>
                                  <div className="text-xs text-slate-400 mt-1">支持 .csv 格式</div>
                                </div>
                              )}
                            </div>
                            <input id="csv-upload" type="file" accept=".csv" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) setClassifyCsvFile(f); }} />
                            <button
                              onClick={async () => {
                                if (!classifyCsvFile) return;
                                setClassifySubmitting(true);
                                setClassifyTaskId(null);
                                setClassifyStages([]);
                                setClassifyTaskStatus('');
                                setClassifyResultRunId(null);
                                setClassifyError(null);
                                try {
                                  const res = await api.classifyUploadCsv(classifyCsvFile, classifyPt);
                                  showToast(res.message);
                                  setClassifyTaskId(res.taskId);
                                  setClassifyCsvFile(null);
                                } catch (e: any) {
                                  showToast(e.message || '上传失败', true);
                                } finally {
                                  setClassifySubmitting(false);
                                }
                              }}
                              disabled={classifySubmitting || !classifyCsvFile}
                              className="px-6 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 disabled:bg-slate-300 transition-colors flex items-center gap-2"
                            >
                              {classifySubmitting ? <><Loader2 size={14} className="animate-spin" /> 上传中...</> : <><Send size={14} /> 开始批量分类</>}
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {/* 动态流程图 */}
                    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                      <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
                        <h3 className="text-sm font-bold text-slate-800">分类流程</h3>
                      </div>
                      <div className="p-6">
                        {(() => {
                          const defaultStages = [
                            { name: 'ODPS 数据查询', status: 'pending', elapsedMs: null as number | null, message: '' },
                            { name: '静态画像', status: 'pending', elapsedMs: null as number | null, message: '' },
                            { name: '动态画像', status: 'pending', elapsedMs: null as number | null, message: '' },
                            { name: '最终裁决', status: 'pending', elapsedMs: null as number | null, message: '' },
                          ];
                          const stages = classifyStages.length > 0 ? classifyStages : defaultStages;
                          const stageIconMap: Record<string, any> = { 'ODPS 数据查询': Database, '静态画像': FileText, '动态画像': Activity, '最终裁决': BrainCircuit, '批量分类': Activity };
                          const stageColors: Record<string, string> = { pending: 'bg-slate-300', running: 'bg-blue-500 animate-pulse', done: 'bg-emerald-500', error: 'bg-red-500' };
                          return (
                            <div className="relative">
                              <div className="absolute left-5 top-6 bottom-6 w-0.5 bg-slate-200" />
                              <div className="space-y-4">
                                {stages.map((stage, idx) => {
                                  const Icon = stageIconMap[stage.name] || Database;
                                  return (
                                    <div key={idx} className="flex items-center gap-4 relative z-10">
                                      <div className={`w-10 h-10 rounded-full ${stageColors[stage.status] || 'bg-slate-300'} text-white flex items-center justify-center shadow-md ring-4 ring-white shrink-0 transition-all`}>
                                        {stage.status === 'running' ? <Loader2 size={18} className="animate-spin" /> : <Icon size={18} />}
                                      </div>
                                      <div className="flex-1">
                                        <div className="flex items-center gap-2">
                                          <span className={`text-sm font-bold ${stage.status === 'pending' ? 'text-slate-400' : 'text-slate-700'}`}>{stage.name}</span>
                                          {stage.elapsedMs != null && (
                                            <span className="text-[10px] font-mono text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">{Math.round(stage.elapsedMs)}ms</span>
                                          )}
                                          {stage.status === 'done' && <CheckCircle2 size={14} className="text-emerald-500" />}
                                          {stage.status === 'error' && <XCircle size={14} className="text-red-500" />}
                                        </div>
                                        {stage.message && <div className="text-xs text-slate-500">{stage.message}</div>}
                                        {stage.status === 'pending' && !classifyTaskId && <div className="text-xs text-slate-300">等待提交</div>}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          );
                        })()}
                        {classifyTaskStatus === 'done' && (
                          <div className="mt-4 pt-4 border-t border-slate-100 flex items-center justify-between">
                            <span className="text-sm text-emerald-600 font-medium">分类完成</span>
                            {classifyResultRunId ? (
                              <button
                                onClick={() => { setSelectedRun(classifyResultRunId); setActiveTab('review-list'); }}
                                className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
                              >
                                查看结果 <ChevronRight size={14} />
                              </button>
                            ) : (
                              <button
                                onClick={() => { setActiveTab('review-list'); }}
                                className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
                              >
                                查看列表 <ChevronRight size={14} />
                              </button>
                            )}
                          </div>
                        )}
                        {classifyTaskStatus === 'error' && classifyError && (
                          <div className="mt-4 pt-4 border-t border-slate-100">
                            <div className="text-sm text-red-600">{classifyError}</div>
                          </div>
                        )}
                      </div>
                    </div>
                  </motion.div>
                )}

                {/* ===== 系统设置 ===== */}
                {activeTab === 'settings' && (
                  <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                      <div className="p-6 border-b border-slate-200 flex items-center justify-between">
                        <div>
                          <h2 className="text-lg font-semibold text-slate-900">系统运行时配置</h2>
                          <p className="text-sm text-slate-500 mt-1">修改分类流水线的运行参数。保存后立即生效。</p>
                        </div>
                        <button
                          onClick={handleSaveSettings}
                          disabled={settingsSaving || settingsLoading}
                          className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:bg-slate-300 transition-colors flex items-center gap-2"
                        >
                          {settingsSaving ? <><Loader2 size={14} className="animate-spin" /> 保存中...</> : <><Save size={14} /> 保存设置</>}
                        </button>
                      </div>

                      {settingsLoading ? (
                        <div className="p-6 space-y-6">
                          {Array.from({ length: 6 }).map((_, i) => (
                            <div key={i} className="space-y-2">
                              <Skeleton className="h-4 w-32" />
                              <Skeleton className="h-10 w-full rounded-lg" />
                              <Skeleton className="h-3 w-48" />
                            </div>
                          ))}
                        </div>
                      ) : settingsError ? (
                        <ErrorBox message={settingsError} onRetry={fetchSettings} />
                      ) : (
                        <div className="p-6 space-y-6">
                          {settingsFields.map(field => (
                            <div key={field.key}>
                              <div className="flex items-center justify-between mb-1">
                                <label className="text-sm font-medium text-slate-800">{field.label}</label>
                                {settings && (
                                  <span className="text-xs text-slate-400">
                                    当前值: {String((settings as any)[field.key])}
                                  </span>
                                )}
                              </div>
                              <input
                                type={field.type}
                                value={settingsForm[field.key] || ''}
                                onChange={e => {
                                  setSettingsForm(prev => ({ ...prev, [field.key]: e.target.value }));
                                  setSettingsValidation(prev => { const n = { ...prev }; delete n[field.key]; return n; });
                                }}
                                className={`w-full px-3 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none ${settingsValidation[field.key] ? 'border-red-300 bg-red-50/50' : 'border-slate-200'}`}
                              />
                              {settingsValidation[field.key] && (
                                <p className="text-xs text-red-500 mt-1">{settingsValidation[field.key]}</p>
                              )}
                              <p className="text-xs text-slate-400 mt-1">{field.desc}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Prompt 模板 */}
                    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                      <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
                        <h2 className="text-lg font-semibold text-slate-900">Prompt 模板</h2>
                        <p className="text-sm text-slate-500 mt-1">各阶段 LLM 调用的 System Prompt 和 User Template</p>
                      </div>
                      {promptsLoading ? (
                        <div className="p-6 space-y-4">
                          <Skeleton className="h-32 w-full rounded-lg" />
                          <Skeleton className="h-32 w-full rounded-lg" />
                        </div>
                      ) : (
                        <div className="divide-y divide-slate-100">
                          {[
                            { key: 'staticProfile', label: '静态画像 (Static Profile)' },
                            { key: 'dynamicProfile', label: '动态画像 (Dynamic Profile)' },
                            { key: 'finalDecision', label: '最终裁决 (Final Decision)' },
                          ].map(item => {
                            const p = prompts?.[item.key];
                            return (
                              <details key={item.key} className="group">
                                <summary className="px-6 py-4 cursor-pointer hover:bg-slate-50/50 flex items-center justify-between">
                                  <div className="flex items-center gap-3">
                                    <span className="text-sm font-bold text-slate-800">{item.label}</span>
                                    {p && <span className="text-[10px] font-mono text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">{p.version}</span>}
                                  </div>
                                  <ChevronRight size={16} className="text-slate-400 group-open:rotate-90 transition-transform" />
                                </summary>
                                {p ? (
                                  <div className="px-6 pb-6 space-y-4">
                                    <div>
                                      <div className="text-xs font-medium text-slate-500 mb-2">System Prompt</div>
                                      <pre className="text-xs text-slate-700 bg-slate-50 p-4 rounded-lg border border-slate-100 overflow-auto max-h-48 whitespace-pre-wrap font-mono">{p.systemPrompt}</pre>
                                    </div>
                                    <div>
                                      <div className="text-xs font-medium text-slate-500 mb-2">User Template</div>
                                      <pre className="text-xs text-slate-700 bg-slate-50 p-4 rounded-lg border border-slate-100 overflow-auto max-h-64 whitespace-pre-wrap font-mono">{p.userTemplate}</pre>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="px-6 pb-4 text-xs text-slate-400">暂无 prompt 数据</div>
                                )}
                              </details>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}

              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
