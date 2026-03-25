# 执行计划：代码安全与质量修复

## 目标
1. 删除所有向后兼容别名，统一使用 `similarity_search`
2. 修复 API 异常信息泄露（5处）
3. 添加线程锁到 `get_vector_store()` 单例
4. 提取硬编码配置到 config/settings.py

## 任务分解

### Task 1: 删除别名并更新引用
- **文件**: `src/rag/vector_store.py`
  - [x] 删除第559行的向后兼容别名
  - [x] 删除第49行的文档引用
  - [x] 更新文档字符串，只保留 `similarity_search` 说明
- **文件**: `src/agent/tools.py`
  - [x] 确认已使用 `similarity_search`（当前正确）
- **文件**: `AGENTS.md`
  - [x] 更新文档，将搜索 API 统一表述为 `similarity_search`

### Task 2: 修复 API 异常泄露（5处）
- **文件**: `api/routes/papers.py` (4处)
  - [x] L34: `detail=str(e)` → `detail="Failed to upload paper"`
  - [x] L43: `detail=str(e)` → `detail="Failed to list papers"`
  - [x] L64: `detail=str(e)` → `detail="Failed to delete paper"`
  - [x] L77: `detail=str(e)` → `detail="Failed to get paper details"`
  - [x] 所有错误需记录到 logger
- **文件**: `api/routes/query.py` (1处)
  - [x] L53: `detail=str(e)` → `detail="Query processing failed"`
  - [x] 确保 logger 记录完整错误

### Task 3: 添加线程锁
- **文件**: `src/rag/vector_store.py`
  - [x] 在模块级别添加：`import threading`
  - [x] 在模块级别添加：`_vector_store_lock = threading.Lock()`
  - [x] 修改 `get_vector_store()` 函数，使用双重检查锁定模式

### Task 4: 提取硬编码配置
- **文件**: `config/settings.py`
  - [x] 添加：`QDRANT_COLLECTION_NAME: str = os.getenv("QDRANT_COLLECTION_NAME", "papers_rag")`
- **文件**: `src/rag/vector_store.py`
  - [x] 修改 `_create_vector_store()`，从 config 读取集合名
- **文件**: `.env.example`
  - [x] 添加：`QDRANT_COLLECTION_NAME=papers_rag`

## 验证标准
- [x] 代码能正常导入无语法错误
- [x] API 路由异常不再泄露内部信息
- [x] 线程锁正确实现（通过代码审查）
- [x] 配置正确提取，可从环境变量覆盖
- [x] 所有修改点都经过测试确认

## Completion Notes
- 已完成全部安全与质量修复项，计划现已收尾。
- 文档仅保留完成状态与修复结果，便于后续追踪。
