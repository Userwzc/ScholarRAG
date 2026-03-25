# AGENTS.md — Custom Models

Qwen3-VL 模型封装：多模态嵌入、视觉工具。

## Structure

```
src/custom/
├── qwen3_vl_embedding.py  # Qwen3-VL 嵌入模型（LangChain 兼容）
├── qwen3_vl_base.py     # 共享基类和工具函数
└── vision_utils.py      # 视觉处理工具
```

## Key Classes

| Class | Purpose | Extends |
|-------|---------|---------|
| `Qwen3VLEmbeddings` | 多模态嵌入 | `langchain_core.embeddings.Embeddings` |
| `BaseQwen3VLModel` | 共享基类 | - |

## Critical Patterns

### Embedding Interface
```python
# Unified API - input can be str or dict
embed_query(input: str | dict) -> list[float]
embed_documents(inputs: list[str | dict]) -> list[list[float]]

# Async versions
aembed_query(input: str | dict)
aembed_documents(inputs: list[str | dict])
```

### Multimodal Input Format
```python
{"text": "...", "image": "path/to/image.jpg"}
```

### PyTorch Rules
- `@torch.no_grad()` on inference methods
- Explicit `tensor.to(self.model.device)`
- Call `model.eval()` after loading
- Use `bfloat16` if supported, else `float16`
- Call `torch.cuda.empty_cache()` after batch loops

## VRAM Optimization
- 从 19GB → ~10GB（~50% reduction）
- 使用 `bfloat16`/`float16` precision
- 批处理和缓存清理
