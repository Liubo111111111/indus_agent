import React, { useState, useEffect, useCallback, useRef } from 'react';
import DetailView from './DetailView';
import {
  Loader2,
  Play,
  CheckCircle2,
  XCircle,
  BarChart3,
  History,
  Trash2,
  ChevronDown,
  AlertCircle,
} from 'lucide-react';

// ─── 类型定义 ───

interface ComparisonStatusResponse {
  session_id: string;
  status: string;
  dataset_size: number;
  completed_count: number;
  error_count: number;
  diff_count: number;
  annotation_count: number;
  current_entity: string | null;
  consistency_rate: number | null;
}

interface DiffAnalysis {
  session_id: string;
  dataset_size: number;
  diff_count: number;
  consistency_rate: number;
  change_matrix: Record<string, Record<string, number>>;
  change_type_ranking: Array<{ old_label: string; new_label: string; count: number }>;
  net_changes: Record<string, number>;
}

interface DiffRecord {
  entity_key: string;
  enterprise_name: string;
  old_label: string;
  new_label: string;
  confidence_level: string | null;
  decision_reason: string | null;
  human_label: string | null;
}

interface RecordsResponse {
  records: DiffRecord[];
  total: number;
  page: number;
  page_size: number;
  annotation_progress: { annotated: number; total_diff: number };
}

interface LabelAccuracy {
  label: string;
  old_precision: number;
  old_recall: number;
  old_f1: number;
  new_precision: number;
  new_recall: number;
  new_f1: number;
  recommendation: string;
}

interface ComparisonReport {
  session_id: string;
  old_accuracy: number;
  new_accuracy: number;
  improvement: number;
  coverage: number;
  coverage_warning: string | null;
  label_metrics: LabelAccuracy[];
  old_confusion_matrix: Record<string, Record<string, number>>;
  new_confusion_matrix: Record<string, Record<string, number>>;
  recommendations: Array<{ label: string; recommendation: string; reason: string }>;
}

interface SessionSummary {
  session_id: string;
  bizdate: string;
  prompt_version_static: string;
  prompt_version_dynamic: string;
  prompt_version_final: string;
  dataset_size: number;
  completed_count: number;
  diff_count: number;
  annotation_count: number;
  consistency_rate: number | null;
  status: string;
  created_at: string;
}

interface PromptNodeConfig {
  displayName: string;
  default: string;
  versions: string[];
}

// ─── 工具函数 ───

const API_BASE = '/api/comparison';

function fmtPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

function cmColor(val: number, max: number): string {
  if (max === 0 || val === 0) return 'bg-white';
  const ratio = val / max;
  if (ratio < 0.25) return 'bg-blue-50';
  if (ratio < 0.5) return 'bg-blue-100';
  if (ratio < 0.75) return 'bg-blue-300 text-white';
  return 'bg-blue-500 text-white';
}


// ─── 子面板: ComparisonLaunchPanel ───

function ComparisonLaunchPanel({
  onLaunch,
  starting,
}: {
  onLaunch: (config: {
    bizdate: string;
    max_rows: number | null;
    lookback_days: number;
    prompt_version_static: string;
    prompt_version_dynamic: string;
    prompt_version_final: string;
  }) => void;
  starting: boolean;
}) {
  const [bizdate, setBizdate] = useState('20260426');
  const [maxRows, setMaxRows] = useState<string>('');
  const [lookbackDays, setLookbackDays] = useState<string>('1');
  const [promptVersionStatic, setPromptVersionStatic] = useState('v1');
  const [promptVersionDynamic, setPromptVersionDynamic] = useState('v1');
  const [promptVersionFinal, setPromptVersionFinal] = useState('v2');
  const [nodes, setNodes] = useState<Record<string, PromptNodeConfig>>({});

  useEffect(() => {
    fetch('/api/backtest/prompt-versions')
      .then(r => r.json())
      .then(data => {
        if (data.nodes) {
          setNodes(data.nodes);
          const sp = data.nodes.staticProfile || data.nodes.static_profile;
          const dp = data.nodes.dynamicProfile || data.nodes.dynamic_profile;
          const fd = data.nodes.finalDecision || data.nodes.final_decision;
          if (sp?.default) setPromptVersionStatic(sp.default);
          if (dp?.default) setPromptVersionDynamic(dp.default);
          if (fd?.default) setPromptVersionFinal(fd.default);
        }
      })
      .catch(() => {});
  }, []);

  const handleLaunch = () => {
    onLaunch({
      bizdate,
      max_rows: maxRows ? parseInt(maxRows, 10) : null,
      lookback_days: lookbackDays ? parseInt(lookbackDays, 10) : 1,
      prompt_version_static: promptVersionStatic,
      prompt_version_dynamic: promptVersionDynamic,
      prompt_version_final: promptVersionFinal,
    });
  };

  const fields: { key: string; node: string; value: string; setter: (v: string) => void }[] = [
    { key: 'static', node: 'staticProfile', value: promptVersionStatic, setter: setPromptVersionStatic },
    { key: 'dynamic', node: 'dynamicProfile', value: promptVersionDynamic, setter: setPromptVersionDynamic },
    { key: 'final', node: 'finalDecision', value: promptVersionFinal, setter: setPromptVersionFinal },
  ];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5">
      <h3 className="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-2">
        <Play size={16} className="text-blue-500" /> 对比评估配置
      </h3>

      <div className="space-y-4">
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">业务日期 (bizdate)</label>
            <input
              value={bizdate}
              onChange={e => setBizdate(e.target.value)}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
              placeholder="yyyymmdd"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">回溯天数</label>
            <input
              value={lookbackDays}
              onChange={e => setLookbackDays(e.target.value)}
              type="number"
              min={1}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
              placeholder="1"
            />
            <span className="text-[10px] text-slate-400 mt-0.5 block">publish_start = bizdate - N天</span>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">最大拉取条数 (可选)</label>
            <input
              value={maxRows}
              onChange={e => setMaxRows(e.target.value)}
              type="number"
              min={1}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
              placeholder="不限"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-600 mb-2 flex items-center gap-1">
            <ChevronDown size={12} /> Prompt 版本配置
          </label>
          <div className="grid grid-cols-3 gap-3">
            {fields.map(f => {
              const nodeConfig = nodes[f.node] || nodes[f.node.replace(/([A-Z])/g, '_$1').toLowerCase()];
              const versions = nodeConfig?.versions || [];
              const displayName = nodeConfig?.display_name || nodeConfig?.displayName || f.key;
              return (
                <div key={f.key}>
                  <label className="block text-[10px] text-slate-500 mb-1">{displayName}</label>
                  <select
                    value={f.value}
                    onChange={e => f.setter(e.target.value)}
                    className="w-full px-2 py-1.5 border border-slate-200 rounded-lg text-xs bg-white focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
                  >
                    {versions.length > 0 ? versions.map(v => (
                      <option key={v} value={v}>{v}</option>
                    )) : (
                      <option value={f.value}>{f.value}</option>
                    )}
                  </select>
                </div>
              );
            })}
          </div>
        </div>

        <button
          onClick={handleLaunch}
          disabled={starting || !bizdate}
          className="w-full py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:bg-slate-300 transition-colors flex items-center justify-center gap-2"
        >
          {starting ? <><Loader2 size={14} className="animate-spin" /> 启动中...</> : <><Play size={14} /> 启动对比</>}
        </button>
      </div>
    </div>
  );
}


// ─── 子面板: ComparisonProgressPanel ───

function ComparisonProgressPanel({ status }: { status: ComparisonStatusResponse | null }) {
  if (!status) return null;

  const pct = status.dataset_size > 0 ? (status.completed_count / status.dataset_size) * 100 : 0;
  const isRunning = status.status === 'running';
  const isDone = status.status === 'diff_ready' || status.status === 'annotating' || status.status === 'evaluated';
  const isError = status.status === 'error';

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5">
      <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
        {isRunning && <Loader2 size={16} className="animate-spin text-blue-500" />}
        {isDone && <CheckCircle2 size={16} className="text-emerald-500" />}
        {isError && <XCircle size={16} className="text-red-500" />}
        对比进度
      </h3>

      <div className="space-y-3">
        <div className="w-full bg-slate-100 rounded-full h-2.5">
          <div
            className={`h-2.5 rounded-full transition-all duration-300 ${isDone ? 'bg-emerald-500' : isError ? 'bg-red-500' : 'bg-blue-500'}`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>

        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>
            {status.completed_count} / {status.dataset_size} 已完成
            {status.error_count > 0 && <span className="text-red-500 ml-2">（{status.error_count} 错误）</span>}
          </span>
          <span>{pct.toFixed(0)}%</span>
        </div>

        {isRunning && status.current_entity && (
          <div className="text-xs text-slate-400">
            正在处理: <span className="text-slate-600 font-medium">{status.current_entity}</span>
          </div>
        )}

        {isDone && status.consistency_rate != null && (
          <div className="text-sm text-emerald-600 font-semibold">
            一致率: {fmtPct(status.consistency_rate)} · 差异记录: {status.diff_count} 条
          </div>
        )}
      </div>
    </div>
  );
}


// ─── 子面板: DiffAnalysisPanel ───

function DiffAnalysisPanel({ diff }: { diff: DiffAnalysis | null }) {
  if (!diff) return null;

  const labels = Array.from(
    new Set([
      ...Object.keys(diff.change_matrix),
      ...Object.values(diff.change_matrix).flatMap(r => Object.keys(r)),
    ])
  ).sort();

  const maxVal = Math.max(
    ...Object.values(diff.change_matrix).flatMap(r => Object.values(r)),
    1
  );

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 space-y-5">
      <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
        <BarChart3 size={16} /> 差异指标分析
      </h3>

      {/* 概览数字 */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-blue-50 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-blue-700">{fmtPct(diff.consistency_rate)}</div>
          <div className="text-xs text-blue-500 mt-1">一致率</div>
        </div>
        <div className="bg-slate-50 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-slate-800">{diff.dataset_size}</div>
          <div className="text-xs text-slate-500 mt-1">总记录数</div>
        </div>
        <div className="bg-amber-50 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-amber-700">{diff.diff_count}</div>
          <div className="text-xs text-amber-500 mt-1">差异记录</div>
        </div>
      </div>

      {/* 变更矩阵热力图 */}
      {labels.length > 0 && (
        <div>
          <div className="text-xs font-medium text-slate-500 mb-2">变更矩阵（行: 老标签, 列: 新标签）</div>
          <div className="overflow-x-auto">
            <table className="text-xs border-collapse">
              <thead>
                <tr>
                  <th className="p-1.5 text-slate-400 font-normal"></th>
                  {labels.map(l => (
                    <th key={l} className="p-1.5 text-slate-600 font-medium text-center whitespace-nowrap">{l}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {labels.map(row => (
                  <tr key={row}>
                    <td className="p-1.5 text-slate-600 font-medium whitespace-nowrap">{row}</td>
                    {labels.map(col => {
                      const val = diff.change_matrix[row]?.[col] ?? 0;
                      return (
                        <td key={col} className={`p-1.5 text-center min-w-[36px] rounded ${cmColor(val, maxVal)}`}>
                          {val > 0 ? val : ''}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 变更类型排行 */}
      {diff.change_type_ranking.length > 0 && (
        <div>
          <div className="text-xs font-medium text-slate-500 mb-2">变更类型排行</div>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {diff.change_type_ranking.map((item, i) => (
              <div key={i} className="flex items-center justify-between px-3 py-1.5 bg-slate-50 rounded-lg text-xs">
                <span className="text-slate-700">
                  {item.old_label} → {item.new_label}
                </span>
                <span className="font-semibold text-slate-900">{item.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 净变化 */}
      {Object.keys(diff.net_changes).length > 0 && (
        <div>
          <div className="text-xs font-medium text-slate-500 mb-2">各标签净变化</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(diff.net_changes).map(([label, change]) => (
              <span
                key={label}
                className={`px-2 py-1 rounded-lg text-xs font-medium ${
                  change > 0 ? 'bg-emerald-50 text-emerald-700' :
                  change < 0 ? 'bg-red-50 text-red-600' :
                  'bg-slate-100 text-slate-500'
                }`}
              >
                {label}: {change > 0 ? '+' : ''}{change}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


// ─── 子面板: ComparisonDetailView（复用 DetailView 组件） ───

function ComparisonDetailView({
  sessionId,
  entityKey,
  onBack,
  onAnnotate,
  taxonomyLabels,
  currentUserName = '',
}: {
  sessionId: string;
  entityKey: string;
  onBack: () => void;
  onAnnotate: () => void;
  taxonomyLabels: Array<{ id: string; displayName: string; enabled?: boolean }>;
  currentUserName?: string;
}) {
  const [currentLabel, setCurrentLabel] = useState<string>('');
  const [annotationOpen, setAnnotationOpen] = useState(false);
  const [selectedLabel, setSelectedLabel] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  // 加载当前标注状态
  useEffect(() => {
    fetch(`${API_BASE}/session/${sessionId}/record/${encodeURIComponent(entityKey)}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.human_label) setCurrentLabel(data.human_label); })
      .catch(() => {});
  }, [sessionId, entityKey]);

  const handleSubmitAnnotation = async () => {
    if (!selectedLabel) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/annotate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ annotations: [{ entity_key: entityKey, human_label: selectedLabel }], reviewer_name: currentUserName }),
      });
      if (res.ok) {
        setCurrentLabel(selectedLabel);
        setRefreshKey(k => k + 1);
        onAnnotate();
        setAnnotationOpen(false);
      }
    } catch { /* */ } finally {
      setSubmitting(false);
    }
  };

  // 自定义 fetchDetailFn
  const fetchDetailFn = useCallback(async (): Promise<any> => {
    const res = await fetch(`${API_BASE}/session/${sessionId}/record/${encodeURIComponent(entityKey)}`);
    if (!res.ok) throw new Error('加载详情失败');
    const data = await res.json();

    let wideRow: any = {};
    let staticProfile: any = null;
    let dynamicProfile: any = null;
    let decisionRecord: any = null;
    try { wideRow = data.wide_row_json ? JSON.parse(data.wide_row_json) : {}; } catch { /* */ }
    try { staticProfile = data.static_profile_json ? JSON.parse(data.static_profile_json) : null; } catch { /* */ }
    try { dynamicProfile = data.dynamic_profile_json ? JSON.parse(data.dynamic_profile_json) : null; } catch { /* */ }
    try { decisionRecord = data.decision_record_json ? JSON.parse(data.decision_record_json) : null; } catch { /* */ }

    if (data.human_label) setCurrentLabel(data.human_label);

    return {
      runId: `${sessionId}::${entityKey}`,
      entityKey: data.entity_key,
      enterpriseName: data.enterprise_name,
      businessScope: wideRow.business_scope || '',
      wideRow,
      staticProfile,
      dynamicProfile,
      decisionRecord,
      route: data.error_type ? 'error' : 'normal',
      errorType: data.error_type || null,
      audit: {},
      timingMs: null,
      annotations: (data.annotations || []).map((a: any, i: number) => ({
        annotatedLabel: a.human_label,
        annotated_label: a.human_label,
        reviewerName: a.reviewer_name || '',
        reviewer_name: a.reviewer_name || '',
        reviewerNotes: '',
        createdAt: a.created_at || '',
      })),
    };
  }, [sessionId, entityKey]);

  return (
    <div className="space-y-3">
      {/* 标注工具栏 */}
      <div className="flex items-center justify-end">
        <button
          onClick={() => { setSelectedLabel(currentLabel); setAnnotationOpen(true); }}
          className="px-5 py-2.5 bg-slate-900 text-white text-sm font-medium rounded-xl hover:bg-slate-800 transition-colors flex items-center gap-2 shadow-sm"
        >
          <CheckCircle2 size={14} /> 标注
        </button>
      </div>

      {/* DetailView */}
      <DetailView
        key={refreshKey}
        runId={`${sessionId}::${entityKey}`}
        onBack={onBack}
        taxonomyLabels={taxonomyLabels}
        fetchDetailFn={fetchDetailFn}
        showAnnotation={false}
      />

      {/* 标注弹窗（和原来 AnnotationDialog 一样的设计） */}
      {annotationOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={() => setAnnotationOpen(false)}>
          <div
            className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-md p-6"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-bold text-slate-900">标注审核</h3>
              <button onClick={() => setAnnotationOpen(false)} className="p-1 text-slate-400 hover:text-slate-600">
                <XCircle size={20} />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">当前标签</label>
                <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-700">{currentLabel || '未标注'}</div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">选择正确标签</label>
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
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={() => setAnnotationOpen(false)} className="flex-1 py-2.5 border border-slate-200 text-slate-700 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors">取消</button>
              <button onClick={handleSubmitAnnotation} disabled={submitting || !selectedLabel} className="flex-1 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:bg-slate-400 transition-colors flex items-center justify-center gap-2">
                {submitting ? <><Loader2 size={14} className="animate-spin" /> 提交中...</> : '提交标注'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ─── 子面板: AnnotationPanel ───

function AnnotationPanel({
  sessionId,
  onAnnotationUpdate,
  onSelectRecord,
  currentUserName = '',
}: {
  sessionId: string;
  onAnnotationUpdate: () => void;
  onSelectRecord?: (entityKey: string) => void;
  currentUserName?: string;
}) {
  const [records, setRecords] = useState<DiffRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [annotationProgress, setAnnotationProgress] = useState<{ annotated: number; total_diff: number }>({ annotated: 0, total_diff: 0 });
  const [loading, setLoading] = useState(false);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [taxonomyLabels, setTaxonomyLabels] = useState<string[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [batchLabel, setBatchLabel] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // 加载 taxonomy 标签列表
  useEffect(() => {
    fetch('/api/taxonomy')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.labels) {
          setTaxonomyLabels(data.labels.filter((l: any) => l.enabled !== false).map((l: any) => l.displayName || l.display_name || l.id));
        }
      })
      .catch(() => {});
  }, []);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/records?status=${filterStatus}&page=${page}&page_size=${pageSize}`);
      if (!res.ok) throw new Error('加载记录失败');
      const data: RecordsResponse = await res.json();
      setRecords(data.records);
      setTotal(data.total);
      setAnnotationProgress(data.annotation_progress);
    } catch {
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, [sessionId, filterStatus, page, pageSize]);

  useEffect(() => { fetchRecords(); }, [fetchRecords]);

  const handleAnnotate = async (entityKey: string, humanLabel: string) => {
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/annotate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ annotations: [{ entity_key: entityKey, human_label: humanLabel }], reviewer_name: currentUserName }),
      });
      if (!res.ok) throw new Error('标注失败');
      fetchRecords();
      onAnnotationUpdate();
    } catch { /* 静默 */ }
  };

  const handleBatchAnnotate = async () => {
    if (selectedKeys.size === 0 || !batchLabel) return;
    setSubmitting(true);
    try {
      const annotations = Array.from(selectedKeys).map(key => ({ entity_key: key, human_label: batchLabel }));
      const res = await fetch(`${API_BASE}/session/${sessionId}/annotate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ annotations, reviewer_name: currentUserName }),
      });
      if (!res.ok) throw new Error('批量标注失败');
      setSelectedKeys(new Set());
      setBatchLabel('');
      fetchRecords();
      onAnnotationUpdate();
    } catch { /* 静默 */ } finally {
      setSubmitting(false);
    }
  };

  const toggleSelect = (key: string) => {
    setSelectedKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const totalPages = Math.ceil(total / pageSize);
  const progressPct = annotationProgress.total_diff > 0
    ? (annotationProgress.annotated / annotationProgress.total_diff) * 100
    : 0;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
          <CheckCircle2 size={16} /> 人工标注
        </h3>
        <div className="text-xs text-slate-500">
          标注进度: {annotationProgress.annotated} / {annotationProgress.total_diff}
          （{progressPct.toFixed(0)}%）
        </div>
      </div>

      {/* 标注进度条 */}
      <div className="w-full bg-slate-100 rounded-full h-1.5">
        <div className="h-1.5 rounded-full bg-emerald-500 transition-all" style={{ width: `${progressPct}%` }} />
      </div>

      {/* 筛选 */}
      <div className="flex items-center gap-2">
        {['all', 'unannotated', 'annotated'].map(s => (
          <button
            key={s}
            onClick={() => { setFilterStatus(s); setPage(1); }}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
              filterStatus === s ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {s === 'all' ? '全部' : s === 'unannotated' ? '未标注' : '已标注'}
          </button>
        ))}
      </div>

      {/* 批量标注 */}
      {selectedKeys.size > 0 && (
        <div className="flex items-center gap-2 p-3 bg-blue-50 rounded-lg">
          <span className="text-xs text-blue-700">已选 {selectedKeys.size} 条</span>
          <select
            value={batchLabel}
            onChange={e => setBatchLabel(e.target.value)}
            className="flex-1 px-2 py-1 border border-blue-200 rounded text-xs outline-none focus:ring-1 focus:ring-blue-400 bg-white"
          >
            <option value="">选择标签...</option>
            {taxonomyLabels.map(l => <option key={l} value={l}>{l}</option>)}
          </select>
          <button
            onClick={handleBatchAnnotate}
            disabled={submitting || !batchLabel}
            className="px-3 py-1 bg-blue-600 text-white rounded text-xs font-medium hover:bg-blue-700 disabled:bg-slate-300"
          >
            {submitting ? '提交中...' : '批量标注'}
          </button>
        </div>
      )}

      {/* 记录列表 */}
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-slate-400 py-4">
          <Loader2 size={14} className="animate-spin" /> 加载中...
        </div>
      ) : records.length === 0 ? (
        <div className="text-sm text-slate-400 text-center py-4">暂无记录</div>
      ) : (
        <div className="space-y-1">
          {/* 表头 */}
          <div className="grid grid-cols-[32px_1fr_100px_100px_80px] gap-2 px-3 py-2 bg-slate-50 rounded-lg text-[10px] text-slate-500 font-medium">
            <div></div>
            <div>企业名称</div>
            <div>老标签</div>
            <div>新标签</div>
            <div>状态</div>
          </div>

          {records.map(r => {
            const isExpanded = expandedKey === r.entity_key;
            const isConsistent = r.old_label === r.new_label;
            return (
              <div key={r.entity_key} className="border border-slate-100 rounded-lg overflow-hidden">
                {/* 行摘要 */}
                <div
                  className={`grid grid-cols-[32px_1fr_100px_100px_80px] gap-2 px-3 py-2.5 items-center cursor-pointer hover:bg-slate-50 transition-colors ${isExpanded ? 'bg-blue-50/50' : ''}`}
                  onClick={() => onSelectRecord ? onSelectRecord(r.entity_key) : setExpandedKey(isExpanded ? null : r.entity_key)}
                >
                  <div>
                    <input
                      type="checkbox"
                      checked={selectedKeys.has(r.entity_key)}
                      onChange={e => { e.stopPropagation(); toggleSelect(r.entity_key); }}
                      onClick={e => e.stopPropagation()}
                      className="w-3.5 h-3.5 rounded border-slate-300"
                    />
                  </div>
                  <div className="text-xs text-slate-700 font-medium truncate" title={r.enterprise_name}>
                    {r.enterprise_name}
                  </div>
                  <div className="text-xs text-slate-600">{r.old_label}</div>
                  <div className={`text-xs font-medium ${isConsistent ? 'text-slate-600' : 'text-blue-600'}`}>
                    {r.new_label}
                  </div>
                  <div>
                    {r.human_label ? (
                      <span className="inline-block px-1.5 py-0.5 bg-emerald-50 text-emerald-700 text-[10px] rounded font-medium">已标注</span>
                    ) : (
                      <span className="inline-block px-1.5 py-0.5 bg-amber-50 text-amber-700 text-[10px] rounded font-medium">待标注</span>
                    )}
                  </div>
                </div>

                {/* 展开明细 */}
                {isExpanded && (
                  <div className="px-4 py-4 bg-slate-50/80 border-t border-slate-100 space-y-4">
                    {/* 标签对比 */}
                    <div className="grid grid-cols-3 gap-4">
                      <div className="bg-white rounded-lg p-3 border border-slate-200">
                        <div className="text-[10px] text-slate-400 mb-1">老标签</div>
                        <div className="text-sm font-semibold text-slate-700">{r.old_label}</div>
                      </div>
                      <div className="bg-white rounded-lg p-3 border border-blue-200">
                        <div className="text-[10px] text-blue-400 mb-1">新标签（模型预测）</div>
                        <div className="text-sm font-semibold text-blue-700">{r.new_label}</div>
                        {r.confidence_level && (
                          <div className="text-[10px] text-slate-400 mt-1">置信度: {r.confidence_level}</div>
                        )}
                      </div>
                      <div className="bg-white rounded-lg p-3 border border-emerald-200">
                        <div className="text-[10px] text-emerald-400 mb-1">人工标注</div>
                        <div className="text-sm font-semibold text-emerald-700">{r.human_label || '—'}</div>
                      </div>
                    </div>

                    {/* 决策原因 */}
                    {r.decision_reason && (
                      <div className="bg-white rounded-lg p-3 border border-slate-200">
                        <div className="text-[10px] text-slate-400 mb-1">决策原因</div>
                        <div className="text-xs text-slate-700 leading-relaxed">{r.decision_reason}</div>
                      </div>
                    )}

                    {/* 标注操作 */}
                    <div className="bg-white rounded-lg p-3 border border-slate-200">
                      <div className="text-[10px] text-slate-400 mb-2">标注审核</div>
                      <div className="flex items-center gap-3">
                        <select
                          value={r.human_label || ''}
                          onChange={e => {
                            const val = e.target.value;
                            if (val) handleAnnotate(r.entity_key, val);
                          }}
                          className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none bg-white"
                        >
                          <option value="">选择正确标签...</option>
                          {taxonomyLabels.map(l => (
                            <option key={l} value={l}>{l}</option>
                          ))}
                        </select>
                        {r.human_label && (
                          <span className="text-[10px] text-emerald-600 whitespace-nowrap">✓ 已标注为: {r.human_label}</span>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>第 {page} / {totalPages} 页，共 {total} 条</span>
          <div className="flex gap-1">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 disabled:opacity-40"
            >
              上一页
            </button>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


// ─── 子面板: ReportPanel ───

function ReportPanel({ report }: { report: ComparisonReport | null }) {
  if (!report) return null;

  const labels = Array.from(
    new Set([
      ...Object.keys(report.old_confusion_matrix),
      ...Object.values(report.old_confusion_matrix).flatMap(r => Object.keys(r)),
      ...Object.keys(report.new_confusion_matrix),
      ...Object.values(report.new_confusion_matrix).flatMap(r => Object.keys(r)),
    ])
  ).sort();

  const maxValOld = Math.max(...Object.values(report.old_confusion_matrix).flatMap(r => Object.values(r)), 1);
  const maxValNew = Math.max(...Object.values(report.new_confusion_matrix).flatMap(r => Object.values(r)), 1);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 space-y-5">
      <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
        <BarChart3 size={16} /> 评估报告
      </h3>

      {/* 覆盖率警告 */}
      {report.coverage_warning && (
        <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
          <AlertCircle size={14} /> {report.coverage_warning}
        </div>
      )}

      {/* 准确率对比 */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-slate-50 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-slate-700">{fmtPct(report.old_accuracy)}</div>
          <div className="text-xs text-slate-500 mt-1">老标签准确率</div>
        </div>
        <div className="bg-blue-50 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-blue-700">{fmtPct(report.new_accuracy)}</div>
          <div className="text-xs text-blue-500 mt-1">新标签准确率</div>
        </div>
        <div className={`rounded-xl p-4 text-center ${report.improvement > 0 ? 'bg-emerald-50' : report.improvement < 0 ? 'bg-red-50' : 'bg-slate-50'}`}>
          <div className={`text-2xl font-bold ${report.improvement > 0 ? 'text-emerald-700' : report.improvement < 0 ? 'text-red-600' : 'text-slate-600'}`}>
            {report.improvement > 0 ? '+' : ''}{fmtPct(report.improvement)}
          </div>
          <div className="text-xs mt-1 text-slate-500">改进幅度</div>
        </div>
        <div className="bg-slate-50 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-slate-700">{fmtPct(report.coverage)}</div>
          <div className="text-xs text-slate-500 mt-1">标注覆盖率</div>
        </div>
      </div>

      {/* 各标签指标表格 */}
      {report.label_metrics.length > 0 && (
        <div>
          <div className="text-xs font-medium text-slate-500 mb-2">各标签指标对比</div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="text-left py-2 px-2 text-slate-500 font-medium">标签</th>
                  <th className="text-right py-2 px-2 text-slate-500 font-medium">老精确率</th>
                  <th className="text-right py-2 px-2 text-slate-500 font-medium">老召回率</th>
                  <th className="text-right py-2 px-2 text-slate-500 font-medium">老F1</th>
                  <th className="text-right py-2 px-2 text-slate-500 font-medium">新精确率</th>
                  <th className="text-right py-2 px-2 text-slate-500 font-medium">新召回率</th>
                  <th className="text-right py-2 px-2 text-slate-500 font-medium">新F1</th>
                  <th className="text-center py-2 px-2 text-slate-500 font-medium">建议</th>
                </tr>
              </thead>
              <tbody>
                {report.label_metrics.map(m => (
                  <tr key={m.label} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="py-2 px-2 text-slate-700 font-medium">{m.label}</td>
                    <td className="py-2 px-2 text-right text-slate-600">{fmtPct(m.old_precision)}</td>
                    <td className="py-2 px-2 text-right text-slate-600">{fmtPct(m.old_recall)}</td>
                    <td className="py-2 px-2 text-right text-slate-600">{fmtPct(m.old_f1)}</td>
                    <td className="py-2 px-2 text-right text-blue-600">{fmtPct(m.new_precision)}</td>
                    <td className="py-2 px-2 text-right text-blue-600">{fmtPct(m.new_recall)}</td>
                    <td className="py-2 px-2 text-right text-blue-600">{fmtPct(m.new_f1)}</td>
                    <td className="py-2 px-2 text-center">
                      <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium ${
                        m.recommendation === 'adopt_new' ? 'bg-emerald-50 text-emerald-700' :
                        m.recommendation === 'keep_old' ? 'bg-red-50 text-red-600' :
                        'bg-slate-100 text-slate-500'
                      }`}>
                        {m.recommendation === 'adopt_new' ? '采用新标签' :
                         m.recommendation === 'keep_old' ? '保留老标签' : '无变化'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 混淆矩阵 */}
      {labels.length > 0 && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs font-medium text-slate-500 mb-2">老标签混淆矩阵（行: 人工标注, 列: 老标签）</div>
            <div className="overflow-x-auto">
              <table className="text-xs border-collapse">
                <thead>
                  <tr>
                    <th className="p-1.5 text-slate-400 font-normal"></th>
                    {labels.map(l => <th key={l} className="p-1.5 text-slate-600 font-medium text-center whitespace-nowrap">{l}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {labels.map(row => (
                    <tr key={row}>
                      <td className="p-1.5 text-slate-600 font-medium whitespace-nowrap">{row}</td>
                      {labels.map(col => {
                        const val = report.old_confusion_matrix[row]?.[col] ?? 0;
                        return <td key={col} className={`p-1.5 text-center min-w-[36px] rounded ${cmColor(val, maxValOld)}`}>{val > 0 ? val : ''}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div>
            <div className="text-xs font-medium text-slate-500 mb-2">新标签混淆矩阵（行: 人工标注, 列: 新标签）</div>
            <div className="overflow-x-auto">
              <table className="text-xs border-collapse">
                <thead>
                  <tr>
                    <th className="p-1.5 text-slate-400 font-normal"></th>
                    {labels.map(l => <th key={l} className="p-1.5 text-slate-600 font-medium text-center whitespace-nowrap">{l}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {labels.map(row => (
                    <tr key={row}>
                      <td className="p-1.5 text-slate-600 font-medium whitespace-nowrap">{row}</td>
                      {labels.map(col => {
                        const val = report.new_confusion_matrix[row]?.[col] ?? 0;
                        return <td key={col} className={`p-1.5 text-center min-w-[36px] rounded ${cmColor(val, maxValNew)}`}>{val > 0 ? val : ''}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* 系统建议 */}
      {report.recommendations.length > 0 && (
        <div>
          <div className="text-xs font-medium text-slate-500 mb-2">系统建议</div>
          <div className="space-y-1.5">
            {report.recommendations.map((rec, i) => (
              <div
                key={i}
                className={`flex items-center justify-between px-3 py-2 rounded-lg text-xs ${
                  rec.recommendation === 'adopt_new' ? 'bg-emerald-50 border border-emerald-200' :
                  rec.recommendation === 'keep_old' ? 'bg-red-50 border border-red-200' :
                  'bg-slate-50 border border-slate-200'
                }`}
              >
                <span className="font-medium text-slate-700">{rec.label}</span>
                <span className={`font-medium ${
                  rec.recommendation === 'adopt_new' ? 'text-emerald-700' :
                  rec.recommendation === 'keep_old' ? 'text-red-600' :
                  'text-slate-500'
                }`}>
                  {rec.recommendation === 'adopt_new' ? '建议采用新标签' :
                   rec.recommendation === 'keep_old' ? '建议保留老标签' : '无显著变化'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


// ─── 子面板: SessionHistoryList ───

function SessionHistoryList({
  sessions,
  loading,
  onSelect,
  onDelete,
}: {
  sessions: SessionSummary[];
  loading: boolean;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5">
      <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
        <History size={16} /> 历史会话
      </h3>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Loader2 size={14} className="animate-spin" /> 加载中...
        </div>
      ) : sessions.length === 0 ? (
        <p className="text-sm text-slate-400">暂无历史会话</p>
      ) : (
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {sessions.map(s => (
            <div
              key={s.session_id}
              className="flex items-center gap-3 p-3 rounded-xl border border-slate-100 hover:border-slate-200 transition-colors"
            >
              <div className="flex-1 min-w-0 cursor-pointer" onClick={() => onSelect(s.session_id)}>
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${
                    s.status === 'diff_ready' || s.status === 'annotating' || s.status === 'evaluated'
                      ? 'bg-emerald-50 text-emerald-700'
                      : s.status === 'running' ? 'bg-blue-50 text-blue-700'
                      : s.status === 'error' ? 'bg-red-50 text-red-600'
                      : 'bg-slate-50 text-slate-500'
                  }`}>
                    {s.status === 'diff_ready' ? '差异就绪' :
                     s.status === 'annotating' ? '标注中' :
                     s.status === 'evaluated' ? '已评估' :
                     s.status === 'running' ? '运行中' :
                     s.status === 'error' ? '错误' : s.status}
                  </span>
                  {s.consistency_rate != null && (
                    <span className="text-xs text-slate-600">一致率 {fmtPct(s.consistency_rate)}</span>
                  )}
                </div>
                <div className="text-[10px] text-slate-400 mt-1">
                  日期: {s.bizdate} · static:{s.prompt_version_static} dynamic:{s.prompt_version_dynamic} final:{s.prompt_version_final}
                </div>
                <div className="text-[10px] text-slate-400">
                  {s.dataset_size} 条 · 差异 {s.diff_count} · 已标注 {s.annotation_count} · {s.created_at}
                </div>
              </div>
              <button
                onClick={() => onDelete(s.session_id)}
                className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors shrink-0"
                title="删除"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


// ─── 主组件: ComparisonDashboard ───

export default function ComparisonDashboard({ currentUserName = '' }: { currentUserName?: string }) {
  // 当前会话
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<ComparisonStatusResponse | null>(null);
  const [diffAnalysis, setDiffAnalysis] = useState<DiffAnalysis | null>(null);
  const [report, setReport] = useState<ComparisonReport | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEntityKey, setSelectedEntityKey] = useState<string | null>(null);

  // 历史会话
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);

  // 报告加载
  const [reportLoading, setReportLoading] = useState(false);

  // Taxonomy 标签
  const [taxonomyLabels, setTaxonomyLabels] = useState<Array<{ id: string; displayName: string }>>([]);

  // 轮询 ref
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ─── 加载历史会话 ───
  const fetchSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/sessions`);
      if (!res.ok) {
        setSessions([]);
        return;
      }
      const data = await res.json();
      setSessions(Array.isArray(data) ? data : []);
    } catch {
      setSessions([]);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => { fetchSessions(); }, [fetchSessions]);

  // 加载 taxonomy 标签列表
  useEffect(() => {
    fetch('/api/taxonomy')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.labels) {
          setTaxonomyLabels(data.labels.filter((l: any) => l.enabled !== false).map((l: any) => ({ id: l.id, displayName: l.displayName || l.display_name || l.id })));
        }
      })
      .catch(() => {});
  }, []);

  // ─── 恢复轮询: 组件挂载时检查是否有正在运行的会话 ───
  useEffect(() => {
    fetch(`${API_BASE}/sessions`)
      .then(r => {
        if (!r.ok) return [];
        return r.json();
      })
      .then((data: SessionSummary[]) => {
        if (!Array.isArray(data)) return;
        const running = data.find(s => s.status === 'running');
        if (running) {
          setCurrentSessionId(running.session_id);
          startPolling(running.session_id);
        }
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── 轮询状态 ───
  const startPolling = useCallback((sessionId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);

    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/session/${sessionId}/status`);
        if (!res.ok) return;
        const status: ComparisonStatusResponse = await res.json();
        setSessionStatus(status);

        if (status.status !== 'running') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;

          // 自动加载差异分析
          if (status.status === 'diff_ready' || status.status === 'annotating' || status.status === 'evaluated') {
            loadDiffAnalysis(sessionId);
          }
          fetchSessions();
        }
      } catch { /* 轮询失败不中断 */ }
    }, 2000);
  }, [fetchSessions]); // eslint-disable-line react-hooks/exhaustive-deps

  // 清理轮询
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  // ─── 加载差异分析 ───
  const loadDiffAnalysis = async (sessionId: string) => {
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/diff`);
      if (!res.ok) return;
      const data: DiffAnalysis = await res.json();
      setDiffAnalysis(data);
    } catch { /* 静默 */ }
  };

  // ─── 启动对比 ───
  const handleLaunch = async (config: {
    bizdate: string;
    max_rows: number | null;
    lookback_days: number;
    prompt_version_static: string;
    prompt_version_dynamic: string;
    prompt_version_final: string;
  }) => {
    setStarting(true);
    setError(null);
    setReport(null);
    setDiffAnalysis(null);
    setSessionStatus(null);

    try {
      const res = await fetch(`${API_BASE}/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bizdate: config.bizdate,
          max_rows: config.max_rows,
          lookback_days: config.lookback_days,
          prompt_version_static: config.prompt_version_static,
          prompt_version_dynamic: config.prompt_version_dynamic,
          prompt_version_final: config.prompt_version_final,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: '启动失败' }));
        throw new Error(err.detail || '启动失败');
      }

      const data: { session_id: string; message: string } = await res.json();
      setCurrentSessionId(data.session_id);
      startPolling(data.session_id);
    } catch (e: any) {
      setError(e.message || '启动对比失败');
    } finally {
      setStarting(false);
    }
  };

  // ─── 选择历史会话 ───
  const handleSelectSession = async (sessionId: string) => {
    setCurrentSessionId(sessionId);
    setReport(null);
    setDiffAnalysis(null);
    setSessionStatus(null);

    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/status`);
      if (!res.ok) return;
      const status: ComparisonStatusResponse = await res.json();
      setSessionStatus(status);

      if (status.status === 'running') {
        startPolling(sessionId);
      } else if (status.status === 'diff_ready' || status.status === 'annotating' || status.status === 'evaluated') {
        loadDiffAnalysis(sessionId);
      }
    } catch { /* 静默 */ }
  };

  // ─── 删除会话 ───
  const handleDeleteSession = async (sessionId: string) => {
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}`, { method: 'DELETE' });
      if (!res.ok) return;
      if (currentSessionId === sessionId) {
        setCurrentSessionId(null);
        setSessionStatus(null);
        setDiffAnalysis(null);
        setReport(null);
      }
      fetchSessions();
    } catch { /* 静默 */ }
  };

  // ─── 生成报告 ───
  const handleGenerateReport = async () => {
    if (!currentSessionId) return;
    setReportLoading(true);
    try {
      const res = await fetch(`${API_BASE}/session/${currentSessionId}/report`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: '生成报告失败' }));
        setError(err.detail || '生成报告失败');
        return;
      }
      const data: ComparisonReport = await res.json();
      setReport(data);
    } catch (e: any) {
      setError(e.message || '生成报告失败');
    } finally {
      setReportLoading(false);
    }
  };

  // ─── 判断当前阶段 ───
  const isRunning = sessionStatus?.status === 'running';
  const isDiffReady = sessionStatus?.status === 'diff_ready' || sessionStatus?.status === 'annotating' || sessionStatus?.status === 'evaluated';
  const hasSession = !!currentSessionId;

  return (
    <div className="space-y-5">
      {/* 错误提示 */}
      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
          <XCircle size={14} /> {error}
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-600">×</button>
        </div>
      )}

      {/* 无会话: 显示启动面板 + 历史列表 */}
      {!hasSession && (
        <>
          <ComparisonLaunchPanel onLaunch={handleLaunch} starting={starting} />
          <SessionHistoryList
            sessions={sessions}
            loading={sessionsLoading}
            onSelect={handleSelectSession}
            onDelete={handleDeleteSession}
          />
        </>
      )}

      {/* 运行中: 显示进度面板 */}
      {hasSession && isRunning && (
        <>
          <ComparisonProgressPanel status={sessionStatus} />
          <button
            onClick={() => {
              if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
              setCurrentSessionId(null);
              setSessionStatus(null);
              fetchSessions();
            }}
            className="px-4 py-2 border border-slate-200 text-slate-700 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors"
          >
            返回
          </button>
        </>
      )}

      {/* 差异就绪: 显示差异分析 + 标注面板 或 详情页 */}
      {hasSession && isDiffReady && !selectedEntityKey && (
        <>
          <ComparisonProgressPanel status={sessionStatus} />
          <DiffAnalysisPanel diff={diffAnalysis} />
          <AnnotationPanel
            sessionId={currentSessionId!}
            onAnnotationUpdate={() => {
              // 刷新状态
              fetch(`${API_BASE}/session/${currentSessionId}/status`)
                .then(r => r.json())
                .then(setSessionStatus)
                .catch(() => {});
            }}
            onSelectRecord={(ek) => setSelectedEntityKey(ek)}
            currentUserName={currentUserName}
          />

          {/* 生成报告按钮 */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleGenerateReport}
              disabled={reportLoading}
              className="px-4 py-2.5 bg-slate-900 text-white rounded-xl text-sm font-medium hover:bg-slate-800 disabled:bg-slate-400 transition-colors flex items-center gap-2"
            >
              {reportLoading ? <><Loader2 size={14} className="animate-spin" /> 生成中...</> : <><BarChart3 size={14} /> 生成评估报告</>}
            </button>
            <button
              onClick={() => {
                setCurrentSessionId(null);
                setSessionStatus(null);
                setDiffAnalysis(null);
                setReport(null);
              }}
              className="px-4 py-2.5 border border-slate-200 text-slate-700 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors"
            >
              返回
            </button>
          </div>

          {/* 报告面板 */}
          <ReportPanel report={report} />
        </>
      )}

      {/* 详情页 */}
      {hasSession && isDiffReady && selectedEntityKey && (
        <ComparisonDetailView
          sessionId={currentSessionId!}
          entityKey={selectedEntityKey}
          onBack={() => setSelectedEntityKey(null)}
          onAnnotate={() => {
            // 标注已在 ComparisonDetailView 内部提交，这里只做状态刷新
            fetch(`${API_BASE}/session/${currentSessionId}/status`)
              .then(r => r.json())
              .then(setSessionStatus)
              .catch(() => {});
          }}
          taxonomyLabels={taxonomyLabels}
          currentUserName={currentUserName}
        />
      )}

      {/* 有会话但非运行/非差异就绪（如 error 状态）: 显示返回按钮 */}
      {hasSession && !isRunning && !isDiffReady && sessionStatus && (
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 text-center">
          <XCircle size={24} className="text-red-400 mx-auto mb-2" />
          <p className="text-sm text-slate-600 mb-3">会话状态: {sessionStatus.status}</p>
          <button
            onClick={() => {
              setCurrentSessionId(null);
              setSessionStatus(null);
              setDiffAnalysis(null);
              setReport(null);
            }}
            className="px-4 py-2 border border-slate-200 text-slate-700 rounded-xl text-sm font-medium hover:bg-slate-50"
          >
            返回
          </button>
        </div>
      )}
    </div>
  );
}
