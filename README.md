# ScholarRAG

ScholarRAG is a cutting-edge **Multimodal RAG (Retrieval-Augmented Generation)** system designed specifically for academic research. It enables users to upload PDF papers and interact with them through an intelligent agent that understands not just text, but also **complex tables, figures, and mathematical formulas**.

## ✨ Key Features

### 🧠 Advanced Agentic Intelligence
- **Powered by LangGraph**: A robust state-machine based agent that autonomously plans research steps, executes tool calls, and synthesizes findings.
- **Multimodal Reasoning**: The agent can "see" and analyze visual evidence (figures/tables) retrieved from papers to provide more comprehensive answers.
- **Dynamic Tooling**: Includes semantic search, targeted visual retrieval, and page-level context expansion.

### 📄 Intelligent PDF Ingestion
- **MinerU Integration**: High-fidelity parsing of academic PDFs into clean Markdown, extracting text, images, and cross-referencing equations.
- **Unified Service Layer**: Centralized ingestion pipeline ensures consistent processing across CLI and Web interfaces.

### 🚀 Performance & Optimization
- **VRAM Optimized**: Smart model loading using `bfloat16`/`float16` precision, reducing GPU memory footprint by nearly **50%** (from 19GB to ~10GB).
- **Repository Pattern**: Clean data access layer isolating business logic from the underlying Qdrant vector database.

### 💻 Modern Web Experience
- **Immersive Chat**: A full-page, fixed-bottom chat interface designed for deep focus sessions.
- **Collapsible Thought Process**: Watch the agent's research steps in real-time through an elegant, interactive UI component.
- **LaTeX Support**: Native rendering of mathematical formulas using KaTeX.
- **Rich Citations**: Instant links to source papers and specific page numbers for every claim.

---

## 🛠️ Architecture

```
ScholarRAG/
├── main.py              # Unified CLI entry point
├── api/                 # FastAPI Backend
│   ├── services/       # Decoupled business logic (Paper/Query services)
│   └── routes/        # RESTful API endpoints
├── frontend/           # Modern React + TypeScript SPA
│   ├── src/components/ # Reusable UI (ThoughtProcess, etc.)
│   └── src/pages/     # Immersive View components
├── src/
│   ├── core/          # Shared Business Logic (Ingestion Service)
│   ├── agent/         # LangGraph state machine and tools
│   ├── custom/        # Qwen3-VL specific model wrappers
│   ├── rag/           # Vector Store (Qdrant) and Repository logic
│   └── ingest/        # MinerU-based PDF parsing engine
└── config/            # Centralized Pydantic-based configuration
```

---

## 🚦 Quick Start

### Prerequisites
- Python 3.12+
- Qdrant (Running locally or in cloud)
- NVIDIA GPU (RTX 2080 Ti or higher recommended)

### Setup
1. **Clone & Install**
   ```bash
   conda create -n scholarrag python=3.12
   conda activate scholarrag
   pip install -r requirements.txt
   ```
2. **Configure**
   ```bash
   cp .env.example .env
   # Set your OPENAI_API_KEY and model paths in .env
   ```

### Execution
- **Run CLI**: `python main.py query "What is the core methodology of the DREAM paper?"`
- **Run Backend**: `uvicorn api.main:app --host 0.0.0.0 --port 8000`
- **Run Frontend**: `cd frontend && npm run dev`

---

## 🧪 Tech Stack
- **AI/ML**: [LangGraph](https://github.com/langchain-ai/langgraph), [LangChain](https://github.com/langchain-ai/langchain), [Qwen3-VL](https://github.com/QwenLM/Qwen-VL), Transformers, PyTorch.
- **Database**: [Qdrant](https://qdrant.tech/) (Vector Database).
- **Backend**: FastAPI, Pydantic v2.
- **Frontend**: React 18, TypeScript, Tailwind CSS, shadcn/ui, KaTeX.
- **Parsing**: [MinerU](https://github.com/opendatalab/MinerU).

## 📄 License
MIT License.
