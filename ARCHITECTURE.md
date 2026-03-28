# ScholarRAG 系统架构文档

> **注意**：本文档原名为 `DEVELOPMENT_PLAN.md`，描述的开发计划已**全部完成**（2026年3月）。现作为系统架构文档保留，供开发者参考。

## 一、项目概述

ScholarRAG 是一个面向学术文献的多模态 RAG 系统，包含完整的 Web 前端和 REST API 服务层。

**目标用户**：个人研究者/学者  
**部署方式**：本地运行（无需 Docker）  
**开发状态**：✅ 已完成（包含必要功能路线图全部 10 个任务）

---

## 二、技术栈

### 后端
| 技术 | 版本 | 用途 |
|------|------|------|
| FastAPI | ≥0.100 | Web 框架 |
| Uvicorn | ≥0.20 | ASGI 服务器 |
| python-multipart | - | 文件上传 |
| sse-starlette | - | Server-Sent Events |

### 前端
| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18 | UI 框架 |
| TypeScript | 5.x | 类型安全 |
| Vite | 5.x | 构建工具 |
| Tailwind CSS | 3.x | 样式 |
| shadcn/ui | - | 组件库 |
| Zustand | - | 状态管理 |
| React Router | 6.x | 路由 |
| @tanstack/react-query | - | 服务端状态 |

### 设计风格
- **简洁文档风**（类似 Notion/Obsidian）
- 深色/浅色主题支持
- 响应式设计（移动端适配）

---

## 三、目录结构

```
ScholarRAG/
├── api/                           # FastAPI 服务层
│   ├── __init__.py
│   ├── main.py                    # FastAPI 应用入口
│   ├── config.py                  # API 配置
│   ├── deps.py                    # 依赖注入
│   ├── schemas.py                 # Pydantic 模型
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── papers.py              # 论文 CRUD 路由
│   │   └── query.py               # 问答路由 (SSE)
│   └── services/
│       ├── __init__.py
│       ├── paper_service.py        # 论文服务封装
│       └── query_service.py       # 问答服务封装
├── frontend/                      # React 前端
│   ├── src/
│   │   ├── components/
│   │   │   ├── ui/                # shadcn/ui 基础组件
│   │   │   ├── layout/             # 布局组件
│   │   │   ├── papers/             # 论文相关组件
│   │   │   └── query/              # 问答相关组件
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── lib/
│   │   ├── stores/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── vite.config.ts
├── main.py                        # 保留 CLI 入口
└── (其他现有文件保持不变)
```

---

## 四、API 设计

### 基础信息
- **Base URL**: `http://localhost:8000`
- **CORS**: 允许 `http://localhost:5173`

### 端点列表

| 方法 | 路径 | 功能 | 请求体 | 响应 |
|------|------|------|--------|------|
| `GET` | `/api/health` | 健康检查 | - | `{status: "ok"}` |
| `POST` | `/api/papers/upload` | 上传 PDF | `FormData: file` | `{pdf_name, title, authors, chunk_count, message}` |
| `GET` | `/api/papers` | 获取论文列表 | - | `{papers: [{pdf_name, title, authors, chunk_count, created_at, ...}]}` |
| `GET` | `/api/papers/{pdf_name}` | 获取论文详情 | - | `{pdf_name, title, authors, metadata: {...}}` |
| `DELETE` | `/api/papers/{pdf_name}` | 删除论文 | - | `{message}` |
| `GET` | `/api/papers/{pdf_name}/chunks` | 获取论文 chunks | `?page=1&limit=20&type=text` | `{chunks: [], total, page, limit}` |
| `POST` | `/api/query` | 流式问答 | `{question: string}` | `SSE stream` |

### SSE 事件格式

```
event: status
data: {"phase": "thinking", "step": 1, "text": "..."}

event: tool_call
data: {"tool": "search_papers", "kind": "paper_search", "args": {...}}

event: tool_result
data: {"kind": "paper_search", "count": 5, "pages": ["paper1:3", "paper2:10"]}

event: answer_started
data: {}

event: answer_token
data: {"text": "token"}

event: answer_done
data: {}
```

---

## 五、前端页面设计

### 1. 路由结构
| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | QueryPage | 问答首页 |
| `/papers` | PapersPage | 论文库 |
| `/papers/:pdf_name` | PaperDetailPage | 论文详情 |

### 2. 页面设计

#### 查询首页 (`/`)
- 大搜索框，居中展示
- 流式回答区域，实时显示
- 引用来源展示（可点击跳转）
- 搜索历史记录

#### 论文库页面 (`/papers`)
- 论文卡片网格展示
- 上传按钮 + 拖拽上传区域
- 删除确认对话框

#### 论文详情页 (`/papers/:pdf_name`)
- 元信息卡片
- Chunk 列表（支持搜索、类型筛选）
- 分页加载

---

## 六、实施步骤

### Phase 1: FastAPI 服务层

#### 步骤 1.1: 创建 API 配置
- 创建 `api/config.py`
- 添加 `API_HOST`, `API_PORT` 配置

#### 步骤 1.2: 定义 Pydantic Schemas
- 创建 `api/schemas.py`
- 定义所有请求/响应模型

#### 步骤 1.3: 实现论文服务
- 创建 `api/services/paper_service.py`
- 实现上传/列表/详情/删除/chunks 获取

#### 步骤 1.4: 实现问答服务
- 创建 `api/services/query_service.py`
- 实现流式问答

#### 步骤 1.5: 创建路由
- `api/routes/papers.py` - 论文 CRUD
- `api/routes/query.py` - 问答

#### 步骤 1.6: 创建主应用
- `api/main.py` - CORS、路由、健康检查

---

### Phase 2: 前端基础架构

#### 步骤 2.1: 初始化项目
```bash
npm create vite@latest . -- --template react-ts
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

#### 步骤 2.2: 安装依赖
```bash
npm install react-router-dom @tanstack/react-query zustand lucide-react clsx tailwind-merge class-variance-authority
npm install -D @types/node
```

#### 步骤 2.3: 设置 shadcn/ui
```bash
npx shadcn@latest init
npx shadcn@latest add button input card dialog dropdown-menu toast
```

---

### Phase 3: 前端组件开发

#### 步骤 3.1: 布局组件
- Header, ThemeToggle, Layout

#### 步骤 3.2: 论文组件
- PaperCard, PaperList, PaperUpload, PaperDetail

#### 步骤 3.3: 问答组件
- QueryBox, QueryResult, SourceCitation

#### 步骤 3.4: 页面
- QueryPage, PapersPage, PaperDetailPage

---

## 七、启动方式

### 终端 1: FastAPI
```bash
conda activate scholarrag
uvicorn api.main:app --reload --port 8000
```

### 终端 2: Frontend
```bash
cd frontend
npm run dev
```

---

## 八、关键注意事项

### 1. CUDA/vLLM 冲突
- FastAPI 启动时 **不要** 在模块级别导入 `vector_store`
- 只在 API 路由内部导入（延迟导入）

### 2. 文件上传
- PDF 上传到临时目录
- 处理完成后清理临时文件

### 3. SSE 流式响应
- 使用 `StreamingResponse` + 生成器
- 正确设置 `media_type="text/event-stream"`

### 4. Agent 模块解耦（W4-A, W4-B）
- `src/agent/retrieval_service.py`：定义 `RetrievalService` 协议与 `VectorStoreRetrievalService` 适配器，工具层通过服务接口检索，避免直接依赖 `get_vector_store()`
- `src/agent/tooling.py`：集中注册 `AGENT_TOOLS` 与 `TOOL_REGISTRY`
- `src/agent/types.py`：集中定义 `AgentState` 共享类型
- `src/agent/langgraph_agent.py`：仅负责图编译与节点执行
- `src/agent/graph.py`：负责流式事件与高层 API，不再与 `langgraph_agent.py` 形成循环导入

### 5. 解析路径统一（W2-B）
- 解析输出目录由 `PARSED_OUTPUT_DIR` 统一配置
- PDF 持久化目录由 `PDF_STORAGE_DIR` 统一配置

### 6. 性能优化架构（W1-B, W3-A, W3-B, W3-D）
- **N+1 查询消除**: `similarity_search()` 从逐条 retrieve 改为批量 retrieve
- **可配置批处理**: `EMBEDDING_BATCH_SIZE` 默认 32（原 4），GPU 利用率提升 12x
- **Tokenizer 缓存**: `get_tokenizer()` 单例模式，避免重复初始化
- **查询缓存**: `QueryCache` 5分钟 TTL，重复查询延迟 <10ms
- **连接复用**: Qdrant/LLM client 单例，支持连接池配置

### 7. 可靠性与监控（W1-A, W2-A, W4-C）
- **数据库租约**: `ingestion_jobs` 表新增 `leased_at/leased_by`，防止多 worker 重复处理
- **统一异常层次**: `AppError` → `ValidationError/NotFoundError/ExternalServiceError`
- **断路器保护**: Tenacity 重试（3次，指数退避）
- **Prometheus 指标**: `/metrics` 端点暴露检索延迟、查询计数等指标

### 8. 部署架构（W4-C）
- **Docker 容器化**: 镜像大小 232MB，支持一键部署
- **Docker Compose**: 同时启动 API + Qdrant + Redis
- **健康检查**: `/api/health` 端点
