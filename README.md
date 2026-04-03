# ScholarRAG

> 面向学术文献的多模态检索增强生成（RAG）系统

ScholarRAG 是一个专为学术研究者设计的**多模态 RAG 系统**。它不仅能理解和检索论文文本，还能解析**复杂的表格、图表和数学公式**，为研究者提供深度、智能的文献交互体验。

---

## 🌟 核心特性

### 🤖 智能代理引擎
- **LangGraph 驱动**：基于状态机的健壮代理架构，能够自主规划研究步骤、执行工具调用、综合研究结果
- **多模态推理**：代理可以"看见"并分析论文中的视觉证据（图表/表格），提供更全面的答案
- **动态工具链**：包含语义搜索、视觉检索、页面上下文扩展等多种工具

### 📄 智能 PDF 解析
- **MinerU 集成**：高精度学术 PDF 解析，提取文本、图片和公式交叉引用
- **统一服务层**：集中的摄取管道，确保 CLI 和 Web 接口的一致性处理

### 🔍 多模态嵌入与检索
- **Qwen3-VL 嵌入**：基于 Qwen3-VL 的多模态嵌入模型，支持文本、图像混合输入
- **LangChain 兼容**：实现 `langchain_core.embeddings.Embeddings` 接口，无缝集成
- **混合检索**：支持稠密向量 + 稀疏 BM25 检索（可选，需设置 `ENABLE_HYBRID=true`）

### 💻 现代化 Web 界面
- **沉浸式聊天**：全屏专注模式，支持 LaTeX 公式渲染（KaTeX）
- **思维过程可视化**：可折叠的推理过程展示，实时观察代理的研究步骤
- **丰富的引用**：每个回答都附带来源论文和具体页码链接
- **PDF 阅读器集成**：内置 PDF 查看器，支持直接跳转到引用页面

### ⚡ 性能优化
- **VRAM 优化**：使用 `bfloat16`/`float16` 精度加载模型，显存占用降低约 **50%**
- **线程安全的存储库模式**：通过 `get_vector_store()` 延迟初始化单例，隔离业务逻辑与 Qdrant 向量数据库，并支持并发访问
- **异步支持**：内置异步方法，实现非阻塞操作

### 🛡️ 安全与稳定性
- **通用错误消息**：对外返回简洁错误信息，内部保留详细日志，避免暴露实现细节

### 📊 版本管理
- **自动版本控制**：重新索引论文时自动创建新版本，保留历史记录
- **当前版本过滤**：默认只检索当前版本的 chunks，避免历史版本干扰
- **版本历史查看**：前端界面展示所有版本，支持查看历史版本详情

### ⚡ 异步上传与任务管理
- **异步处理**：大文件上传不阻塞，立即返回任务 ID
- **实时进度**：通过轮询获取处理进度（解析、嵌入、存储）
- **任务重试**：失败任务支持一键重试，自动清理后重新处理
- **持久化状态**：所有任务状态保存在 SQLite，重启后不会丢失
- **数据库租约防重入**：支持基于 `ingestion_jobs.status + leased_at + leased_by` 的租约锁，避免多 worker 重复处理同一任务
- **可配置执行器**：后台任务执行器可在线程池/进程池间切换，CPU 密集型 PDF 解析可用进程池并行

### 🧪 离线评估流水线
- **6 种评估指标**：检索命中率、页面命中率、关键词匹配率、引用覆盖率、版本泄漏率、失败查询率
- **阈值门禁**：可配置指标阈值，未通过时 CI 自动失败
- **JSON 报告**：生成机器可读的评估报告，支持历史对比

---

## 🏗️ 系统架构

```
ScholarRAG/
├── main.py                    # CLI 入口（add/query/delete 子命令）
├── api/                       # FastAPI 后端
│   ├── main.py               # 应用工厂、CORS、路由挂载
│   ├── config.py             # API 配置（主机、端口、上传目录）
│   ├── schemas.py              # Pydantic 请求/响应模型
│   ├── routes/                # 端点处理器
│   │   ├── papers.py         # 论文管理接口
│   │   ├── query.py            # 查询接口
│   │   └── conversations.py    # 对话历史接口
│   └── services/              # 业务逻辑层
│       ├── paper_service.py    # 论文服务
│       ├── query_service.py    # 查询服务
│       └── conversation_service.py
├── frontend/                  # React + TypeScript SPA
│   ├── src/
│   │   ├── components/        # 可复用 UI 组件
│   │   ├── pages/             # 路由级视图
│   │   ├── hooks/             # 自定义 React Hooks
│   │   ├── stores/            # Zustand 状态管理
│   │   └── lib/               # 工具函数
│   └── package.json
├── config/
│   └── settings.py            # 配置数据类，读取 .env
├── src/
│   ├── core/                  # 共享业务逻辑
│   │   └── ingestion.py       # 摄取服务
│   ├── agent/                 # LangGraph 智能体
│   │   ├── graph.py           # 状态机定义
│   │   ├── tools.py           # 工具定义
│   │   ├── langgraph_agent.py # 代理实现
│   │   └── multimodal_answerer.py
│   ├── custom/                # Qwen3-VL 模型封装
│   │   ├── qwen3_vl_embedding.py
│   │   └── vision_utils.py
│   ├── ingest/                # MinerU 解析器
│   │   ├── mineru_parser.py
│   │   └── paper_manager.py
│   ├── rag/                   # 向量存储与检索
│   │   ├── vector_store.py    # Qdrant 多模态存储
│   │   └── embedding.py
│   ├── utils/
│   │   └── logger.py          # 日志工具
│   └── jobs/                  # 任务与版本管理
│       ├── job_manager.py     # 异步任务管理
│       └── version_manager.py # 版本控制管理
├── tests/
│   └── evaluation/           # 离线评估流水线
│       ├── runner.py
│       ├── dataset.json
│       └── thresholds.json
├── data/                      # 数据目录（gitignored）
│   ├── parsed/               # MinerU 输出目录
│   ├── uploads/              # 上传文件临时目录
│   └── scholarrag.db         # SQLite 数据库（任务/版本持久化）
└── .github/workflows/        # GitHub Actions CI/CD
```

---

## 🚀 快速开始

### 环境要求

- **Python**: 3.12+
- **Node.js**: 18+（前端开发）
- **Qdrant**: 本地或云端向量数据库
- **GPU**: NVIDIA GPU（推荐 RTX 2080 Ti 或更高）

### 1. 克隆与安装

```bash
# 克隆仓库
git clone <repository-url>
cd ScholarRAG

# 创建 Python 环境
conda create -n scholarrag python=3.12
conda activate scholarrag

# 安装依赖
pip install -r requirements.txt

# 安装 MinerU（PDF 解析器）
pip install -U mineru[all]

# 下载 Qwen3-VL-Embedding-2B 嵌入模型（约 4GB）
# 方式一：使用 git-lfs 从 HuggingFace 下载
mkdir -p models
cd models
git lfs install
git clone https://huggingface.co/Qwen/Qwen3-VL-Embedding-2B
cd ..

# 方式二：使用 modelscope 下载（国内推荐）
# pip install modelscope
# mkdir -p models
# python -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen3-VL-Embedding-2B', cache_dir='models', local_dir='models/Qwen3-VL-Embedding-2B')"

# 方式三：使用 HuggingFace 镜像
# export HF_ENDPOINT=https://hf-mirror.com
# huggingface-cli download Qwen/Qwen3-VL-Embedding-2B --local-dir models/Qwen3-VL-Embedding-2B
```

### 2. 配置环境

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑 .env 文件，配置以下关键项：
# - OPENAI_API_KEY: 你的 OpenAI API 密钥
# - OPENAI_API_BASE: API 基础地址（默认: http://localhost:8000/v1）
# - EMBEDDING_MODEL: Qwen3-VL 嵌入模型路径
# - QDRANT_HOST, QDRANT_PORT: Qdrant 服务地址
# - QDRANT_COLLECTION_NAME: Qdrant 集合名（默认: scholarrag）
# - LLM_MODEL: 语言模型名称（默认: Pro/moonshotai/Kimi-K2.5）
```

### 3. 启动服务

**方式一：命令行（CLI）**

```bash
# 添加论文到向量库
python main.py add path/to/paper.pdf

# 查询论文
python main.py query "这篇论文的核心方法是什么？"

# 删除论文
python main.py delete paper_name
```

**方式二：Web 服务**

```bash
# 启动后端（终端 1）
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 启动前端（终端 2）
cd frontend
npm install
npm run dev

# 访问 http://localhost:5173
```

### 4. Docker 部署

```bash
docker build -t scholarrag .
docker compose up -d

# 健康检查
curl http://localhost:8000/api/health

# Prometheus 指标
curl http://localhost:8000/metrics
```

容器编排会同时拉起：
- `api`（FastAPI）
- `qdrant`（向量数据库）

`.dockerignore` 已默认排除 `data/`、`models/`、`qdrant_storage/` 等大目录以减少镜像体积。

---

## 📖 使用指南

### CLI 命令

| 命令 | 描述 | 示例 |
|------|------|------|
| `add <pdf_path>` | 摄取 PDF 到向量库 | `python main.py add ./papers/dream.pdf` |
| `query <question>` | 向 RAG 代理提问 | `python main.py query "什么是 DREAM 方法的核心思想？"` |
| `delete <pdf_name>` | 删除论文 | `python main.py delete dream` |

### API 端点

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/api/papers/uploads` | 异步上传 PDF |
| GET | `/api/papers/uploads` | 获取上传任务列表 |
| GET | `/api/papers/uploads/{job_id}` | 获取任务详情 |
| POST | `/api/papers/uploads/{job_id}/retry` | 重试失败任务 |
| GET | `/api/papers` | 列出所有论文 |
| GET | `/api/papers/{pdf_name}/versions` | 获取论文版本列表 |
| POST | `/api/papers/{pdf_name}/reindex` | 重新索引论文 |
| DELETE | `/api/papers/{name}` | 删除论文 |
| POST | `/api/query/stream` | 流式查询（SSE） |
| GET | `/api/conversations` | 获取对话历史 |
| DELETE | `/api/conversations/{id}` | 删除对话 |

### 环境变量配置

| 变量 | 描述 | 默认值 |
|------|------|--------|
| `OPENAI_API_BASE` | OpenAI 兼容 API 地址 | `http://localhost:8000/v1` |
| `OPENAI_API_KEY` | API 密钥 | `""` |
| `LLM_MODEL` | 语言模型名称 | `Pro/moonshotai/Kimi-K2.5` |
| `EMBEDDING_MODEL` | 嵌入模型路径 | `models/Qwen3-VL-Embedding-2B` |
| `QDRANT_HOST` | Qdrant 主机 | `localhost` |
| `QDRANT_PORT` | Qdrant 端口 | `6333` |
| `QDRANT_COLLECTION_NAME` | Qdrant 集合名 | `scholarrag` |
| `RAG_TOP_K` | 检索 top-k | `5` |
| `SCORE_THRESHOLD` | 相似度阈值 | `0.3` |
| `AGENT_MAX_ITERATIONS` | 代理最大迭代次数 | `10` |
| `ENABLE_HYBRID` | 启用混合检索 | `false` |
| `MINERU_BACKEND` | MinerU 后端 | `pipeline` |
| `PDF_STORAGE_DIR` | PDF 文件存储目录 | `./data/pdfs` |
| `PARSED_OUTPUT_DIR` | MinerU 解析输出目录 | `./data/parsed` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `LOG_FORMAT` | 日志格式模板 | `%(asctime)s - %(name)s - %(levelname)s - %(message)s` |
| `USE_DB_JOB_LEASE` | 启用数据库任务租约（false 时保持旧 guard 逻辑） | `false` |
| `JOB_LEASE_TTL_SECONDS` | 任务租约过期秒数（过期后可被其他 worker 接管） | `300` |
| `EXECUTOR_TYPE` | 后台执行器类型（`thread`/`process`） | `thread` |
| `BACKGROUND_EXECUTOR_WORKERS` | 后台执行器并行 worker 数 | `2` |

---

## 🛠️ 技术栈

### AI/ML
- [LangGraph](https://github.com/langchain-ai/langgraph) - 智能体编排框架
- [LangChain](https://github.com/langchain-ai/langchain) - LLM 应用框架
- [Qwen3-VL](https://github.com/QwenLM/Qwen-VL) - 多模态视觉语言模型
- [Transformers](https://github.com/huggingface/transformers) - 预训练模型库
- PyTorch - 深度学习框架

### 数据库与存储
- [Qdrant](https://qdrant.tech/) - 向量数据库
- [SQLite](https://sqlite.org/) - 任务队列与版本持久化

### 后端
- FastAPI - 高性能 Web 框架
- Pydantic v2 - 数据验证
- Prometheus Client - 指标暴露
- Tenacity - 外部调用重试/熔断保护

### 前端
- React 19 - UI 框架
- TypeScript - 类型安全
- Tailwind CSS - 样式框架
- shadcn/ui - UI 组件库
- KaTeX - LaTeX 公式渲染
- Zustand - 状态管理

### PDF 解析
- [MinerU](https://github.com/opendatalab/MinerU) - 高质量 PDF 解析工具

---

## 🔄 CI/CD

项目使用 GitHub Actions 进行持续集成：

```yaml
# .github/workflows/ci.yml
- 后端代码检查 (ruff + bandit)
- 后端测试 (pytest with coverage, 阈值 35%)
- 评估流水线 (evaluation runner, non-blocking)
- 前端代码检查 (npm run lint)
- 前端构建 (npm run build)
```

每次提交到 main 分支或创建 PR 时自动运行。

**注意：** 
- 前端 CI 当前不包含自动化测试（尚未配置测试框架）
- 评估流水线配置为 `continue-on-error: true`，失败不会阻断构建
- 测试覆盖率阈值当前设置为 35%，可根据需要调整

---

## 🧪 评估

### 运行离线评估

```bash
python -m tests.evaluation.runner \
  --dataset tests/evaluation/dataset.json \
  --output reports/evaluation_report.json \
  --thresholds-file tests/evaluation/thresholds.json
```

### 评估指标

- **Retrieval Hit Rate**: 检索命中率
- **Page Hit Rate**: 页面命中率
- **Keyword Match Rate**: 关键词匹配率
- **Citation Coverage Rate**: 引用覆盖率
- **Current Version Leak Rate**: 当前版本泄漏率
- **Failed Query Rate**: 失败查询率

### 阈值配置

在 `tests/evaluation/thresholds.json` 中配置各项指标的阈值。评估流水线配置为 `continue-on-error: true`，未达标不会导致 CI 失败（仅生成报告供参考）。

---

## 🧪 开发指南

### Python 代码风格

```bash
# 代码检查与格式化
ruff check .              # 检查
ruff check --fix .       # 自动修复
ruff format .            # 格式化

# 测试
pytest                   # 运行所有测试
pytest -x                # 遇到第一个失败停止
```

### 前端开发

```bash
cd frontend

# 开发服务器
npm run dev              # http://localhost:5173

# 生产构建
npm run build

# 代码检查
npm run lint
```

### 项目约定

- **导入顺序**: 标准库 → 第三方 → 本地（每组之间空行）
- **类型注解**: 所有函数签名必须包含参数和返回类型
- **命名规范**:
  - 类: `PascalCase`
  - 函数: `snake_case`
  - 常量: `UPPER_SNAKE_CASE`
  - 私有方法: `_leading_underscore`
- **错误处理**: 捕获具体异常，对外返回通用错误消息，详细信息仅写入日志，避免裸 `except:`
- **日志**: 使用 `get_logger(__name__)`，禁用 `print()`

---

## ⚠️ 注意事项

1. **CUDA/vLLM 冲突**: 模块级别不要导入 `vector_store`，应在函数内部调用 `get_vector_store()`（特别是在 MinerU 解析完成后）
2. **向量存储**: `get_vector_store()` 是线程安全的单例入口；检索统一使用 `similarity_search()`，不要使用旧的 `search()` / `client.search()` 方法
3. **Idempotent 写入**: 使用 `uuid.uuid5` 生成点 ID，确保相同内容生成相同 ID
4. **图像路径**: 存储图像时同时探测 `auto/<img_path>` 和 `auto/images/<img_path>`

---

## 📄 许可证

MIT License © ScholarRAG Team

---

<div align="center">

**[⬆ 返回顶部](#scholarrag)**

Built with ❤️ for Academic Research

</div>
