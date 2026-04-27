import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Loader2,
  Calendar,
  Play,
  CheckCircle2,
  XCircle,
  BarChart3,
  History,
  GitCompareArrows,
  Trash2,
  ChevronDown,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  AlertCircle,
  Filter,
} from 'lucide-react';
import { api } from '../api/client';
import DetailView from './DetailView';
import type {
  AvailableDate,
  AnnotationDatasetSummary,
  BacktestRunRequest,
  BacktestStatus,
  AccuracyReport,
  BacktestRunSummary,
  ComparisonResult,
  LabelMetrics,
  MisclassifiedItem,
  FlipItem,
} from '../api/types';

// ─── 工具函数 ───

function fmtDate(d: string): string {
  if (/^\d{8}$/.test(d)) return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
  return d;
}

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

function diffColor(diff: number): string {
  if (diff > 0) return 'text-emerald-600';
  if (diff < 0) return 'text-red-600';
  return 'text-slate-500';
}

function diffBg(diff: number): string {
  if (diff > 0) return 'bg-emerald-50';
  if (diff < 0) return 'bg-red-50';
  return 'bg-slate-50';
}

// ─── 子面板: 标注数据集选择 ───

function AnnotationDatasetPanel({
  availableDates,
  selectedDates,
  onToggleDate,
  summary,
  summaryLoading,
}: {
  availableDates: AvailableDate[];
  selectedDates: string[];
  onToggleDate: (d: string) => void;
  summary: AnnotationDatasetSummary | null;
  summaryLoading: boolean;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5">
      <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
        <Calendar size={16} /> 选择标注数据集
      </h3>
      {availableDates.length === 0 ? (
        <p className="text-sm text-slate-400">暂无可用标注日期</p>
      ) : (
        <div className="flex flex-wrap gap-2 mb-4">
          {availableDates.map(d => {
            const sel = selectedDates.includes(d.date);
            return (
              <button
                key={d.date}
                onClick={() => onToggleDate(d.date)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  sel
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300'
                }`}
              >
                {fmtDate(d.date)}（{d.count}条）
              </button>
            );
          })}
        </div>
      )}

      {summaryLoading && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Loader2 size={14} className="animate-spin" /> 加载数据集统计...
        </div>
      )}

      {summary && !summaryLoading && (
        <div className="space-y-3">
          <div className="text-sm text-slate-600">
            共 <span className="font-semibold text-slate-900">{summary.total}</span> 条标注记录
          </div>
          {Object.keys(summary.labelDistribution).length > 0 && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-slate-500">标签分布</div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(summary.labelDistribution).map(([label, count]) => (
                  <span key={label} className="px-2 py-0.5 rounded bg-slate-100 text-xs text-slate-700">
                    {label}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}


// ─── 子面板: Prompt 版本配置 ───

interface PromptNodeConfig {
  displayName: string;
  default: string;
  versions: string[];
}

function PromptConfigPanel({
  config,
  onChange,
}: {
  config: { promptVersionStatic: string; promptVersionDynamic: string; promptVersionFinal: string };
  onChange: (field: string, value: string) => void;
}) {
  const [nodes, setNodes] = React.useState<Record<string, PromptNodeConfig>>({});

  React.useEffect(() => {
    api.getPromptVersions().then((data) => {
      if (data.nodes) setNodes(data.nodes);
    }).catch(() => {});
  }, []);

  const fields: { key: string; node: string; value: string }[] = [
    { key: 'promptVersionStatic', node: 'staticProfile', value: config.promptVersionStatic },
    { key: 'promptVersionDynamic', node: 'dynamicProfile', value: config.promptVersionDynamic },
    { key: 'promptVersionFinal', node: 'finalDecision', value: config.promptVersionFinal },
  ];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5">
      <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
        <ChevronDown size={16} /> Prompt 版本配置
      </h3>
      <div className="grid grid-cols-3 gap-4">
        {fields.map(f => {
          const nodeConfig = nodes[f.node];
          const versions = nodeConfig?.versions || [];
          const displayName = nodeConfig?.displayName || f.node;
          return (
            <div key={f.key}>
              <label className="block text-xs font-medium text-slate-500 mb-1">{displayName}</label>
              <select
                value={f.value}
                onChange={e => onChange(f.key, e.target.value)}
                className="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none"
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
  );
}

// ─── 子面板: 回溯进度 ───

function BacktestProgressPanel({
  status,
}: {
  status: BacktestStatus | null;
}) {
  if (!status) return null;

  const pct = status.datasetSize > 0 ? (status.completedCount / status.datasetSize) * 100 : 0;
  const isRunning = status.status === 'running' || status.status === 'pending';
  const isDone = status.status === 'done';
  const isError = status.status === 'error';

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5">
      <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
        {isRunning && <Loader2 size={16} className="animate-spin text-blue-500" />}
        {isDone && <CheckCircle2 size={16} className="text-emerald-500" />}
        {isError && <XCircle size={16} className="text-red-500" />}
        回溯进度
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
            {status.completedCount} / {status.datasetSize} 已完成
            {status.errorCount > 0 && <span className="text-red-500 ml-2">（{status.errorCount} 错误）</span>}
          </span>
          <span>{pct.toFixed(0)}%</span>
        </div>

        {isRunning && status.currentEntity && (
          <div className="text-xs text-slate-400">
            正在处理: <span className="text-slate-600 font-medium">{status.currentEntity}</span>
          </div>
        )}

        {isDone && status.accuracy != null && (
          <div className="text-sm text-emerald-600 font-semibold">
            准确率: {fmtPct(status.accuracy)}
          </div>
        )}
      </div>
    </div>
  );
}


// ─── 子面板: 准确率报告 ───

function ConfusionMatrix({ matrix }: { matrix: Record<string, Record<string, number>> }) {
  const labels = Array.from(new Set([...Object.keys(matrix), ...Object.values(matrix).flatMap(r => Object.keys(r))])).sort();
  if (labels.length === 0) return null;

  const maxVal = Math.max(...Object.values(matrix).flatMap(r => Object.values(r)), 1);

  return (
    <div className="overflow-x-auto">
      <div className="text-xs font-medium text-slate-500 mb-2">混淆矩阵（行: 标注, 列: 预测）</div>
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
                const val = matrix[row]?.[col] ?? 0;
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
  );
}

function AccuracyReportPanel({
  report,
  onClickEntity,
}: {
  report: AccuracyReport | null;
  onClickEntity?: (entityKey: string) => void;
}) {
  const [confFilter, setConfFilter] = useState<Set<string>>(new Set());
  const [resultFilter, setResultFilter] = useState<string>('all'); // all | correct | wrong | error
  const [labelFilter, setLabelFilter] = useState<string>('all');

  if (!report) return null;

  // 按置信度筛选 details，重新计算指标
  const isFiltering = confFilter.size > 0;
  const filteredDetails = !isFiltering
    ? report.details
    : report.details.filter(d => d.confidenceLevel && confFilter.has(d.confidenceLevel));

  const validFiltered = filteredDetails.filter(d => !d.errorType);
  const filteredTotal = validFiltered.length;
  const filteredCorrect = validFiltered.filter(d => d.match).length;
  const filteredErrorCount = filteredDetails.length - validFiltered.length;
  const filteredAccuracy = filteredTotal > 0 ? filteredCorrect / filteredTotal : 0;

  // 重新计算各标签指标
  const filteredLabelMetrics = (() => {
    if (validFiltered.length === 0) return [];
    const allLabels = new Set<string>();
    validFiltered.forEach(d => {
      if (d.annotatedLabel) allLabels.add(d.annotatedLabel);
      if (d.predictedLabel) allLabels.add(d.predictedLabel);
    });
    return Array.from(allLabels).sort().map(label => {
      const tp = validFiltered.filter(d => d.annotatedLabel === label && d.predictedLabel === label).length;
      const fp = validFiltered.filter(d => d.annotatedLabel !== label && d.predictedLabel === label).length;
      const fn = validFiltered.filter(d => d.annotatedLabel === label && d.predictedLabel !== label).length;
      const support = tp + fn;
      const precision = (tp + fp) > 0 ? tp / (tp + fp) : 0;
      const recall = (tp + fn) > 0 ? tp / (tp + fn) : 0;
      const f1 = (precision + recall) > 0 ? 2 * precision * recall / (precision + recall) : 0;
      return { label, precision, recall, f1, support };
    });
  })();

  // 重新计算混淆矩阵
  const filteredConfusionMatrix = (() => {
    const matrix: Record<string, Record<string, number>> = {};
    validFiltered.forEach(d => {
      if (!d.annotatedLabel || !d.predictedLabel) return;
      if (!matrix[d.annotatedLabel]) matrix[d.annotatedLabel] = {};
      matrix[d.annotatedLabel][d.predictedLabel] = (matrix[d.annotatedLabel][d.predictedLabel] || 0) + 1;
    });
    return matrix;
  })();

  // 收集所有出现过的置信度
  const confLevels = Array.from(new Set(report.details.map(d => d.confidenceLevel).filter(Boolean))) as string[];

  const displayAccuracy = isFiltering ? filteredAccuracy : report.accuracy;
  const displayTotal = isFiltering ? filteredTotal : report.total;
  const displayCorrect = isFiltering ? filteredCorrect : report.correct;
  const displayErrorCount = isFiltering ? filteredErrorCount : report.errorCount;
  const displayLabelMetrics = isFiltering ? filteredLabelMetrics : report.labelMetrics;
  const displayConfusionMatrix = isFiltering ? filteredConfusionMatrix : report.confusionMatrix;
  const displayDetails = filteredDetails;

  const toggleConf = (level: string) => {
    setConfFilter(prev => {
      const next = new Set(prev);
      if (next.has(level)) next.delete(level);
      else next.add(level);
      return next;
    });
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
          <BarChart3 size={16} /> 准确率报告
          {isFiltering && <span className="text-xs text-blue-500 font-normal">（筛选中）</span>}
        </h3>
        {confLevels.length > 0 && (
          <div className="flex items-center gap-1.5">
            <Filter size={12} className="text-slate-400" />
            <span className="text-[10px] text-slate-400">置信度:</span>
            {confLevels.map(level => (
              <button
                key={level}
                onClick={() => toggleConf(level)}
                className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                  confFilter.has(level)
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                }`}
              >
                {level === 'high' ? '高' : level === 'medium' ? '中' : level === 'low' ? '低' : level}
              </button>
            ))}
            {isFiltering && (
              <button
                onClick={() => setConfFilter(new Set())}
                className="px-2 py-0.5 rounded text-[10px] font-medium text-slate-400 hover:text-slate-600 hover:bg-slate-100"
              >
                清除
              </button>
            )}
          </div>
        )}
      </div>

      {/* 概览数字 */}
      <div className="grid grid-cols-5 gap-4">
        {report.originalAccuracy != null && !isFiltering && (
          <div className="bg-slate-100 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-slate-600">{fmtPct(report.originalAccuracy)}</div>
            <div className="text-xs text-slate-500 mt-1">原模型准确率</div>
          </div>
        )}
        <div className={`rounded-xl p-4 text-center ${
          !isFiltering && report.originalAccuracy != null
            ? displayAccuracy > report.originalAccuracy ? 'bg-emerald-50' : displayAccuracy < report.originalAccuracy ? 'bg-red-50' : 'bg-blue-50'
            : 'bg-blue-50'
        }`}>
          <div className={`text-2xl font-bold ${
            !isFiltering && report.originalAccuracy != null
              ? displayAccuracy > report.originalAccuracy ? 'text-emerald-700' : displayAccuracy < report.originalAccuracy ? 'text-red-600' : 'text-blue-700'
              : 'text-blue-700'
          }`}>{fmtPct(displayAccuracy)}</div>
          <div className="text-xs mt-1">
            <span className={
              !isFiltering && report.originalAccuracy != null
                ? displayAccuracy > report.originalAccuracy ? 'text-emerald-500' : displayAccuracy < report.originalAccuracy ? 'text-red-500' : 'text-blue-500'
                : 'text-blue-500'
            }>
              {isFiltering ? '筛选后准确率' : '新预测准确率'}
              {!isFiltering && report.originalAccuracy != null && (() => {
                const diff = displayAccuracy - report.originalAccuracy;
                if (Math.abs(diff) < 0.0001) return '';
                return diff > 0 ? ` ↑${fmtPct(diff)}` : ` ↓${fmtPct(Math.abs(diff))}`;
              })()}
            </span>
          </div>
        </div>
        <div className="bg-slate-50 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-slate-800">{displayTotal}</div>
          <div className="text-xs text-slate-500 mt-1">总样本</div>
        </div>
        <div className="bg-emerald-50 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-emerald-700">{displayCorrect}</div>
          <div className="text-xs text-emerald-500 mt-1">正确</div>
        </div>
        <div className="bg-red-50 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-red-600">{displayErrorCount}</div>
          <div className="text-xs text-red-500 mt-1">错误条目</div>
        </div>
      </div>

      {/* 各标签指标表格 */}
      {displayLabelMetrics.length > 0 && (
        <div>
          <div className="text-xs font-medium text-slate-500 mb-2">各标签指标</div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="text-left py-2 px-2 text-slate-500 font-medium">标签</th>
                  <th className="text-right py-2 px-2 text-slate-500 font-medium">精确率</th>
                  <th className="text-right py-2 px-2 text-slate-500 font-medium">召回率</th>
                  <th className="text-right py-2 px-2 text-slate-500 font-medium">F1</th>
                  <th className="text-right py-2 px-2 text-slate-500 font-medium">样本数</th>
                </tr>
              </thead>
              <tbody>
                {displayLabelMetrics.map(m => (
                  <tr key={m.label} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="py-2 px-2 text-slate-700 font-medium">{m.label}</td>
                    <td className="py-2 px-2 text-right text-slate-600">{fmtPct(m.precision)}</td>
                    <td className="py-2 px-2 text-right text-slate-600">{fmtPct(m.recall)}</td>
                    <td className="py-2 px-2 text-right text-slate-600">{fmtPct(m.f1)}</td>
                    <td className="py-2 px-2 text-right text-slate-500">{m.support}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 混淆矩阵 */}
      <ConfusionMatrix matrix={displayConfusionMatrix} />

      {/* 错误分类明细 */}
      {report.misclassified.length > 0 && (
        <div>
          <div className="text-xs font-medium text-slate-500 mb-2">
            错误分类明细（{report.misclassified.length} 条）
          </div>
          <div className="max-h-64 overflow-y-auto border border-slate-100 rounded-lg">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-50">
                <tr className="border-b border-slate-100">
                  <th className="text-left py-2 px-2 text-slate-500 font-medium">企业名称</th>
                  <th className="text-left py-2 px-2 text-slate-500 font-medium">标注标签</th>
                  <th className="text-left py-2 px-2 text-slate-500 font-medium">预测标签</th>
                  <th className="text-left py-2 px-2 text-slate-500 font-medium">置信度</th>
                </tr>
              </thead>
              <tbody>
                {report.misclassified.map(item => (
                  <tr key={item.entityKey} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="py-2 px-2">
                      <span className="text-slate-700">{item.enterpriseName || item.entityKey}</span>
                    </td>
                    <td className="py-2 px-2 text-slate-600">{item.annotatedLabel}</td>
                    <td className="py-2 px-2 text-red-600 font-medium">{item.predictedLabel}</td>
                    <td className="py-2 px-2 text-slate-500">{item.confidenceLevel ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 逐条明细表：原模型标签 | 人工标注 | 新预测标签 */}
      {report.details && displayDetails.length > 0 && (() => {
        // 按结果和标签筛选明细
        const detailFiltered = displayDetails.filter(d => {
          if (resultFilter === 'correct' && !d.match) return false;
          if (resultFilter === 'wrong' && (d.match || !!d.errorType)) return false;
          if (resultFilter === 'error' && !d.errorType) return false;
          if (labelFilter !== 'all' && d.annotatedLabel !== labelFilter) return false;
          return true;
        });
        const allLabels = Array.from(new Set(displayDetails.map(d => d.annotatedLabel).filter(Boolean))).sort();
        const correctCount = displayDetails.filter(d => d.match).length;
        const wrongCount = displayDetails.filter(d => !d.match && !d.errorType).length;
        const errorCount = displayDetails.filter(d => !!d.errorType).length;

        return (
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-medium text-slate-500">
              逐条明细（{detailFiltered.length} 条{(resultFilter !== 'all' || labelFilter !== 'all') ? `，筛选自 ${displayDetails.length} 条` : ''}）
            </div>
            <div className="flex items-center gap-3">
              {/* 结果筛选 */}
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-slate-400">结果:</span>
                {[
                  { key: 'all', label: '全部', count: displayDetails.length },
                  { key: 'correct', label: '✓ 正确', count: correctCount },
                  { key: 'wrong', label: '✗ 错误', count: wrongCount },
                  ...(errorCount > 0 ? [{ key: 'error', label: '异常', count: errorCount }] : []),
                ].map(opt => (
                  <button
                    key={opt.key}
                    onClick={() => setResultFilter(opt.key)}
                    className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                      resultFilter === opt.key
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                    }`}
                  >
                    {opt.label}({opt.count})
                  </button>
                ))}
              </div>
              {/* 标签筛选 */}
              {allLabels.length > 1 && (
                <div className="flex items-center gap-1">
                  <span className="text-[10px] text-slate-400">标签:</span>
                  <select
                    value={labelFilter}
                    onChange={e => setLabelFilter(e.target.value)}
                    className="text-[10px] px-1.5 py-0.5 border border-slate-200 rounded bg-white text-slate-600 outline-none"
                  >
                    <option value="all">全部标签</option>
                    {allLabels.map(l => (
                      <option key={l} value={l}>{l}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          </div>
          <div className="max-h-[480px] overflow-y-auto border border-slate-100 rounded-lg">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-50 z-10">
                <tr className="border-b border-slate-200">
                  <th className="text-left py-2.5 px-3 text-slate-500 font-medium">企业名称</th>
                  <th className="text-left py-2.5 px-3 text-slate-500 font-medium">原模型标签</th>
                  <th className="text-left py-2.5 px-3 text-slate-500 font-medium">人工标注</th>
                  <th className="text-left py-2.5 px-3 text-slate-500 font-medium">新预测标签</th>
                  <th className="text-left py-2.5 px-3 text-slate-500 font-medium">置信度</th>
                  <th className="text-center py-2.5 px-3 text-slate-500 font-medium">结果</th>
                </tr>
              </thead>
              <tbody>
                {detailFiltered.map(d => {
                  const hasError = !!d.errorType;
                  const isMatch = d.match;
                  const originalChanged = d.originalLabel && d.predictedLabel && d.originalLabel !== d.predictedLabel;
                  return (
                    <tr key={d.entityKey} className={`border-b border-slate-50 hover:bg-slate-50 ${hasError ? 'bg-amber-50/50' : ''}`}>
                      <td className="py-2 px-3 font-medium max-w-[200px] truncate" title={d.enterpriseName}>
                        {onClickEntity ? (
                          <button
                            onClick={() => onClickEntity(d.entityKey)}
                            className="text-blue-600 hover:text-blue-700 hover:underline text-left"
                          >
                            {d.enterpriseName || d.entityKey}
                          </button>
                        ) : (
                          <span className="text-slate-700">{d.enterpriseName || d.entityKey}</span>
                        )}
                      </td>
                      <td className="py-2 px-3 text-slate-500">{d.originalLabel ?? '-'}</td>
                      <td className="py-2 px-3 text-slate-700 font-medium">{d.annotatedLabel}</td>
                      <td className={`py-2 px-3 font-medium ${
                        hasError ? 'text-amber-600' :
                        isMatch ? 'text-emerald-600' : 'text-red-600'
                      }`}>
                        {hasError ? `错误: ${d.errorType}` : d.predictedLabel ?? '-'}
                        {originalChanged && !hasError && (
                          <span className="ml-1 text-[10px] text-slate-400">
                            (原: {d.originalLabel})
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-3 text-slate-500">{d.confidenceLevel ?? '-'}</td>
                      <td className="py-2 px-3 text-center">
                        {hasError ? (
                          <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-700">错误</span>
                        ) : isMatch ? (
                          <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-50 text-emerald-700">✓ 正确</span>
                        ) : (
                          <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-50 text-red-600">✗ 错误</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        );
      })()}
    </div>
  );
}


// ─── 子面板: 历史运行列表 ───

function HistoryRunList({
  runs,
  loading,
  selectedForCompare,
  onToggleCompare,
  onCompare,
  onDelete,
  onViewReport,
}: {
  runs: BacktestRunSummary[];
  loading: boolean;
  selectedForCompare: string[];
  onToggleCompare: (id: string) => void;
  onCompare: () => void;
  onDelete: (id: string) => void;
  onViewReport: (id: string) => void;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
          <History size={16} /> 历史运行
        </h3>
        {selectedForCompare.length === 2 && (
          <button
            onClick={onCompare}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700 transition-colors"
          >
            <GitCompareArrows size={14} /> 对比选中
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Loader2 size={14} className="animate-spin" /> 加载历史运行...
        </div>
      ) : runs.length === 0 ? (
        <p className="text-sm text-slate-400">暂无历史运行记录</p>
      ) : (
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {runs.map(run => {
            const isSelected = selectedForCompare.includes(run.backtestRunId);
            const isDone = run.status === 'done';
            return (
              <div
                key={run.backtestRunId}
                className={`flex items-center gap-3 p-3 rounded-xl border transition-colors ${
                  isSelected ? 'border-blue-300 bg-blue-50' : 'border-slate-100 hover:border-slate-200'
                }`}
              >
                {/* 对比选择框 */}
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => onToggleCompare(run.backtestRunId)}
                  disabled={!isDone || (!isSelected && selectedForCompare.length >= 2)}
                  className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:opacity-40"
                />

                {/* 运行信息 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${
                      isDone ? 'bg-emerald-50 text-emerald-700' :
                      run.status === 'running' ? 'bg-blue-50 text-blue-700' :
                      run.status === 'error' ? 'bg-red-50 text-red-600' :
                      'bg-slate-50 text-slate-500'
                    }`}>
                      {isDone ? '完成' : run.status === 'running' ? '运行中' : run.status === 'error' ? '错误' : '等待'}
                    </span>
                    {isDone && run.accuracy != null && (
                      <span className="text-xs font-semibold text-slate-700">准确率 {fmtPct(run.accuracy)}</span>
                    )}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-1">
                    {run.ptDates.map(fmtDate).join(', ')} · static:{run.promptVersionStatic} dynamic:{run.promptVersionDynamic} final:{run.promptVersionFinal}
                  </div>
                  <div className="text-[10px] text-slate-400">
                    {run.datasetSize} 条 · {run.createdAt}
                  </div>
                </div>

                {/* 操作按钮 */}
                <div className="flex items-center gap-1 shrink-0">
                  {isDone && (
                    <button
                      onClick={() => onViewReport(run.backtestRunId)}
                      className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                      title="查看报告"
                    >
                      <BarChart3 size={14} />
                    </button>
                  )}
                  <button
                    onClick={() => onDelete(run.backtestRunId)}
                    className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                    title="删除"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {selectedForCompare.length > 0 && selectedForCompare.length < 2 && (
        <div className="mt-2 text-[10px] text-slate-400">
          已选 {selectedForCompare.length} 个，请再选 {2 - selectedForCompare.length} 个进行对比
        </div>
      )}
    </div>
  );
}


// ─── 子面板: 对比视图 ───

function ComparisonView({
  comparison,
  onClose,
}: {
  comparison: ComparisonResult;
  onClose: () => void;
}) {
  const [flipFilter, setFlipFilter] = useState<string>('all');

  const filteredFlips = comparison.flips.filter(f =>
    flipFilter === 'all' ? true : f.direction === flipFilter
  );

  const diffLabels = Array.from(
    new Set([
      ...Object.keys(comparison.confusionMatrixA),
      ...Object.values(comparison.confusionMatrixA).flatMap(r => Object.keys(r)),
      ...Object.keys(comparison.confusionMatrixB),
      ...Object.values(comparison.confusionMatrixB).flatMap(r => Object.keys(r)),
    ])
  ).sort();

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
          <GitCompareArrows size={16} /> 运行对比
        </h3>
        <button
          onClick={onClose}
          className="text-xs text-slate-400 hover:text-slate-600 px-2 py-1 rounded hover:bg-slate-50"
        >
          关闭对比
        </button>
      </div>

      {/* 准确率对比 */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-slate-50 rounded-xl p-4 text-center">
          <div className="text-xs text-slate-500 mb-1">运行 A</div>
          <div className="text-lg font-bold text-slate-800">
            {comparison.runA.accuracy != null ? fmtPct(comparison.runA.accuracy) : '-'}
          </div>
          <div className="text-[10px] text-slate-400 mt-1">{comparison.runA.createdAt}</div>
        </div>
        <div className={`rounded-xl p-4 text-center ${diffBg(comparison.accuracyDiff)}`}>
          <div className="text-xs text-slate-500 mb-1">差异</div>
          <div className={`text-lg font-bold ${diffColor(comparison.accuracyDiff)}`}>
            {comparison.accuracyDiff > 0 ? '+' : ''}{fmtPct(comparison.accuracyDiff)}
          </div>
          <div className={`text-[10px] mt-1 ${diffColor(comparison.accuracyDiff)}`}>
            {comparison.accuracyDiff > 0 ? '↑ 提升' : comparison.accuracyDiff < 0 ? '↓ 下降' : '无变化'}
          </div>
        </div>
        <div className="bg-slate-50 rounded-xl p-4 text-center">
          <div className="text-xs text-slate-500 mb-1">运行 B</div>
          <div className="text-lg font-bold text-slate-800">
            {comparison.runB.accuracy != null ? fmtPct(comparison.runB.accuracy) : '-'}
          </div>
          <div className="text-[10px] text-slate-400 mt-1">{comparison.runB.createdAt}</div>
        </div>
      </div>

      {/* 翻转明细 */}
      {comparison.flips.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-medium text-slate-500">
              翻转明细（{comparison.flips.length} 条）
            </div>
            <div className="flex items-center gap-1">
              <Filter size={12} className="text-slate-400" />
              {[
                { key: 'all', label: '全部' },
                { key: 'improved', label: '改善' },
                { key: 'degraded', label: '恶化' },
                { key: 'changed', label: '变化' },
              ].map(opt => (
                <button
                  key={opt.key}
                  onClick={() => setFlipFilter(opt.key)}
                  className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                    flipFilter === opt.key
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          <div className="max-h-64 overflow-y-auto border border-slate-100 rounded-lg">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-50">
                <tr className="border-b border-slate-100">
                  <th className="text-left py-2 px-2 text-slate-500 font-medium">企业名称</th>
                  <th className="text-left py-2 px-2 text-slate-500 font-medium">标注</th>
                  <th className="text-left py-2 px-2 text-slate-500 font-medium">运行A</th>
                  <th className="text-left py-2 px-2 text-slate-500 font-medium">运行B</th>
                  <th className="text-left py-2 px-2 text-slate-500 font-medium">方向</th>
                </tr>
              </thead>
              <tbody>
                {filteredFlips.map(flip => (
                  <tr key={flip.entityKey} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="py-2 px-2 text-slate-700">{flip.enterpriseName}</td>
                    <td className="py-2 px-2 text-slate-600">{flip.annotatedLabel}</td>
                    <td className="py-2 px-2 text-slate-600">{flip.labelA}</td>
                    <td className="py-2 px-2 text-slate-600">{flip.labelB}</td>
                    <td className="py-2 px-2">
                      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${
                        flip.direction === 'improved' ? 'bg-emerald-50 text-emerald-700' :
                        flip.direction === 'degraded' ? 'bg-red-50 text-red-600' :
                        'bg-amber-50 text-amber-700'
                      }`}>
                        {flip.direction === 'improved' && <ArrowUpRight size={10} />}
                        {flip.direction === 'degraded' && <ArrowDownRight size={10} />}
                        {flip.direction === 'improved' ? '改善' : flip.direction === 'degraded' ? '恶化' : '变化'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 混淆矩阵差异 */}
      {diffLabels.length > 0 && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs font-medium text-slate-500 mb-2">运行 A 混淆矩阵</div>
            <ConfusionMatrix matrix={comparison.confusionMatrixA} />
          </div>
          <div>
            <div className="text-xs font-medium text-slate-500 mb-2">运行 B 混淆矩阵</div>
            <ConfusionMatrix matrix={comparison.confusionMatrixB} />
          </div>
        </div>
      )}
    </div>
  );
}


// ─── 主组件: BacktestDashboard ───

export default function BacktestDashboard() {
  // 可用日期 & 数据集
  const [availableDates, setAvailableDates] = useState<AvailableDate[]>([]);
  const [selectedDates, setSelectedDates] = useState<string[]>([]);
  const [summary, setSummary] = useState<AnnotationDatasetSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  // 基线报告（原模型现状）
  const [baselineReport, setBaselineReport] = useState<any | null>(null);
  const [baselineLoading, setBaselineLoading] = useState(false);
  const [baselineConfFilter, setBaselineConfFilter] = useState<Set<string>>(new Set());
  const [baselineResultFilter, setBaselineResultFilter] = useState<string>('all');
  const [baselineLabelFilter, setBaselineLabelFilter] = useState<string>('all');

  // Prompt 配置（初始值从 API 加载后更新）
  const [promptConfig, setPromptConfig] = useState({
    promptVersionStatic: 'v1',
    promptVersionDynamic: 'v1',
    promptVersionFinal: 'v2',
  });

  // 加载 Prompt 版本配置，设置默认值
  useEffect(() => {
    api.getPromptVersions().then((data) => {
      if (data.nodes) {
        const sp = data.nodes.staticProfile || data.nodes.static_profile;
        const dp = data.nodes.dynamicProfile || data.nodes.dynamic_profile;
        const fd = data.nodes.finalDecision || data.nodes.final_decision;
        setPromptConfig({
          promptVersionStatic: sp?.default || 'v1',
          promptVersionDynamic: dp?.default || 'v1',
          promptVersionFinal: fd?.default || 'v2',
        });
      }
    }).catch(() => {});
  }, []);

  // 当前运行
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<BacktestStatus | null>(null);
  const [report, setReport] = useState<AccuracyReport | null>(null);
  const [starting, setStarting] = useState(false);

  // 历史运行
  const [historyRuns, setHistoryRuns] = useState<BacktestRunSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedForCompare, setSelectedForCompare] = useState<string[]>([]);

  // 对比
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);

  // 错误
  const [error, setError] = useState<string | null>(null);

  // 轮询 ref
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 回溯结果详情面板（直接使用 DetailView）
  const [detailRunId, setDetailRunId] = useState<string | null>(null);
  const [detailRunPt, setDetailRunPt] = useState<string | undefined>(undefined);
  const [detailFetchFn, setDetailFetchFn] = useState<((rid: string, pt?: string) => Promise<any>) | undefined>(undefined);

  // ─── 初始化: 加载可用日期和历史运行 ───
  const fetchAvailableDates = useCallback(async () => {
    try {
      const dates = await api.getBacktestAvailableDates();
      setAvailableDates(dates);
    } catch (e: any) {
      setError(e.message || '加载可用日期失败');
    }
  }, []);

  const fetchHistoryRuns = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const runs = await api.getBacktestRuns();
      setHistoryRuns(runs);
    } catch {
      // 静默处理
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAvailableDates();
    fetchHistoryRuns();
  }, [fetchAvailableDates, fetchHistoryRuns]);

  // ─── 日期选择 → 加载摘要 ───
  const handleToggleDate = useCallback((date: string) => {
    setSelectedDates(prev => {
      const next = prev.includes(date) ? prev.filter(d => d !== date) : [...prev, date];
      return next;
    });
    // 切换日期时清掉旧的回溯报告，让基线报告显示出来
    setReport(null);
    setRunStatus(null);
    setCurrentRunId(null);
    setComparison(null);
  }, []);

  useEffect(() => {
    if (selectedDates.length === 0) {
      setSummary(null);
      setBaselineReport(null);
      return;
    }
    setSummaryLoading(true);
    setBaselineLoading(true);
    api.getBacktestAnnotationSummary(selectedDates)
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setSummaryLoading(false));
    api.getBaselineReport(selectedDates)
      .then(setBaselineReport)
      .catch(() => setBaselineReport(null))
      .finally(() => setBaselineLoading(false));
  }, [selectedDates]);

  // ─── 轮询状态 ───
  const startPolling = useCallback((runId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);

    pollRef.current = setInterval(async () => {
      try {
        const status = await api.getBacktestStatus(runId);
        setRunStatus(status);

        if (status.status === 'done' || status.status === 'error') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;

          // 自动加载报告
          if (status.status === 'done') {
            try {
              const rpt = await api.getBacktestReport(runId);
              setReport(rpt);
            } catch {
              // 静默
            }
          }

          // 刷新历史列表
          fetchHistoryRuns();
        }
      } catch {
        // 轮询失败时不中断
      }
    }, 2000);
  }, [fetchHistoryRuns]);

  // 清理轮询
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // ─── 恢复轮询: 组件挂载时检查是否有正在运行的任务 ───
  useEffect(() => {
    api.getBacktestRuns().then((runs) => {
      const running = runs.find((r: any) => r.status === 'running' || r.status === 'pending');
      if (running) {
        setCurrentRunId(running.backtestRunId);
        startPolling(running.backtestRunId);
      }
    }).catch(() => {});
  }, [startPolling]);

  // ─── 开始回溯 ───
  const handleStartBacktest = useCallback(async () => {
    if (selectedDates.length === 0) return;
    setStarting(true);
    setError(null);
    setReport(null);
    setRunStatus(null);
    setComparison(null);

    try {
      const result = await api.startBacktestRun({
        ptDates: selectedDates,
        promptVersionStatic: promptConfig.promptVersionStatic,
        promptVersionDynamic: promptConfig.promptVersionDynamic,
        promptVersionFinal: promptConfig.promptVersionFinal,
      });
      setCurrentRunId(result.backtestRunId);
      setRunStatus({
        backtestRunId: result.backtestRunId,
        status: 'pending',
        datasetSize: result.datasetSize,
        completedCount: 0,
        errorCount: 0,
        currentEntity: null,
        accuracy: null,
      });
      startPolling(result.backtestRunId);
    } catch (e: any) {
      setError(e.message || '启动评估失败');
    } finally {
      setStarting(false);
    }
  }, [selectedDates, promptConfig, startPolling]);

  // ─── 查看历史报告 ───
  const handleViewReport = useCallback(async (runId: string) => {
    setComparison(null);
    setCurrentRunId(runId);
    try {
      const rpt = await api.getBacktestReport(runId);
      setReport(rpt);
      setRunStatus(null);
    } catch (e: any) {
      setError(e.message || '加载报告失败');
    }
  }, []);

  // ─── 删除运行 ───
  const handleDelete = useCallback(async (runId: string) => {
    try {
      await api.deleteBacktestRun(runId);
      setSelectedForCompare(prev => prev.filter(id => id !== runId));
      if (currentRunId === runId) {
        setCurrentRunId(null);
        setReport(null);
        setRunStatus(null);
      }
      fetchHistoryRuns();
    } catch (e: any) {
      setError(e.message || '删除失败');
    }
  }, [currentRunId, fetchHistoryRuns]);

  // ─── 对比选择 ───
  const handleToggleCompare = useCallback((id: string) => {
    setSelectedForCompare(prev => {
      if (prev.includes(id)) return prev.filter(x => x !== id);
      if (prev.length >= 2) return prev;
      return [...prev, id];
    });
  }, []);

  const handleCompare = useCallback(async () => {
    if (selectedForCompare.length !== 2) return;
    setCompareLoading(true);
    setReport(null);
    setError(null);
    try {
      const result = await api.compareBacktestRuns(selectedForCompare[0], selectedForCompare[1]);
      setComparison(result);
    } catch (e: any) {
      setError(e.message || '对比失败');
    } finally {
      setCompareLoading(false);
    }
  }, [selectedForCompare]);

  // ─── Prompt 配置变更 ───
  const handlePromptChange = useCallback((field: string, value: string) => {
    setPromptConfig(prev => ({ ...prev, [field]: value }));
  }, []);

  // ─── 查看回溯结果详情 ───
  // 回溯明细点击：用 original-detail API 获取原始运行数据，在 DetailView 中展示
  const handleViewResultDetail = useCallback((entityKey: string) => {
    // 回溯报告点击：优先用 backtest result detail API（包含完整画像数据）
    if (currentRunId) {
      const fetchFn = async (_rid: string, _pt?: string) => {
        return api.getBacktestResultDetail(currentRunId, entityKey) as any;
      };
      setDetailRunId(entityKey);
      setDetailRunPt(undefined);
      setDetailFetchFn(() => fetchFn);
      return;
    }
    // 兜底：从 baseline 中找 run_id
    const baselineDetail = baselineReport?.details?.find((d: any) => d.entityKey === entityKey);
    const runId = baselineDetail?.runId;
    if (runId) {
      setDetailRunId(runId);
      setDetailRunPt(baselineDetail?.pt);
      setDetailFetchFn(undefined);
    }
  }, [baselineReport, currentRunId]);

  const isRunning = runStatus?.status === 'running' || runStatus?.status === 'pending';

  return (
    <div className="space-y-6 pb-10">
      {/* 页面标题 */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
          <BarChart3 size={20} className="text-blue-600" /> 效果评估
        </h2>
        <button
          onClick={() => { fetchAvailableDates(); fetchHistoryRuns(); }}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
        >
          <RefreshCw size={14} /> 刷新
        </button>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-600">
          <AlertCircle size={16} />
          {error}
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-600">
            <XCircle size={14} />
          </button>
        </div>
      )}

      {/* 配置区域 */}
      <div className="grid grid-cols-2 gap-6">
        <AnnotationDatasetPanel
          availableDates={availableDates}
          selectedDates={selectedDates}
          onToggleDate={handleToggleDate}
          summary={summary}
          summaryLoading={summaryLoading}
        />
        <div className="space-y-4">
          <PromptConfigPanel config={promptConfig} onChange={handlePromptChange} />
          <button
            onClick={handleStartBacktest}
            disabled={selectedDates.length === 0 || starting || isRunning}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors"
          >
            {starting ? (
              <><Loader2 size={16} className="animate-spin" /> 启动中...</>
            ) : isRunning ? (
              <><Loader2 size={16} className="animate-spin" /> 运行中...</>
            ) : (
              <><Play size={16} /> 开始评估</>
            )}
          </button>
        </div>
      </div>

      {/* 基线报告（优化前现状）— 选完日期即可查看 */}
      {baselineLoading && (
        <div className="flex items-center gap-2 py-4 text-sm text-slate-400">
          <Loader2 size={14} className="animate-spin" /> 加载原模型现状...
        </div>
      )}
      {baselineReport && !baselineLoading && !report && (() => {
        const blDetails = baselineReport.details || [];
        const blConfLevels = Array.from(new Set(blDetails.map((d: any) => d.confidenceLevel).filter(Boolean))) as string[];
        const blIsFiltering = baselineConfFilter.size > 0;
        const blFiltered = !blIsFiltering ? blDetails : blDetails.filter((d: any) => d.confidenceLevel && baselineConfFilter.has(d.confidenceLevel));
        const blValid = blFiltered.filter((d: any) => d.match !== undefined);
        const blTotal = blValid.length;
        const blCorrect = blValid.filter((d: any) => d.match).length;
        const blAccuracy = blTotal > 0 ? blCorrect / blTotal : 0;

        // 重新计算标签指标
        const blLabelMetrics = (() => {
          const validItems = blFiltered.filter((d: any) => d.originalLabel);
          if (validItems.length === 0) return [];
          const labels = new Set<string>();
          validItems.forEach((d: any) => { if (d.annotatedLabel) labels.add(d.annotatedLabel); if (d.originalLabel) labels.add(d.originalLabel); });
          return Array.from(labels).sort().map(label => {
            const tp = validItems.filter((d: any) => d.annotatedLabel === label && d.originalLabel === label).length;
            const fp = validItems.filter((d: any) => d.annotatedLabel !== label && d.originalLabel === label).length;
            const fn = validItems.filter((d: any) => d.annotatedLabel === label && d.originalLabel !== label).length;
            const support = tp + fn;
            const precision = (tp + fp) > 0 ? tp / (tp + fp) : 0;
            const recall = (tp + fn) > 0 ? tp / (tp + fn) : 0;
            const f1 = (precision + recall) > 0 ? 2 * precision * recall / (precision + recall) : 0;
            return { label, precision, recall, f1, support };
          });
        })();

        const blConfMatrix = (() => {
          const matrix: Record<string, Record<string, number>> = {};
          blFiltered.filter((d: any) => d.originalLabel && d.annotatedLabel).forEach((d: any) => {
            if (!matrix[d.annotatedLabel]) matrix[d.annotatedLabel] = {};
            matrix[d.annotatedLabel][d.originalLabel] = (matrix[d.annotatedLabel][d.originalLabel] || 0) + 1;
          });
          return matrix;
        })();

        const displayBLMetrics = blIsFiltering ? blLabelMetrics : baselineReport.labelMetrics;
        const displayBLMatrix = blIsFiltering ? blConfMatrix : baselineReport.confusionMatrix;
        const displayBLAccuracy = blIsFiltering ? blAccuracy : baselineReport.accuracy;
        const displayBLTotal = blIsFiltering ? blTotal : baselineReport.total;
        const displayBLCorrect = blIsFiltering ? blCorrect : baselineReport.correct;

        const toggleBLConf = (level: string) => {
          setBaselineConfFilter(prev => {
            const next = new Set(prev);
            if (next.has(level)) next.delete(level);
            else next.add(level);
            return next;
          });
        };

        return (
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5 space-y-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <BarChart3 size={16} /> 优化前现状（原模型 vs 人工标注）
              {blIsFiltering && <span className="text-xs text-blue-500 font-normal">（筛选中）</span>}
            </h3>
            {blConfLevels.length > 0 && (
              <div className="flex items-center gap-1.5">
                <Filter size={12} className="text-slate-400" />
                <span className="text-[10px] text-slate-400">置信度:</span>
                {blConfLevels.map(level => (
                  <button
                    key={level}
                    onClick={() => toggleBLConf(level)}
                    className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                      baselineConfFilter.has(level)
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                    }`}
                  >
                    {level === 'high' ? '高' : level === 'medium' ? '中' : level === 'low' ? '低' : level}
                  </button>
                ))}
                {blIsFiltering && (
                  <button onClick={() => setBaselineConfFilter(new Set())} className="px-2 py-0.5 rounded text-[10px] font-medium text-slate-400 hover:text-slate-600 hover:bg-slate-100">清除</button>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-4 gap-4">
            <div className="bg-slate-100 rounded-xl p-4 text-center">
              <div className="text-2xl font-bold text-slate-700">{fmtPct(displayBLAccuracy)}</div>
              <div className="text-xs text-slate-500 mt-1">{blIsFiltering ? '筛选后准确率' : '原模型准确率'}</div>
            </div>
            <div className="bg-slate-50 rounded-xl p-4 text-center">
              <div className="text-2xl font-bold text-slate-800">{displayBLTotal}</div>
              <div className="text-xs text-slate-500 mt-1">总样本</div>
            </div>
            <div className="bg-emerald-50 rounded-xl p-4 text-center">
              <div className="text-2xl font-bold text-emerald-700">{displayBLCorrect}</div>
              <div className="text-xs text-emerald-500 mt-1">正确</div>
            </div>
            <div className="bg-red-50 rounded-xl p-4 text-center">
              <div className="text-2xl font-bold text-red-600">{displayBLTotal - displayBLCorrect}</div>
              <div className="text-xs text-red-500 mt-1">错误</div>
            </div>
          </div>

          {/* 各标签指标 */}
          {displayBLMetrics && displayBLMetrics.length > 0 && (
            <div>
              <div className="text-xs font-medium text-slate-500 mb-2">各标签指标</div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="text-left py-2 px-2 text-slate-500 font-medium">标签</th>
                      <th className="text-right py-2 px-2 text-slate-500 font-medium">精确率</th>
                      <th className="text-right py-2 px-2 text-slate-500 font-medium">召回率</th>
                      <th className="text-right py-2 px-2 text-slate-500 font-medium">F1</th>
                      <th className="text-right py-2 px-2 text-slate-500 font-medium">样本数</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayBLMetrics.map((m: any) => (
                      <tr key={m.label} className="border-b border-slate-50 hover:bg-slate-50">
                        <td className="py-2 px-2 text-slate-700 font-medium">{m.label}</td>
                        <td className="py-2 px-2 text-right text-slate-600">{fmtPct(m.precision)}</td>
                        <td className="py-2 px-2 text-right text-slate-600">{fmtPct(m.recall)}</td>
                        <td className="py-2 px-2 text-right text-slate-600">{fmtPct(m.f1)}</td>
                        <td className="py-2 px-2 text-right text-slate-500">{m.support}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* 混淆矩阵 */}
          {displayBLMatrix && Object.keys(displayBLMatrix).length > 0 && (
            <ConfusionMatrix matrix={displayBLMatrix} />
          )}

          {/* 明细表 */}
          {blFiltered.length > 0 && (() => {
            const blDetailFiltered = blFiltered.filter((d: any) => {
              if (baselineResultFilter === 'correct' && !d.match) return false;
              if (baselineResultFilter === 'wrong' && d.match) return false;
              if (baselineLabelFilter !== 'all' && d.annotatedLabel !== baselineLabelFilter) return false;
              return true;
            });
            const blAllLabels = Array.from(new Set(blFiltered.map((d: any) => d.annotatedLabel).filter(Boolean))).sort() as string[];
            const blCorrectCnt = blFiltered.filter((d: any) => d.match).length;
            const blWrongCnt = blFiltered.filter((d: any) => !d.match).length;

            return (
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs font-medium text-slate-500">
                  逐条明细（{blDetailFiltered.length} 条{(baselineResultFilter !== 'all' || baselineLabelFilter !== 'all') ? `，筛选自 ${blFiltered.length} 条` : ''}）
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1">
                    <span className="text-[10px] text-slate-400">结果:</span>
                    {[
                      { key: 'all', label: '全部', count: blFiltered.length },
                      { key: 'correct', label: '✓ 正确', count: blCorrectCnt },
                      { key: 'wrong', label: '✗ 错误', count: blWrongCnt },
                    ].map(opt => (
                      <button key={opt.key} onClick={() => setBaselineResultFilter(opt.key)}
                        className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${baselineResultFilter === opt.key ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
                      >{opt.label}({opt.count})</button>
                    ))}
                  </div>
                  {blAllLabels.length > 1 && (
                    <div className="flex items-center gap-1">
                      <span className="text-[10px] text-slate-400">标签:</span>
                      <select value={baselineLabelFilter} onChange={e => setBaselineLabelFilter(e.target.value)}
                        className="text-[10px] px-1.5 py-0.5 border border-slate-200 rounded bg-white text-slate-600 outline-none">
                        <option value="all">全部标签</option>
                        {blAllLabels.map(l => <option key={l} value={l}>{l}</option>)}
                      </select>
                    </div>
                  )}
                </div>
              </div>
              <div className="max-h-[360px] overflow-y-auto border border-slate-100 rounded-lg">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-slate-50 z-10">
                    <tr className="border-b border-slate-200">
                      <th className="text-left py-2.5 px-3 text-slate-500 font-medium">企业名称</th>
                      <th className="text-left py-2.5 px-3 text-slate-500 font-medium">原模型标签</th>
                      <th className="text-left py-2.5 px-3 text-slate-500 font-medium">人工标注</th>
                      <th className="text-center py-2.5 px-3 text-slate-500 font-medium">结果</th>
                    </tr>
                  </thead>
                  <tbody>
                    {blDetailFiltered.map((d: any) => (
                      <tr key={d.entityKey} className="border-b border-slate-50 hover:bg-slate-50">
                        <td className="py-2 px-3 font-medium max-w-[200px] truncate" title={d.enterpriseName}>
                          {d.runId ? (
                            <button
                              onClick={() => {
                                setDetailRunId(d.runId);
                                setDetailRunPt(d.pt);
                                setDetailFetchFn(undefined);
                              }}
                              className="text-blue-600 hover:text-blue-700 hover:underline text-left"
                            >
                              {d.enterpriseName || d.entityKey}
                            </button>
                          ) : (
                            <span className="text-slate-700">{d.enterpriseName || d.entityKey}</span>
                          )}
                        </td>
                        <td className={`py-2 px-3 ${d.match ? 'text-slate-600' : 'text-red-600 font-medium'}`}>
                          {d.originalLabel ?? '-'}
                        </td>
                        <td className="py-2 px-3 text-slate-700 font-medium">{d.annotatedLabel}</td>
                        <td className="py-2 px-3 text-center">
                          {d.match ? (
                            <span className="inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-50 text-emerald-700">✓ 正确</span>
                          ) : (
                            <span className="inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-50 text-red-600">✗ 错误</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            );
          })()}
        </div>
        );
      })()}

      {/* 进度面板 */}
      {runStatus && <BacktestProgressPanel status={runStatus} />}

      {/* 对比加载 */}
      {compareLoading && (
        <div className="flex items-center justify-center gap-2 py-8 text-sm text-slate-400">
          <Loader2 size={16} className="animate-spin" /> 加载对比结果...
        </div>
      )}

      {/* 对比视图 */}
      {comparison && !compareLoading && (
        <ComparisonView comparison={comparison} onClose={() => setComparison(null)} />
      )}

      {/* 准确率报告 */}
      {report && !comparison && (
        <AccuracyReportPanel report={report} onClickEntity={handleViewResultDetail} />
      )}

      {/* 回溯结果详情面板 */}
      {/* 运行详情 (DetailView) */}
      {detailRunId && (
        <DetailView
          runId={detailRunId}
          onBack={() => setDetailRunId(null)}
          pt={detailRunPt}
          showAnnotation={false}
          fetchDetailFn={detailFetchFn}
        />
      )}

      {/* 历史运行列表 */}
      <HistoryRunList
        runs={historyRuns}
        loading={historyLoading}
        selectedForCompare={selectedForCompare}
        onToggleCompare={handleToggleCompare}
        onCompare={handleCompare}
        onDelete={handleDelete}
        onViewReport={handleViewReport}
      />
    </div>
  );
}
