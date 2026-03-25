# Plan: Default Disable Reranker, Keep Hybrid-Only Path

## Objective
默认禁用 standalone reranker，使用 LangChain-Qdrant hybrid retrieval 作为默认检索路径，保留回退开关，并添加离线评测验证质量。

## Background
- 当前系统使用 LangChain-Qdrant HYBRID (dense+sparse fusion) + 自定义 Qwen3-VL reranker
- HYBRID 是召回层融合，reranker 是精排层；两者职责不同
- 目标：降低 VRAM 占用，简化架构

## Scope

### IN
- 配置层：修改默认 `RERANKER_MODEL` 为空
- 检索层：统一使用 `similarity_search()`
- Agent 层：更新工具调用使用新方法
- 文档：更新 README、AGENTS.md
- 评测：添加离线检索质量评测

### OUT
- 不物理删除 reranker 代码（保留回退能力）
- 不修改 embedding 模型
- 不修改 MinerU 解析逻辑

## TODOs

### Task 1: 修改配置默认禁用 Reranker
- [x] 修改 `config/settings.py`: `RERANKER_MODEL` 默认值为空字符串
- [x] 更新 `.env.example`: 注释掉或清空 `RERANKER_MODEL`
- [x] 验证：启动时不加载 reranker 模型

### Task 2: 重构检索 API
- [x] 在 `src/rag/vector_store.py`:
  - [x] 统一调用 `similarity_search()`
  - [x] 简化逻辑：当 `_reranker_path` 为空时直接返回结果
- [x] 更新 `get_vector_store()` 工厂函数

### Task 3: 更新 Agent 工具
- [x] 修改 `src/agent/tools.py`:
  - [x] `search_papers`: 使用新的 `similarity_search()`
  - [x] `search_visuals`: 使用新的 `similarity_search()`
  - [x] 调整 `candidate_k` 计算（无 reranker 时不需要 *3）

### Task 4: 更新文档
- [x] 更新 `README.md`:
  - [x] 移除 reranker 作为主要特性
  - [x] 添加 "可选 reranker" 说明
  - [x] 更新架构图
- [x] 更新 `AGENTS.md`:
  - [x] 更新 Vector Store API 章节
  - [x] 添加 "禁用 reranker" 说明

### Task 5: 添加离线评测
- [x] 创建 `tests/evaluation/` 目录
- [x] 添加评测数据集（示例论文问答对）
- [x] 实现评测脚本：对比 hybrid-only vs reranker 的 top-k 命中率
- [x] 定义质量门槛（如 Precision@10 >= 0.6）

## Acceptance Criteria

- [x] `RERANKER_MODEL` 默认为空时系统正常运行
- [x] 显存占用降低（对比之前）
- [x] 检索功能正常（通过人工测试）
- [x] 文档已更新
- [x] 评测脚本可运行

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| 检索质量下降 | 保留配置开关，可快速回退；添加评测验证 |
| API 破坏 | 统一迁移调用点，避免保留旧别名 |
| 显存未明显下降 | 监控实际占用，必要时进一步优化 |

## Notes
- Hybrid retrieval 使用 RRF 融合，不是 semantic reranking
- 如需更高精度，可重新启用 reranker（设置 `RERANKER_MODEL`）

## Completion Notes
- 已完成默认禁用 reranker 的收尾整理，所有 TODO 已关闭。
- 保留 hybrid-only 检索与回退路径，便于后续需要时恢复 reranker。
