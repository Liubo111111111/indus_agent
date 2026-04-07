# Industry Classification Dashboard

前端控制台基于 React + Vite，负责展示分类结果、审核 fallback、触发批量任务，以及调用后端 `/api` 接口。

## 本地运行

前置要求：
- Node.js 20+

安装依赖：

```bash
npm install
```

启动开发环境：

```bash
npm run dev
```

类型检查：

```bash
npm run lint
```

生产构建：

```bash
npm run build
```

## 环境变量

- `VITE_API_BASE_URL`: 后端 API 基础路径，默认 `/api`

复制 `.env.example` 为 `.env.local` 或 `.env` 后再按需覆盖。
