# 移除 Qwen3-VL Reranker 代码执行计划

## 目标
彻底移除 Qwen3-VL reranker 相关代码，简化架构，减少维护负担。

## 背景
- 已默认禁用 reranker（RERANKER_MODEL 默认为空）
- 评测显示 hybrid-only 模式已足够
- 决定彻底移除 reranker 支持，而非保留为可选功能

## 任务分解

### Task 1: 删除 reranker 实现文件
- [ ] 删除 `src/custom/qwen3_vl_reranker.py`
- [ ] 删除 `src/rag/reranker_strategy.py`

### Task 2: 清理 vector_store.py 中的 reranker 代码
- [ ] 移除 `NoOpReranker, RerankerStrategy` 导入
- [ ] 移除 `reranker` 参数（构造函数）
- [ ] 移除 `_reranker_path` 和 `_reranker_instance` 属性
- [ ] 移除 `reranker` property
- [ ] 移除 `_load_reranker` 方法
- [ ] 移除 `_do_rerank` 方法
- [ ] 简化 `similarity_search` 方法（移除 rerank 逻辑）
- [ ] 更新 `_create_vector_store` 中的 reranker 相关代码

### Task 3: 移除配置
- [ ] `config/settings.py`: 移除 `RERANKER_MODEL` 配置
- [ ] `.env.example`: 移除 `RERANKER_MODEL` 环境变量

### Task 4: 更新相关代码
- [ ] `src/agent/tools.py`: 移除 reranker 检测逻辑（candidate_k 计算）
- [ ] `tests/evaluation/retrieval_eval.py`: 移除 reranker 评测逻辑

### Task 5: 更新文档
- [ ] `AGENTS.md`: 移除 reranker 相关文档
- [ ] `README.md`: 移除 reranker 相关说明
- [ ] `src/custom/AGENTS.md`: 移除 Qwen3VLReranker 说明
- [ ] `src/rag/AGENTS.md`: 如果存在，移除 reranker 相关

## 验证清单
- [ ] 代码能正常导入无语法错误
- [ ] 无残留 reranker 引用（grep 检查）
- [ ] 文档一致更新
- [ ] 系统能正常运行（基础功能测试）

## 注意事项
- `src/custom/qwen3_vl_base.py` **保留** - 被 embedding 使用
- `src/custom/qwen3_vl_embedding.py` **保留** - 核心功能
- 确保 hybrid-only 检索逻辑完整
