# AGENTS.md — Agent Module

LangGraph 智能体实现：状态机定义、工具链、多模态答案生成。

## Structure

```
src/agent/
├── graph.py           # LangGraph 状态机和流式事件处理
├── tools.py           # Agent 工具定义（search_papers, search_visuals, get_page_context）
├── langgraph_agent.py # Agent 核心实现
├── evidence_builder.py # 证据组装和视觉上下文
└── multimodal_answerer.py # 多模态答案生成
```

## Key Patterns

### Graph State Machine
- `graph.py` 定义完整的 LangGraph 状态流转
- 流式事件通过 `stream_answer_events()` 生成
- Tool calling 必须至少调用一个 tool 才能回答

### Tool Implementation
- 所有 tools 定义在 `tools.py` 的 `AGENT_TOOLS` 和 `TOOL_REGISTRY`
- Tool 选择规则在 `_SYSTEM_PROMPT` 中定义
- 支持多工具调用和动态 reassessment
- 检索工具只使用 `similarity_search`；不要引用旧的 `client.search()`

### Evidence Assembly
- `evidence_builder.py`: 组装检索证据
- `multimodal_answerer.py`: 生成带视觉上下文的答案
- 视觉证据通过 `_multimodal_input` 传递

## Critical Constraints

1. **Message Types**: 系统提示词用 `SystemMessage`，禁止 `HumanMessage`
2. **Tool Calls**: 回答前必须至少调用一个 tool
3. **Stream Mode**: 不要切换为 `"values"`（除非内部迭代器）
4. **CUDA/vLLM**: 不要在此模块导入 `get_vector_store()`（见根级 AGENTS.md）

## API

```python
from src.agent.graph import stream_answer_events

for event in stream_answer_events(question):
    # event types: agent_status, tool_call, tool_result, 
    #              agent_observation, agent_visual_context, 
    #              answer_started, answer_token
    pass
```
