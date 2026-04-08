# Industry Classification Pipeline

基于 LangGraph 的企业行业分类流水线，通过多阶段 LLM 推理将企业归类到 11 个行业标签之一。

## 业务背景

企业行业识别传统上依赖企业名称和经营范围等静态信息，但很多企业名称泛化、经营范围宽泛，单靠主体信息无法准确反映真实业务方向。本项目在静态信息基础上引入近 90 天招聘行为数据，综合判断企业所属行业。

## 行业标签（11 类）

| ID | 标签 | 说明 |
|---|---|---|
| ride_hailing | 网约车 | 网约车司机、商务车司机、代驾、出行服务 |
| freight_logistics | 货运物流 | C照货车司机、物流类公司、道路货物运输、运力调度 |
| entertainment_services | 娱乐服务 | 酒吧、KTV、SPA、足浴、按摩、洗浴、夜场 |
| cultural_media | 文化传媒 | 主播、直播、传媒、演艺、广告传播、短视频 |
| domestic_services | 家政服务 | 保姆、月嫂、育儿嫂、钟点工、家庭保洁、收纳 |
| property_management | 物业管理 | 小区、写字楼、园区物业运营及配套秩序保洁维修 |
| order_taking_platform | 接单类平台 | 平台撮合、派单、上门维修安装保洁家政 |
| security_services | 安保服务 | 保安、护卫、押运、安全保障 |
| construction | 建筑类 | 建筑施工、装修装饰、工程安装、建材配套 |
| delivery_riders | 骑手配送 | 外卖、同城、站点配送、跑腿、骑手运力 |
| catering_services | 餐饮服务 | 餐馆、饭店、前厅、后厨、厨师、服务员 |
| other | 其他 | 证据不足或无法明确归类 |

## 架构概览

```
ODPS Wide Table (SQL)
       │
       ▼
 ┌─────────────┐
 │ Batch Loader │  ← JSON / JSONL 输入
 └──────┬──────┘
        ▼
 ┌──────────────────┐
 │ GraphState Builder│  ← Pydantic 模型，版本化状态
 └──────┬───────────┘
        ▼
 ┌──────────────────┐
 │  Static Profile   │  ← 企业名称 + 经营范围 → LLM → top3 候选行业
 └──────┬───────────┘
        ▼
 ┌──────────────────┐
 │ Dynamic Profile   │  ← 招聘统计 + 近期样本 → LLM → 招聘画像
 └──────┬───────────┘
        ▼
 ┌──────────────────┐
 │ Final Decision    │  ← 静态 + 动态画像 → LLM → 11 选 1 裁决
 └──────┬───────────┘
        │
   ┌────┴────┐
   ▼         ▼
┌────────┐ ┌──────────┐
│ Formal │ │ Fallback │  ← 高置信 → 正式输出；低置信/错误 → 审核通道
│ Output │ │  Output  │
└────────┘ └──────────┘
```

每次运行附带：审计元数据、版本感知缓存、Prompt 预算控制、共享 LLM 结果处理器。

## 项目结构

```
├── backend/                              # Python 后端工程
│   ├── src/industry_classification/      # 后端应用源码
│   ├── tests/                            # 后端单元/集成测试
│   ├── scripts/                          # 后端运维脚本
│   ├── sql/                              # 后端相关 SQL
│   ├── output/                           # 后端运行输出
│   ├── pyproject.toml
│   └── .env.example
├── frontend/                             # React + Vite 前端控制台
│   ├── src/
│   │   ├── api/                         # 前端 API client 与类型定义
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
├── docs/
│   ├── backlog/                         # 待办与后续治理事项
│   ├── context/                         # 业务背景、构想、参考资料
│   ├── plans/
│   ├── requirements/
│   └── runbooks/
```

## 环境要求

- Python >= 3.11
- 依赖：pydantic >= 2.8, PyYAML >= 6.0, langgraph >= 0.2

## 安装

```bash
# 克隆项目
git clone <repo-url>
cd industry-classification

# 安装后端
cd backend
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 安装项目（含开发依赖）
pip install -e ".[dev]"
```

### 前端安装

```bash
cd ..
cd frontend
npm install
```

## 统一入口

仓库根目录提供统一命令入口，默认从根目录执行：

```bash
# 后端 API 开发
npm run dev:backend

# 后端测试
npm run test:backend
npm run test:backend:unit
npm run test:backend:integration

# 后端 dry-run
npm run dry-run:backend

# 前端开发/检查/构建
npm run dev:frontend
npm run lint:frontend
npm run build:frontend
```

说明：
- 后端命令会自动切到 `backend/` 执行
- 会优先使用 `backend/.venv`，其次回退到仓库根 `.venv`

## 环境配置

复制 `backend/.env.example` 为 `backend/.env`，填入实际密钥：

```bash
cp backend/.env.example backend/.env
```

配置项说明：

| 变量 | 必填 | 说明 |
|---|---|---|
| `DASHSCOPE_API_KEY` | 是（三选一） | 通义千问 API Key |
| `OPENAI_API_KEY` | 是（三选一） | OpenAI 兼容 API Key |
| `LLM_API_KEY` | 是（三选一） | 通用 LLM API Key |
| `LLM_BASE_URL` | 否 | LLM 接口地址 |
| `LLM_MODEL` | 否 | 模型名称，默认 `qwen3-max` |
| `LLM_TIMEOUT_SEC` | 否 | 单次调用超时，默认 30 秒 |
| `LLM_MAX_RETRY` | 否 | 最大重试次数，默认 2 |
| `ODPS_ACCESS_KEY_ID` | 是 | MaxCompute AccessKey ID |
| `ODPS_ACCESS_KEY_SECRET` | 是 | MaxCompute AccessKey Secret |
| `ODPS_PROJECT` | 是 | MaxCompute 项目名 |
| `ODPS_ENDPOINT` | 是 | MaxCompute 服务端点 |
| `FEISHU_WEBHOOK` | 否 | 飞书告警 Webhook 地址 |

## 使用方式

### Dry-Run 模式

使用内置样本数据验证流水线：

```bash
npm run dry-run:backend
```

等价原生命令：

```bash
cd backend
python -m industry_classification.main --pt 20260402 --mode dry-run
```

### Fetch 模式（从 ODPS 拉取数据）

从 `yuapo_dev.enterprise_industry_wide_table` 拉取宽表数据，自动转换为 JSON：

```bash
# 拉取数据并转为 JSON
python -m industry_classification.main --pt 20260402 --mode fetch --output-dir output/data/

# 限制条数（调试用）
python -m industry_classification.main --pt 20260402 --mode fetch --max-rows 100

# 输出 JSONL 格式
python -m industry_classification.main --pt 20260402 --mode fetch --format jsonl
```

### Fetch-Run 模式（拉取 + 分类一站式）

自动完成：ODPS 拉取 → CSV → JSON → LLM 分类 → 输出结果：

```bash
python -m industry_classification.main \
  --pt 20260402 \
  --mode fetch-run \
  --output-dir output/ \
  --max-rows 50 \
  --worker-count 4 \
  --provider-rate-limit-per-minute 60
```

### Run / Run-Single 模式（使用真实 LLM）

对已有的 JSON/JSONL 数据文件运行分类：

```bash
# 单条测试
python -m industry_classification.main --pt 20260402 --mode run-single --input-path output/data/wide_table_20260402.json

# 批量运行
python -m industry_classification.main --pt 20260402 --mode run --input-path output/data/wide_table_20260402.json
```

### File-Batch 模式（Mock 响应）

批量处理企业数据：

```bash
python -m industry_classification.main \
  --pt 20260402 \
  --mode file-batch \
  --input-path output/data/enterprises.json \
  --responses-path output/data/mock_responses.json \
  --output-dir output/ \
  --worker-count 4 \
  --provider-rate-limit-per-minute 120 \
  --max-in-flight 8 \
  --timeout-seconds 30 \
  --retry-limit 1
```

### 运行时参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--pt` | 必填 | 业务日期分区（yyyymmdd） |
| `--mode` | 必填 | `dry-run` / `fetch` / `fetch-run` / `run` / `run-single` / `file-batch` |
| `--format` | json | 数据输出格式（`json` 或 `jsonl`，fetch 模式用） |
| `--max-rows` | 无限制 | ODPS 最大拉取条数（fetch 模式用） |
| `--worker-count` | 4 | 并发工作线程数 |
| `--provider-rate-limit-per-minute` | 120 | LLM 调用限流（次/分钟） |
| `--max-in-flight` | 8 | 最大并发任务数 |
| `--timeout-seconds` | 30 | 单任务超时（秒） |
| `--retry-limit` | 1 | 失败重试次数 |

## 输出说明

### Formal Output（正式输出）

高置信度裁决结果，包含：
- `final_label`：行业标签
- `confidence_level`：置信度等级（high / medium / low）
- `decision_reason`：裁决原因
- `supporting_evidence`：支持证据列表
- `audit`：完整审计元数据（run_id、版本信息、路由结果）

### Fallback Output（兜底输出）

低置信度或错误结果，进入人工审核通道，包含：
- `decision_record`：裁决记录（如有）
- `error_type`：错误类型（如有）
- `audit`：完整审计元数据

## 测试

```bash
# 运行全部测试
npm run test:backend

# 仅单元测试
npm run test:backend:unit

# 仅集成测试
npm run test:backend:integration
```

等价原生命令：

```bash
cd backend
pytest -q

# 运行特定测试
pytest -k "test_graph_routing" -q
```

### 前端开发与验证

```bash
# 启动前端开发服务
npm run dev:frontend

# 前端类型检查
npm run lint:frontend

# 前端生产构建
npm run build:frontend
```

## 核心设计决策

1. **三阶段 LLM 推理**：静态画像 → 动态画像 → 最终裁决，逐步收敛判断
2. **版本化状态**：GraphState 记录 taxonomy、prompt、model 版本，确保可复现
3. **双通道输出**：高置信走正式通道，低置信/错误走兜底审核通道
4. **Prompt 预算控制**：限制发送给 LLM 的数据量，防止 raw 90 天数据泄漏到最终裁决
5. **版本感知缓存**：缓存键包含所有版本维度，版本变更自动失效
6. **幂等重跑**：相同输入 + 相同版本 = 命中缓存，不重复发布

## 数据输入格式

每条企业数据（WideRow）包含：

```json
{
  "user_id": 1,
  "social_credit_code": "91110000MA...",
  "enterprise_name": "某某物业管理有限公司",
  "business_scope": "物业管理、保洁服务、园林绿化",
  "total_job_post_cnt_90d": 45,
  "distinct_job_name_cnt_90d": 6,
  "top_job_names": [
    {"job_name": "保安", "cnt": 15, "ratio": 0.33},
    {"job_name": "保洁", "cnt": 12, "ratio": 0.27}
  ],
  "jobs_recent_20": [
    {"job_name": "保安", "desc": "小区秩序维护", "add_time": "2026-04-01 10:00:00"}
  ]
}
```

## License

Private / Internal Use
