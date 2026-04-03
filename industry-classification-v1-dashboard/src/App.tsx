import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  LayoutDashboard,
  GitMerge,
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
  Info,
  Car,
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
  BrainCircuit,
  TerminalSquare,
  Check,
  ChevronDown
} from 'lucide-react';

// --- Taxonomy Data ---
const TAXONOMY_LABELS = [
  { id: 1, name: '汽车租赁', description: '汽车租赁、网约车、货运司机、运力、出行相关企业。', icon: Car, color: 'text-blue-500', bg: 'bg-blue-50' },
  { id: 2, name: '娱乐服务', description: '酒吧、KTV、SPA、足浴、按摩、洗浴、夜场相关企业。', icon: Music, color: 'text-purple-500', bg: 'bg-purple-50' },
  { id: 3, name: '文化传媒', description: '主播、直播、传媒、演艺、广告传播、短视频相关企业。', icon: Video, color: 'text-pink-500', bg: 'bg-pink-50' },
  { id: 4, name: '家政服务', description: '保姆、月嫂、育儿嫂、钟点工、家庭保洁、收纳相关企业。', icon: Home, color: 'text-teal-500', bg: 'bg-teal-50' },
  { id: 5, name: '物业管理', description: '小区、写字楼、园区、商业综合体物业运营，以及与之配套的秩序、保洁、维修相关企业。', icon: Building, color: 'text-indigo-500', bg: 'bg-indigo-50' },
  { id: 6, name: '接单类平台', description: '平台撮合、派单、接单，以及围绕上门维修、安装、保洁、家政网络组织的接单型平台企业。', icon: Smartphone, color: 'text-cyan-500', bg: 'bg-cyan-50' },
  { id: 7, name: '安保服务', description: '保安、护卫、押运、安全保障相关企业。', icon: Shield, color: 'text-slate-700', bg: 'bg-slate-100' },
  { id: 8, name: '建筑类', description: '建筑施工、装修装饰、工程安装、建材配套相关企业。', icon: HardHat, color: 'text-amber-600', bg: 'bg-amber-50' },
  { id: 9, name: '骑手配送', description: '外卖、同城、站点配送、跑腿、骑手运力相关企业。', icon: Bike, color: 'text-orange-500', bg: 'bg-orange-50' },
  { id: 10, name: '餐饮服务', description: '餐馆、饭店、前厅、后厨、厨师、服务员相关企业。', icon: Utensils, color: 'text-red-500', bg: 'bg-red-50' },
  { id: 11, name: '其他', description: '不属于以上10个分类的其他所有企业。', icon: HelpCircle, color: 'text-slate-400', bg: 'bg-slate-50' },
];

// --- Mock Data ---
const STATS = [
  { label: 'Total Processed (24h)', value: '12,450', icon: Database, color: 'text-blue-600', bg: 'bg-blue-100' },
  { label: 'Formal Output (Safe)', value: '11,200', icon: CheckCircle2, color: 'text-emerald-600', bg: 'bg-emerald-100' },
  { label: 'Fallback (Review Needed)', value: '1,250', icon: ShieldAlert, color: 'text-amber-600', bg: 'bg-amber-100' },
  { label: 'Cache Hit Rate', value: '68.5%', icon: Zap, color: 'text-purple-600', bg: 'bg-purple-100' },
];

const RECENT_CLASSIFICATIONS = [
  { id: 'RUN-2039148807937417240', name: '某物业管理有限公司', code: '91330100MA28W12345', industry: '物业管理', confidence: 0.98, status: 'formal', time: '2026/4/2 10:17:45' },
  { id: 'RUN-2039148807937417241', name: '星辰科技有限公司', code: '91440300MA5G188888', industry: '其他', confidence: 0.95, status: 'formal', time: '2026/4/2 10:15:22' },
  { id: 'RUN-2039148807937417242', name: '绿源生态农业', code: '91510100MA6DF99999', industry: '其他', confidence: 0.42, status: 'fallback', time: '2026/4/2 10:08:11', error: 'Low Confidence' },
  { id: 'RUN-2039148807937417243', name: '宏达物流运输', code: '91310000MA1FL77777', industry: '汽车租赁', confidence: 0.88, status: 'formal', time: '2026/4/2 10:02:05' },
  { id: 'RUN-2039148807937417244', name: '未知贸易商行', code: '92320100MA4K966666', industry: '其他', confidence: 0.0, status: 'fallback', time: '2026/4/2 09:55:30', error: 'Parse Error' },
];

const PIPELINE_NODES = [
  { id: 'loader', name: 'Batch Loader', status: 'active' },
  { id: 'static', name: 'Static Profile', status: 'active' },
  { id: 'dynamic', name: 'Dynamic Profile', status: 'active' },
  { id: 'decision', name: 'Final Decision', status: 'active' },
];

const MOCK_RUN_DETAIL = {
  runId: '2039148807937417240',
  status: '已完成',
  confidence: 0.98,
  finalLabel: '物业管理',
  time: '2026/4/2 10:17:45',
  totalTime: '2380ms',
  basicInfo: {
    name: '某物业管理有限公司',
    code: '91330100MA28W12345',
    scope: '物业管理；家政服务；停车场服务；建筑物清洁服务；园林绿化工程施工。'
  },
  flow: [
    { id: 'loader', name: 'Batch Loader', time: '120ms', icon: Database, color: 'bg-blue-500', text: 'text-blue-500' },
    { id: 'static', name: 'Static Profile', time: '850ms', icon: FileText, color: 'bg-indigo-500', text: 'text-indigo-500' },
    { id: 'dynamic', name: 'Dynamic Profile', time: '920ms', icon: Activity, color: 'bg-purple-500', text: 'text-purple-500' },
    { id: 'decision', name: 'Final Decision', time: '450ms', icon: BrainCircuit, color: 'bg-amber-500', text: 'text-amber-500' },
    { id: 'output', name: 'Formal Output', time: '40ms', icon: CheckCircle2, color: 'bg-emerald-500', text: 'text-emerald-500' }
  ],
  staticProfile: {
    keywords: ['物业管理', '家政服务', '建筑物清洁'],
    initialGuess: '物业管理 / 家政服务',
    matchRules: ['SVR-005 物业特征', 'SVR-004 家政特征']
  },
  dynamicProfile: {
    totalJobs: 12,
    topJobs: [
      { name: '保安', count: 5, ratio: '42%' },
      { name: '保洁', count: 4, ratio: '33%' },
      { name: '绿化维护', count: 3, ratio: '25%' }
    ],
    recentSample: '小区秩序维护、日常巡逻、门岗登记'
  },
  cot: [
    "**静态特征分析**: 企业经营范围包含“物业管理”、“建筑物清洁服务”，初步指向【物业管理】或【家政服务】。",
    "**动态特征分析**: 过去90天内发布了12个岗位，其中Top岗位为“保安”(42%)和“保洁”(33%)，近期招聘描述为“小区秩序维护、日常巡逻”。",
    "**综合推理**: 企业不仅有物业管理的资质，且实际正在大量招聘保安、保洁等物业配套岗位，符合【物业管理】行业的典型用工特征。",
    "**置信度评估**: 静态与动态特征高度一致，且样本量充足，置信度极高 (0.98)。"
  ],
  llmCalls: [
    { id: '#1', step: 'Static Profile', model: 'gemini-3.1-pro', tokens: 'P:120 / C:45', latency: '850ms', status: 'success' },
    { id: '#2', step: 'Dynamic Profile', model: 'gemini-3.1-pro', tokens: 'P:340 / C:80', latency: '920ms', status: 'success' },
    { id: '#3', step: 'Final Decision', model: 'gemini-3.1-pro', tokens: 'P:550 / C:120', latency: '450ms', status: 'success' }
  ],
  timeAnalysis: [
    { label: 'dbRead', value: '120ms' },
    { label: 'staticLLM', value: '850ms' },
    { label: 'dynamicLLM', value: '920ms' },
    { label: 'decisionLLM', value: '450ms' },
    { label: 'dbWrite', value: '40ms' },
  ]
};

// --- Components ---

const SidebarItem = ({ icon: Icon, label, active = false, onClick }: { icon: any, label: string, active?: boolean, onClick?: () => void }) => (
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
      {isFormal ? 'Formal' : 'Fallback'}
    </span>
  );
};

// --- Run Detail View Component ---
const RunDetailView = ({ onBack }: { onBack: () => void }) => {
  const run = MOCK_RUN_DETAIL;

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      className="space-y-6 max-w-6xl mx-auto pb-12"
    >
      {/* Header */}
      <div className="flex items-center justify-between bg-white p-4 rounded-2xl border border-slate-200 shadow-sm sticky top-0 z-10">
        <div className="flex items-center gap-4">
          <button 
            onClick={onBack}
            className="flex items-center gap-2 text-blue-600 hover:text-blue-700 font-medium px-3 py-1.5 rounded-lg hover:bg-blue-50 transition-colors"
          >
            <ArrowLeft size={18} />
            返回列表
          </button>
          <div className="w-px h-6 bg-slate-200" />
          <h2 className="text-lg font-bold text-slate-900 flex items-center gap-3">
            运行 #{run.runId}
            <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-700 border border-emerald-200">{run.status}</span>
            <span className="text-emerald-600 font-mono text-sm">{(run.confidence * 100).toFixed(0)}%</span>
            <span className="px-2.5 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700 border border-amber-200">{run.finalLabel}</span>
          </h2>
        </div>
        <div className="text-sm text-slate-400 font-mono">
          {run.time}
        </div>
      </div>

      {/* Basic Info */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
          <h3 className="text-sm font-bold text-slate-800">基本信息</h3>
        </div>
        <div className="p-6 grid grid-cols-2 gap-y-6 gap-x-12">
          <div>
            <div className="text-xs text-slate-500 mb-1">企业名称</div>
            <div className="text-sm font-medium text-slate-900">{run.basicInfo.name}</div>
          </div>
          <div>
            <div className="text-xs text-slate-500 mb-1">统一社会信用代码</div>
            <div className="text-sm font-mono text-slate-900">{run.basicInfo.code}</div>
          </div>
          <div className="col-span-2">
            <div className="text-xs text-slate-500 mb-1">经营范围</div>
            <div className="text-sm text-slate-700 leading-relaxed">{run.basicInfo.scope}</div>
          </div>
        </div>
      </div>

      {/* Pipeline Flow */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
          <h3 className="text-sm font-bold text-slate-800">管道流程</h3>
          <span className="text-xs font-medium text-blue-600">总耗时 {run.totalTime}</span>
        </div>
        <div className="p-8">
          <div className="flex items-center justify-between w-full max-w-4xl mx-auto relative">
            {/* Connecting Line Background */}
            <div className="absolute left-0 right-0 top-6 h-0.5 bg-slate-100 -z-10" />
            
            {run.flow.map((step, i) => (
              <React.Fragment key={step.id}>
                <div className="flex flex-col items-center bg-white px-2">
                  <div className={`w-12 h-12 rounded-full ${step.color} text-white flex items-center justify-center shadow-md shadow-${step.color.split('-')[1]}-500/20 ring-4 ring-white`}>
                    <step.icon size={20} />
                  </div>
                  <span className="text-xs font-bold text-slate-700 mt-3">{step.name}</span>
                  <span className={`text-[10px] font-mono font-medium mt-0.5 ${step.text}`}>{step.time}</span>
                </div>
                {i < run.flow.length - 1 && (
                  <div className="flex-1 h-0.5 bg-gradient-to-r from-slate-200 to-slate-200 mx-2 -z-10" />
                )}
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>

      {/* Profile Results Grid */}
      <div className="grid grid-cols-2 gap-6">
        {/* Static Profile */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
            <h3 className="text-sm font-bold text-slate-800">静态画像结果 (Static Profile)</h3>
          </div>
          <div className="p-6 space-y-4">
            <div>
              <div className="text-xs text-slate-500 mb-2">提取关键词</div>
              <div className="flex flex-wrap gap-2">
                {run.staticProfile.keywords.map(kw => (
                  <span key={kw} className="px-2.5 py-1 bg-indigo-50 text-indigo-700 border border-indigo-100 rounded-md text-xs font-medium">
                    {kw}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500 mb-1">初步推测行业</div>
              <div className="text-sm font-medium text-slate-900">{run.staticProfile.initialGuess}</div>
            </div>
          </div>
        </div>

        {/* Dynamic Profile */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
            <h3 className="text-sm font-bold text-slate-800">动态画像结果 (Dynamic Profile)</h3>
          </div>
          <div className="p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-xs text-slate-500">90天内发布岗位数</div>
              <div className="text-sm font-bold text-slate-900">{run.dynamicProfile.totalJobs}</div>
            </div>
            <div>
              <div className="text-xs text-slate-500 mb-2">Top 岗位分布</div>
              <div className="space-y-2">
                {run.dynamicProfile.topJobs.map(job => (
                  <div key={job.name} className="flex items-center gap-3">
                    <span className="text-sm text-slate-700 w-16">{job.name}</span>
                    <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full bg-purple-500 rounded-full" style={{ width: job.ratio }} />
                    </div>
                    <span className="text-xs font-mono text-slate-500 w-8 text-right">{job.ratio}</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500 mb-1">近期招聘描述样本</div>
              <div className="text-sm text-slate-700 bg-slate-50 p-3 rounded-lg border border-slate-100">
                "{run.dynamicProfile.recentSample}"
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Agent Reasoning */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
          <h3 className="text-sm font-bold text-slate-800">Agent 推理结果 (Final Decision)</h3>
          <div className="flex items-center gap-4 text-sm">
            <span className="text-slate-500">最终决策:</span>
            <span className="px-2.5 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700 border border-blue-200">formalOutput</span>
            <span className="text-slate-500">置信度:</span>
            <span className="font-mono font-bold text-emerald-600">{(run.confidence * 100).toFixed(0)}%</span>
          </div>
        </div>
        <div className="p-6">
          <div className="flex items-center gap-2 mb-4 text-sm font-bold text-slate-800">
            <ChevronDown size={16} className="text-slate-400" />
            推理链 (Chain of Thought)
          </div>
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-3">
            {run.cot.map((step, idx) => {
              const [title, ...rest] = step.split(':');
              return (
                <div key={idx} className="flex gap-3 text-sm">
                  <span className="text-slate-400 font-mono mt-0.5">{idx + 1}.</span>
                  <div className="text-slate-700 leading-relaxed">
                    <strong className="text-slate-900">{title.replace(/\*\*/g, '')}:</strong>
                    {rest.join(':')}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* LLM Calls */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
          <h3 className="text-sm font-bold text-slate-800">模型调用链路 (LLM Calls)</h3>
        </div>
        <div className="p-0">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-white border-b border-slate-100">
                <th className="px-6 py-3 text-xs font-semibold text-slate-500 uppercase">调用节点</th>
                <th className="px-6 py-3 text-xs font-semibold text-slate-500 uppercase">模型</th>
                <th className="px-6 py-3 text-xs font-semibold text-slate-500 uppercase">Tokens (Prompt / Completion)</th>
                <th className="px-6 py-3 text-xs font-semibold text-slate-500 uppercase">耗时</th>
                <th className="px-6 py-3 text-xs font-semibold text-slate-500 uppercase">状态</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {run.llmCalls.map((call) => (
                <tr key={call.id} className="hover:bg-slate-50/50 transition-colors">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <TerminalSquare size={14} className="text-slate-400" />
                      <span className="text-sm font-medium text-slate-800">{call.step}</span>
                      <span className="text-xs text-slate-400 font-mono">{call.id}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-600 font-mono">{call.model}</td>
                  <td className="px-6 py-4 text-sm text-slate-600 font-mono">{call.tokens}</td>
                  <td className="px-6 py-4 text-sm text-slate-600 font-mono">{call.latency}</td>
                  <td className="px-6 py-4">
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-50 text-emerald-600 border border-emerald-100">
                      <Check size={12} /> success
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Time Analysis */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
          <h3 className="text-sm font-bold text-slate-800">耗时分析 (Time Analysis)</h3>
        </div>
        <div className="p-6 flex flex-wrap gap-4">
          {run.timeAnalysis.map((item) => (
            <div key={item.label} className="bg-slate-50 border border-slate-100 rounded-lg px-4 py-3 flex-1 min-w-[120px]">
              <div className="text-xs text-slate-500 mb-1">{item.label}</div>
              <div className="text-sm font-mono font-bold text-slate-900">{item.value}</div>
            </div>
          ))}
          <div className="bg-blue-50 border border-blue-100 rounded-lg px-4 py-3 flex-1 min-w-[120px]">
            <div className="text-xs text-blue-600 mb-1 font-medium">总耗时</div>
            <div className="text-sm font-mono font-bold text-blue-700">{run.totalTime}</div>
          </div>
        </div>
      </div>

    </motion.div>
  );
};

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [selectedRun, setSelectedRun] = useState<any>(null);
  const [isTriggering, setIsTriggering] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const handleTriggerBatch = () => {
    if (isTriggering) return;
    setIsTriggering(true);
    // Simulate API call
    setTimeout(() => {
      setIsTriggering(false);
      showToast('Manual batch triggered successfully!');
    }, 1500);
  };

  const handleRowClick = (item: any) => {
    setSelectedRun(item);
  };

  return (
    <div className="flex h-screen bg-slate-50 font-sans overflow-hidden selection:bg-blue-200 selection:text-blue-900">
      {/* Toast Notification */}
      <AnimatePresence>
        {toastMessage && (
          <motion.div
            initial={{ opacity: 0, y: 50, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            className="fixed bottom-6 right-6 z-50 flex items-center gap-3 bg-slate-900 text-white px-5 py-3 rounded-xl shadow-xl shadow-slate-900/20 border border-slate-800"
          >
            <CheckCircle2 size={18} className="text-emerald-400" />
            <span className="text-sm font-medium">{toastMessage}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <motion.aside 
        initial={{ x: -250 }}
        animate={{ x: 0 }}
        className="w-64 bg-slate-950 text-slate-50 flex flex-col border-r border-slate-800 relative z-20"
      >
        <div className="p-6 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/30">
            <Building2 size={18} className="text-white" />
          </div>
          <span className="font-bold text-lg tracking-tight">IndusClass V1</span>
        </div>
        
        <div className="px-4 py-2 flex-1 space-y-1">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4 px-4 mt-4">Overview</div>
          <SidebarItem icon={LayoutDashboard} label="Dashboard" active={activeTab === 'dashboard' && !selectedRun} onClick={() => { setActiveTab('dashboard'); setSelectedRun(null); }} />
          <SidebarItem icon={GitMerge} label="Pipeline Runs" active={activeTab === 'pipeline' || !!selectedRun} onClick={() => { setActiveTab('pipeline'); setSelectedRun(null); }} />
          <SidebarItem icon={AlertCircle} label="Manual Review" active={activeTab === 'review'} onClick={() => { setActiveTab('review'); setSelectedRun(null); }} />
          
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4 px-4 mt-8">Configuration</div>
          <SidebarItem icon={FileText} label="Taxonomy Config" active={activeTab === 'taxonomy'} onClick={() => { setActiveTab('taxonomy'); setSelectedRun(null); }} />
          <SidebarItem icon={Settings} label="System Settings" active={activeTab === 'settings'} onClick={() => { setActiveTab('settings'); setSelectedRun(null); }} />
        </div>

        <div className="p-4 border-t border-slate-800">
          <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-900 border border-slate-800">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-sm font-medium text-slate-300">System Online</span>
          </div>
        </div>
      </motion.aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden relative z-10">
        {/* Header */}
        <header className="h-20 bg-white/80 backdrop-blur-md border-b border-slate-200 flex items-center justify-between px-8 sticky top-0 z-30">
          <div className="flex items-center gap-4">
            <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
              {selectedRun ? 'Run Details' : 
               activeTab === 'dashboard' ? 'Pipeline Dashboard' :
               activeTab === 'pipeline' ? 'Pipeline Runs' :
               activeTab === 'review' ? 'Manual Review' :
               activeTab === 'taxonomy' ? 'Taxonomy Configuration' :
               'System Settings'}
            </h1>
            <span className="px-2.5 py-1 bg-slate-100 text-slate-600 text-xs font-semibold rounded-md border border-slate-200">v1.0.4</span>
          </div>
          
          <div className="flex items-center gap-6">
            <div className="relative group">
              <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-blue-500 transition-colors" />
              <input 
                type="text" 
                placeholder="Search enterprise by name or code..." 
                className="w-80 pl-10 pr-4 py-2.5 bg-slate-100 border-transparent focus:bg-white focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 rounded-xl text-sm transition-all outline-none"
              />
            </div>
            <button 
              onClick={() => showToast('No new notifications')}
              className="relative p-2 text-slate-400 hover:text-slate-600 transition-colors"
            >
              <Bell size={20} />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border-2 border-white" />
            </button>
            <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-indigo-100 to-blue-100 border border-blue-200 flex items-center justify-center text-blue-700 font-semibold text-sm cursor-pointer hover:shadow-md transition-shadow">
              AD
            </div>
          </div>
        </header>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-8">
          <AnimatePresence mode="wait">
            {selectedRun ? (
              <RunDetailView key="run-detail" onBack={() => setSelectedRun(null)} />
            ) : (
              <motion.div 
                key="main-content"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="max-w-7xl mx-auto space-y-8"
              >
                {activeTab === 'dashboard' || activeTab === 'pipeline' ? (
                  <>
                    {/* Stats Grid */}
                    {activeTab === 'dashboard' && (
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                        {STATS.map((stat, idx) => (
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
                        ))}
                      </div>
                    )}

                    <div className={`grid grid-cols-1 ${activeTab === 'dashboard' ? 'lg:grid-cols-3' : ''} gap-8`}>
                      {/* Recent Classifications Table */}
                      <motion.div 
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.4 }}
                        className={`${activeTab === 'dashboard' ? 'lg:col-span-2' : ''} bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex flex-col`}
                      >
                        <div className="p-6 border-b border-slate-200 flex items-center justify-between bg-white">
                          <div>
                            <h2 className="text-lg font-semibold text-slate-900">
                              {activeTab === 'dashboard' ? 'Recent Classifications' : 'All Pipeline Runs'}
                            </h2>
                            <p className="text-sm text-slate-500 mt-1">Click on any row to view detailed execution trace.</p>
                          </div>
                          {activeTab === 'dashboard' && (
                            <button 
                              onClick={() => setActiveTab('pipeline')}
                              className="text-sm font-medium text-blue-600 hover:text-blue-700 flex items-center gap-1 transition-colors"
                            >
                              View All <ChevronRight size={16} />
                            </button>
                          )}
                        </div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-left border-collapse">
                            <thead>
                              <tr className="bg-slate-50/50 border-b border-slate-200">
                                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Run ID / Enterprise</th>
                                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Industry</th>
                                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Confidence</th>
                                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Status</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {RECENT_CLASSIFICATIONS.map((item) => (
                                <tr key={item.id} className="hover:bg-slate-50/80 transition-colors group cursor-pointer" onClick={() => handleRowClick(item)}>
                                  <td className="px-6 py-4">
                                    <div className="flex flex-col">
                                      <span className="font-medium text-slate-900 group-hover:text-blue-600 transition-colors">{item.name}</span>
                                      <span className="text-xs text-slate-500 font-mono mt-0.5">{item.id}</span>
                                    </div>
                                  </td>
                                  <td className="px-6 py-4">
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-800 border border-slate-200">
                                      {item.industry}
                                    </span>
                                  </td>
                                  <td className="px-6 py-4">
                                    <div className="flex items-center gap-2">
                                      <div className="w-16 h-2 bg-slate-100 rounded-full overflow-hidden">
                                        <div 
                                          className={`h-full rounded-full ${item.confidence > 0.8 ? 'bg-emerald-500' : item.confidence > 0.4 ? 'bg-amber-500' : 'bg-red-500'}`}
                                          style={{ width: `${item.confidence * 100}%` }}
                                        />
                                      </div>
                                      <span className="text-xs font-medium text-slate-600">{(item.confidence * 100).toFixed(0)}%</span>
                                    </div>
                                  </td>
                                  <td className="px-6 py-4">
                                    <div className="flex flex-col items-start gap-1">
                                      <StatusBadge status={item.status} />
                                      {item.error && <span className="text-[10px] text-red-500 font-medium">{item.error}</span>}
                                    </div>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </motion.div>

                      {/* Pipeline Health / Graph Visualizer (Only on Dashboard) */}
                      {activeTab === 'dashboard' && (
                        <motion.div 
                          initial={{ opacity: 0, y: 20 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: 0.5 }}
                          className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 flex flex-col"
                        >
                          <h2 className="text-lg font-semibold text-slate-900 mb-1">Pipeline Health</h2>
                          <p className="text-sm text-slate-500 mb-8">Current LangGraph execution flow.</p>
                          
                          <div className="flex-1 relative">
                            {/* Connecting Line */}
                            <div className="absolute left-[1.1rem] top-4 bottom-4 w-0.5 bg-slate-100" />
                            
                            <div className="space-y-6 relative">
                              {PIPELINE_NODES.map((node, idx) => (
                                <div key={node.id} className="flex items-start gap-4">
                                  <div className="relative z-10 w-9 h-9 rounded-full bg-white border-2 border-blue-500 flex items-center justify-center shadow-sm">
                                    <div className="w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
                                  </div>
                                  <div className="pt-1.5 flex-1">
                                    <h4 className="text-sm font-semibold text-slate-900">{node.name}</h4>
                                    <p className="text-xs text-slate-500 mt-1">
                                      {idx === 0 && "Reading from ODPS Wide Table"}
                                      {idx === 1 && "LLM parsing static features"}
                                      {idx === 2 && "LLM parsing 90-day job stats"}
                                      {idx === 3 && "Synthesizing final label & confidence"}
                                    </p>
                                  </div>
                                  <div className="pt-1.5">
                                    <span className="text-xs font-medium text-emerald-600 bg-emerald-50 px-2 py-1 rounded-md">Healthy</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>

                          <div className="mt-8 pt-6 border-t border-slate-100">
                            <button 
                              onClick={handleTriggerBatch}
                              disabled={isTriggering}
                              className="w-full py-2.5 bg-slate-900 hover:bg-slate-800 disabled:bg-slate-400 text-white text-sm font-medium rounded-xl transition-colors flex items-center justify-center gap-2 shadow-sm"
                            >
                              {isTriggering ? (
                                <>
                                  <Loader2 size={16} className="animate-spin" />
                                  Triggering...
                                </>
                              ) : (
                                <>
                                  <Clock size={16} />
                                  Trigger Manual Batch
                                </>
                              )}
                            </button>
                          </div>
                        </motion.div>
                      )}
                    </div>
                  </>
                ) : activeTab === 'taxonomy' ? (
                  <motion.div 
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="space-y-6"
                  >
                    {/* Taxonomy Header / Background Info */}
                    <div className="bg-white p-8 rounded-2xl border border-slate-200 shadow-sm">
                      <div className="flex items-start gap-4">
                        <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center shrink-0">
                          <BookOpen size={24} className="text-blue-600" />
                        </div>
                        <div>
                          <h2 className="text-xl font-bold text-slate-900 mb-2">需求背景与目标</h2>
                          <p className="text-slate-600 leading-relaxed text-sm mb-4">
                            当前企业行业识别主要依赖企业名称、经营范围等静态信息，但在实际业务中，很多企业名称较泛、经营范围较宽，单靠主体信息无法准确反映企业真实业务方向。与此同时，企业发布的招聘岗位和招聘描述能够体现其实际招聘需求和业务重心，尤其是历史一段时间内的招聘岗位分布与招聘内容，更能反映企业真实在做什么。
                          </p>
                          <div className="bg-slate-50 p-4 rounded-xl border border-slate-100">
                            <h3 className="text-sm font-semibold text-slate-900 mb-2">分类策略：</h3>
                            <ul className="text-sm text-slate-600 space-y-1.5 list-disc list-inside">
                              <li><strong className="text-slate-800">企业名称、经营范围：</strong>主要用于识别企业主体属性。</li>
                              <li><strong className="text-slate-800">招工行为信息：</strong>（历史招聘岗位、招聘描述等）主要用于反映企业实际招聘方向、招聘集中度和招聘频率。</li>
                            </ul>
                            <p className="text-sm text-slate-600 mt-3 font-medium text-blue-700">
                              最终目标：结合企业主体信息与招工行为，将企业准确归类到以下 11 个行业标签中。
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Taxonomy Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                      {TAXONOMY_LABELS.map((label, idx) => (
                        <motion.div
                          initial={{ opacity: 0, y: 20 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: idx * 0.05 }}
                          key={label.id}
                          className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition-all group"
                        >
                          <div className="flex items-center gap-4 mb-4">
                            <div className={`w-12 h-12 rounded-xl ${label.bg} flex items-center justify-center shrink-0 group-hover:scale-110 transition-transform`}>
                              <label.icon size={24} className={label.color} />
                            </div>
                            <div>
                              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">ID: {label.id}</span>
                              <h3 className="text-lg font-bold text-slate-900">{label.name}</h3>
                            </div>
                          </div>
                          <p className="text-sm text-slate-600 leading-relaxed">
                            {label.description}
                          </p>
                        </motion.div>
                      ))}
                    </div>
                  </motion.div>
                ) : (
                  <motion.div 
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="flex flex-col items-center justify-center h-96 bg-white rounded-2xl border border-slate-200 border-dashed"
                  >
                    <div className="w-16 h-16 bg-slate-50 rounded-full flex items-center justify-center mb-4">
                      <Info size={32} className="text-slate-400" />
                    </div>
                    <h2 className="text-xl font-semibold text-slate-900 mb-2">
                      {activeTab === 'review' && 'Manual Review Queue'}
                      {activeTab === 'settings' && 'System Settings'}
                    </h2>
                    <p className="text-slate-500 text-center max-w-md">
                      This module is currently under construction. Check back later for updates to the {activeTab} features.
                    </p>
                    <button 
                      onClick={() => setActiveTab('dashboard')}
                      className="mt-6 px-6 py-2 bg-blue-50 text-blue-600 hover:bg-blue-100 font-medium rounded-lg transition-colors"
                    >
                      Return to Dashboard
                    </button>
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
