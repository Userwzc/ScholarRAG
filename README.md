# ScholarRAG

A multimodal RAG (Retrieval-Augmented Generation) system for academic papers. Upload PDF papers, ask questions, and get AI-powered answers with citations.

## Features

### Current Features

- **PDF Ingestion**: Parse academic papers using MinerU with support for text, images, tables, and equations
- **Multimodal Embedding**: Generate embeddings using Qwen3-VL for text and images
- **Vector Storage**: Store embeddings in Qdrant for efficient similarity search
- **RAG Agent**: LangGraph-based agent with multiple search tools:
  - Semantic paper search
  - Visual search (images/figures)
  - Page context lookup
- **Dual Interfaces**:
  - CLI interface (`main.py`)
  - Web UI (FastAPI + React)
- **Theme Support**: Light/dark theme for web interface

### Web Interface Screens

- **Query Page**: Ask questions with streaming answers and source citations
- **Papers Library**: Upload and manage your paper collection
- **Paper Detail**: View chunks and search within papers

## Quick Start

### Prerequisites

- Python 3.12+
- Conda (recommended) or virtualenv
- Qdrant (local or remote)
- CUDA-capable GPU (recommended for embedding)

### Installation

```bash
# Clone and setup environment
conda create -n scholarrag python=3.12
conda activate scholarrag
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
# Edit .env with your API keys and configuration
```

### Running the Application

#### Option 1: CLI

```bash
# Add a paper
python main.py add path/to/paper.pdf

# Query
python main.py query "What is the main contribution of this paper?"

# Delete
python main.py delete paper_name
```

#### Option 2: Web Interface

Start the backend (Terminal 1):
```bash
conda activate scholarrag
uvicorn api.main:app --reload --port 8000
```

Start the frontend (Terminal 2):
```bash
cd frontend
npm run dev
```

Then open http://localhost:5173 in your browser.

## Architecture

```
ScholarRAG/
├── main.py              # CLI entry point
├── api/                 # FastAPI backend
│   ├── main.py         # App setup, CORS, routes
│   ├── schemas.py      # Pydantic models
│   ├── services/       # Business logic
│   └── routes/        # API endpoints
├── frontend/           # React web UI
│   ├── src/
│   │   ├── pages/     # Page components
│   │   ├── components/# UI components
│   │   └── lib/       # API client
├── src/
│   ├── agent/         # LangGraph agent
│   ├── custom/        # Qwen3-VL embedding/reranking
│   ├── ingest/        # MinerU parser, paper manager
│   ├── rag/           # Vector store, embedding
│   └── utils/         # Logging
└── config/            # Settings
```

## Configuration

Key environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | LLM API key | Required |
| `OPENAI_API_BASE` | LLM API base URL | Required |
| `QDRANT_HOST` | Qdrant host | localhost |
| `QDRANT_PORT` | Qdrant port | 6333 |
| `LLM_MODEL` | LLM model name | - |
| `EMBEDDING_MODEL` | Embedding model path | - |
| `MINERU_BACKEND` | MinerU backend | auto |

## Tech Stack

- **Backend**: FastAPI, LangChain/LangGraph, Qdrant
- **ML**: Transformers, PyTorch, Qwen3-VL
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui
- **PDF Processing**: MinerU

## Future Enhancements

- [ ] **User Authentication**: Add user login and personal paper collections
- [ ] **Paper Collections**: Organize papers into folders/collections
- [ ] **Search History**: Save and revisit past queries
- [ ] **Citation Export**: Export answers with formatted citations (BibTeX, APA, etc.)
- [ ] **PDF Viewer**: Inline PDF preview with highlighted references
- [ ] **Multi-language Support**: Support for papers in other languages
- [ ] **Mobile Responsive**: Better mobile UI experience
- [ ] **Paper Recommendations**: Suggest related papers based on queries
- [ ] **Annotation Tools**: Highlight and annotate paper sections
- [ ] **API Authentication**: API key management for external integrations

## License

MIT License
