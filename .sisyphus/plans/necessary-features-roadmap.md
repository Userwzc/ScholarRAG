# ScholarRAG Necessary Features Roadmap

## TL;DR
> **Summary**: Add the five highest-value missing capabilities that move ScholarRAG from a usable single-user demo to a reliable research system: async ingestion jobs, document versioning/reindex, fine-grained citations, offline evaluation, and automated QA/CI.
> **Deliverables**:
> - Persistent paper/version/job metadata in SQLite with non-breaking API integration
> - Async ingestion + progress/retry UX in FastAPI and React
> - Structured provenance payloads and frontend citation deep-links
> - Offline evaluation runner with regression dataset and machine-readable reports
> - Automated backend/frontend test suite and GitHub Actions workflow
> **Effort**: Large
> **Parallel**: YES - 2 waves
> **Critical Path**: 1 → 2 → 3 → 4 → 6 → 8 → 9 → 10

## Context
### Original Request
查看当前的项目还能添加哪些必要的功能；在优先级收敛后，用户确认把前 5 项整理成可执行 work plan。

### Interview Summary
- 当前系统已具备 CLI、FastAPI、React 前端、MinerU 摄取、Qdrant 检索、LangGraph Agent、SQLite 对话历史。
- 本计划只覆盖 5 个最高优先缺口：RAG 评测闭环、细粒度引用/溯源、文档版本化与重建索引、摄取任务状态/重试、自动化测试与 CI。
- 计划默认维持现有单机技术栈：FastAPI + React + LangGraph + Qdrant + SQLite。
- 明确排除：鉴权/多租户、Redis/Celery、在线评测后台、完整管理后台。
- 兼容性要求：现有 CLI 与已公开 API 不做破坏式替换；新增能力通过新增表、字段、端点、前端流程接入。

### Metis Review (gaps addressed)
- 固化 guardrail：不引入 Redis、Auth、多租户等新基础设施。
- 固化兼容策略：新增异步上传与版本化能力，但保留现有同步入口作为兼容路径。
- 固化默认决策：评测先做离线 runner + pytest 回归；引用改为结构化 provenance 并保留现有 `sources` 语义。
- 固化风险控制：版本化必须保留当前检索默认只读“当前版本”；CI 只先覆盖新增能力，不要求全仓 100% 覆盖。

## Work Objectives
### Core Objective
在不引入外部基础设施、不中断现有使用路径的前提下，为 ScholarRAG 增加“可追踪、可回归、可恢复、可验证”的基础能力。

### Deliverables
- SQLite 中新增 paper / paper_version / ingestion_job 持久化模型与迁移机制。
- 新增异步上传/重建索引/任务状态/任务重试 API，与前端轮询展示流程。
- Agent/后端返回结构化 citation/provenance，前端渲染可跳转到 PDF 页面的引用 UI。
- 离线评测 runner、数据集格式、JSON 报告与回归阈值。
- pytest + 前端验证 + GitHub Actions CI。

### Definition of Done (verifiable conditions with commands)
- `pytest tests -q` 通过。
- `pytest tests/evaluation -q` 通过并生成评测产物。
- `ruff check .` 通过。
- `cd frontend && npm run lint && npm run build` 通过。
- API smoke：`curl -s http://localhost:8000/api/health | jq -r '.status'` 返回 `ok`。
- Async ingest smoke：上传接口返回 `job_id`，状态接口能从 `pending/processing` 走到 `completed/failed`。
- Reindex smoke：同一论文重建索引后，当前检索只读取最新版本，版本列表能列出历史版本。
- Citation smoke：查询结果中的 `sources` 至少包含 `pdf_name`、`page`、`chunk_id`、`paper_version`、`heading`。

### Must Have
- 新能力全部遵循现有 route/service 分层。
- 所有 Qdrant 过滤仍使用 `qdrant_client.http.models.Filter`。
- 版本化不破坏当前 `pdf_name` 维度的读取体验。
- 任务状态持久化到 SQLite，进程内后台执行，不依赖 Redis。
- 评测结果为机器可读 JSON，可在 CI 中判断阈值。
- 每项新增能力都有自动化测试与 agent-executed QA 场景。

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- 不新增鉴权、RBAC、多租户、管理后台。
- 不引入 Redis、Celery、Kafka、外部任务队列。
- 不做破坏式 API 改名；已有同步入口只允许兼容性增强。
- 不把评测做成在线 dashboard；仅做离线 runner + CI gate。
- 不要求全仓历史代码补全测试，只覆盖新能力及其关键回归路径。
- 不让任何验证步骤依赖人工肉眼判断。

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.
- Test decision: tests-after + pytest / curl / jq / frontend lint+build
- QA policy: Every task bundles implementation + verification in one task
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks for max parallelism.

Wave 1: foundation + contracts
- Task 1: test harness and fixtures
- Task 2: SQLite schema + migration bootstrap for papers/versions/jobs
- Task 3: async ingestion contract and status/retry endpoints
- Task 4: ingestion progress/failure instrumentation
- Task 5: structured citation/provenance backend contract

Wave 2: productization + regression + automation
- Task 6: version-aware reindex and current-version retrieval
- Task 7: frontend job/provenance UX
- Task 8: offline evaluation pipeline and dataset
- Task 9: regression tests across jobs/versioning/citations/evaluation
- Task 10: GitHub Actions CI and quality gates

### Dependency Matrix (full, all tasks)
| Task | Depends On | Blocks |
|---|---|---|
| 1 | - | 2, 8, 9, 10 |
| 2 | 1 | 3, 6, 9 |
| 3 | 1, 2 | 4, 7, 9 |
| 4 | 2, 3 | 6, 7, 9 |
| 5 | 1 | 7, 8, 9 |
| 6 | 2, 4 | 7, 8, 9 |
| 7 | 3, 5, 6 | 9 |
| 8 | 1, 5, 6 | 9, 10 |
| 9 | 3, 4, 5, 6, 7, 8 | 10 |
| 10 | 1, 8, 9 | F1-F4 |

### Agent Dispatch Summary (wave → task count → categories)
- Wave 1 → 5 tasks → unspecified-high / deep
- Wave 2 → 5 tasks → unspecified-high / quick
- Final Verification → 4 tasks → oracle / unspecified-high / deep

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [x] 1. Establish backend test harness and reproducible fixtures

  **What to do**: Add a pytest configuration, shared fixtures, and deterministic test doubles so the new roadmap work can be verified without GPU hardware or live model calls. Create fixtures for a temporary SQLite database, mocked/fake vector store interactions, representative parsed-paper payloads, and at least one stable sample PDF path fixture. If frontend citation/job rendering is split into reusable helpers, add a minimal TS test harness for those helpers; otherwise keep frontend verification at lint/build + final QA level.
  **Must NOT do**: Do not make CI depend on a local GPU, real Qwen3-VL weights, or external OpenAI calls. Do not rewrite existing production logic just to satisfy test setup.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: introduces shared verification infrastructure used by all later tasks.
  - Skills: `[]` — no extra skill required.
  - Omitted: `[]` — no specialty intentionally omitted.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 2, 8, 9, 10 | Blocked By: none

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `api/database.py:34-71` — existing async DB lifecycle and session context to mirror in test fixtures.
  - Pattern: `api/routes/conversations.py:25-121` — representative async route testing surface.
  - Pattern: `tests/evaluation/retrieval_eval.py:14-160` — current evaluation script to convert into reusable test fixtures and regression inputs.
  - Pattern: `config/settings.py:27-71` — env-driven configuration that tests must override deterministically.
  - Pattern: `frontend/src/lib/api.ts:170-243` — current SSE client contract to isolate with deterministic test inputs if helper extraction is needed.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests -q` runs with discovered tests and no import/setup errors.
  - [ ] `pytest tests -q -k "not integration"` passes without requiring Qdrant, GPU, or network access.
  - [ ] A reusable fixture exists for temporary DB initialization and at least one fake vector-store response path.
  - [ ] New test documentation/comments clearly state how to override env/config for local and CI runs.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Backend test harness boots cleanly
    Tool: Bash
    Steps: run `pytest tests -q -k "not integration"`
    Expected: pytest exits 0 and reports collected tests without trying to download models or connect to external services
    Evidence: .sisyphus/evidence/task-1-test-harness.txt

  Scenario: Missing env values do not break fixture startup
    Tool: Bash
    Steps: run `env -u OPENAI_API_KEY -u EMBEDDING_MODEL pytest tests -q -k "not integration"`
    Expected: tests still run using test overrides/fakes; no auth/model-path crash occurs during collection
    Evidence: .sisyphus/evidence/task-1-test-harness-error.txt
  ```

  **Commit**: YES | Message: `test(infra): add deterministic test harness for roadmap features` | Files: `pytest.ini`, `tests/conftest.py`, `tests/fixtures/**`, optional `frontend/**/__tests__/**`

- [x] 2. Add persistent paper/version/job schema with migration bootstrap

  **What to do**: Introduce SQLite persistence for `paper`, `paper_version`, and `ingestion_job`, plus the minimal migration/bootstrap mechanism needed to evolve the current DB safely. Keep `Conversation` and `Message` intact, but extend startup so schema changes are explicit and repeatable rather than relying only on `Base.metadata.create_all()`. Define durable fields for job status, progress, stage, retry count, source file path, result summary, error message, and for versions: `version_number`, `is_current`, timestamps, source hash, and schema version.
  **Must NOT do**: Do not add Redis/Celery. Do not remove or rename existing conversation tables. Do not store transient-only status in memory.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: persistent schema decisions affect every later feature.
  - Skills: `[]` — no extra skill required.
  - Omitted: `[]` — no specialty intentionally omitted.

  **Parallelization**: Can Parallel: PARTIAL | Wave 1 | Blocks: 3, 6, 9 | Blocked By: 1

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `api/models.py:15-61` — current SQLAlchemy modeling style and relationship pattern.
  - Pattern: `api/database.py:22-45` — current engine/session/bootstrap behavior to evolve into migration-aware startup.
  - Pattern: `api/routes/conversations.py:37-121` — current CRUD flow for DB-backed resources.
  - Pattern: `src/core/ingestion.py:11-156` — existing ingestion metadata and `INGESTION_SCHEMA_VERSION` that must be persisted at version level.
  - Pattern: `main.py:25-49` — current CLI ingestion schema constant and sync ingestion path that must remain compatible.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Database bootstrap creates/updates `papers`, `paper_versions`, and `ingestion_jobs` alongside existing conversation tables.
  - [ ] Startup path remains idempotent: running schema bootstrap twice produces no error.
  - [ ] Model/service tests verify create/read/update transitions for job state and current-version toggling.
  - [ ] Existing conversation CRUD tests still pass unchanged after schema expansion.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Schema bootstrap creates new tables safely
    Tool: Bash
    Steps: run the migration/bootstrap command twice against a fresh temp SQLite database, then query table names
    Expected: conversations, messages, papers, paper_versions, and ingestion_jobs all exist; second run is a no-op success
    Evidence: .sisyphus/evidence/task-2-schema.txt

  Scenario: Job/version rows survive restart
    Tool: Bash
    Steps: create a paper, version, and ingestion job in a temp DB; reopen a new session and query them back
    Expected: persisted rows retain status/version fields exactly; no in-memory-only loss occurs
    Evidence: .sisyphus/evidence/task-2-schema-error.txt
  ```

  **Commit**: YES | Message: `feat(api): persist papers versions and ingestion jobs` | Files: `api/models.py`, `api/database.py`, migration/bootstrap files, related service modules/tests

- [x] 3. Introduce non-breaking async ingestion API with status and retry endpoints

  **What to do**: Keep the current synchronous upload path for compatibility, but add a new async job-oriented upload flow that the frontend will adopt. Create endpoints that: (1) accept multipart upload and immediately return `202` with `job_id`, (2) fetch a job by ID, (3) retry a failed job, and (4) optionally list recent jobs for the library screen. Persist the staged source PDF in a job-scoped location so retries are possible even after the initial request ends.
  **Must NOT do**: Do not replace `/api/papers/upload` with a breaking response format. Do not keep retry state only in memory. Do not delete the staged file before the job reaches a terminal state.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: API contract and service orchestration change together.
  - Skills: `[]` — no extra skill required.
  - Omitted: `[]` — no specialty intentionally omitted.

  **Parallelization**: Can Parallel: PARTIAL | Wave 1 | Blocks: 4, 7, 9 | Blocked By: 1, 2

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `api/routes/papers.py:20-37` — current synchronous upload route that must remain intact.
  - Pattern: `api/services/paper_service.py:54-87` — current sync ingest workflow to wrap/split into job creation + background execution.
  - Pattern: `api/services/paper_service.py:198-208` — current temp-file save/cleanup helpers that need staged-file retention for retries.
  - Pattern: `api/main.py:45-54` — route registration style and health endpoint conventions.
  - Pattern: `frontend/src/pages/PapersPage.tsx:27-41` — current upload UX that will move to async job submission.
  - API/Type: `api/schemas.py:22-89` — response modeling conventions to extend with job schemas.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `POST` to the new async upload endpoint returns `202` and JSON containing `job_id`, `status`, and original filename metadata.
  - [ ] `GET` job endpoint returns durable `status`, `stage`, `progress`, `retry_count`, `error_message`, and `result` fields.
  - [ ] `POST` retry endpoint only succeeds for terminal failed jobs and increments `retry_count`.
  - [ ] Existing `/api/papers/upload` compatibility path still returns the prior completed-upload shape for synchronous callers.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Async upload returns job_id immediately
    Tool: Bash
    Steps: `curl -s -o /tmp/job.json -w "%{http_code}" -F "file=@tests/fixtures/pdfs/test-paper.pdf" http://localhost:8000/api/papers/uploads`
    Expected: HTTP status 202 and `/tmp/job.json` contains non-empty `job_id`, `status: "pending"|"processing"`, and no completed paper payload yet
    Evidence: .sisyphus/evidence/task-3-async-upload.txt

  Scenario: Retry is rejected for non-failed jobs
    Tool: Bash
    Steps: create a fresh pending job, then call the retry endpoint before it fails
    Expected: API returns 409 or 400 with a sanitized message indicating retry is only allowed for failed jobs
    Evidence: .sisyphus/evidence/task-3-async-upload-error.txt
  ```

  **Commit**: YES | Message: `feat(api): add async ingestion job endpoints` | Files: `api/routes/papers.py`, new/updated service modules, `api/schemas.py`, tests

- [x] 4. Instrument ingestion pipeline with progress, terminal states, and manual retry safety

  **What to do**: Thread progress reporting through parse → chunk → persist → finalize so every async ingestion job has durable stage/progress updates. Add a progress callback/reporting abstraction to `process_paper()` and the surrounding paper service, persist terminal success/failure details, and ensure manual retry reuses the staged source file while preventing duplicate concurrent execution of the same job. Set the default policy to manual retry only; no automatic backoff loop.
  **Must NOT do**: Do not add silent auto-retries. Do not mark a job `completed` before Qdrant write and PDF persistence both succeed. Do not leave jobs permanently in `processing` after exceptions.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: touches blocking ingestion internals, state transitions, and error semantics.
  - Skills: `[]` — no extra skill required.
  - Omitted: `[]` — no specialty intentionally omitted.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 6, 7, 9 | Blocked By: 2, 3

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `src/core/ingestion.py:13-156` — current monolithic ingestion function to extend with progress callbacks.
  - Pattern: `api/services/paper_service.py:54-87` — current upload path where parse/store/finalize happen in one synchronous block.
  - Pattern: `api/services/paper_service.py:72-79` — PDF persistence and vector-store write order that terminal-state reporting must honor.
  - Pattern: `src/ingest/mineru_parser.py:287-345` — chunking process and token counting area where progress stages should be anchored.
  - Pattern: `config/settings.py:45-68` — retrieval/ingestion settings surface for any new retry/job retention knobs.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Job status progresses through explicit stages such as `queued`, `parsing`, `chunking`, `storing`, `finalizing`, `completed` or `failed`.
  - [ ] A thrown exception during parsing or storing records `failed` with sanitized `error_message` and leaves the job eligible for manual retry.
  - [ ] Duplicate execution is prevented: a second worker/request cannot run the same job while it is already `processing`.
  - [ ] Successful completion records paper/version/result metadata on the job row for later UI display.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Progress moves through durable stages
    Tool: Bash
    Steps: submit an async upload, poll the job endpoint every second until terminal state, and capture intermediate payloads
    Expected: observed responses show monotonic stage/progress advancement ending in `completed`; no stage regression occurs
    Evidence: .sisyphus/evidence/task-4-ingestion-progress.txt

  Scenario: Failed ingest becomes retryable instead of hanging
    Tool: Bash
    Steps: submit a known-bad PDF fixture or force a storage failure with a test double, then poll the job endpoint
    Expected: job ends in `failed` with a sanitized error, `retry_count` unchanged, and a subsequent retry request is accepted
    Evidence: .sisyphus/evidence/task-4-ingestion-progress-error.txt
  ```

  **Commit**: YES | Message: `feat(ingest): persist job progress and retry-safe terminal states` | Files: `src/core/ingestion.py`, `api/services/paper_service.py`, related helpers/tests

- [x] 5. Emit structured citation and provenance data from the backend query flow

  **What to do**: Replace the current coarse page-only source reconstruction with backend-authored provenance objects. Extend evidence assembly and streaming so final query results include `chunk_id`, `paper_version`, `pdf_name`, `page`, `chunk_type`, `heading`, and a short supporting text/label while preserving existing `sources` compatibility. Ensure both SSE final events and persisted conversation messages carry the same normalized provenance shape.
  **Must NOT do**: Do not force the frontend to infer citations from `tool_result.pages` only. Do not remove the existing `pdf_name/page/type` fields that current consumers already understand. Do not expose raw internal exception data in SSE payloads.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: spans LangGraph evidence handling, API schemas, SSE, and persistence.
  - Skills: `[]` — no extra skill required.
  - Omitted: `[]` — no specialty intentionally omitted.

  **Parallelization**: Can Parallel: PARTIAL | Wave 1 | Blocks: 7, 8, 9 | Blocked By: 1

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `src/agent/graph.py:34-58` — answer/tool rules that provenance must respect.
  - Pattern: `src/agent/graph.py:105-143` — tool execution/event kind mapping where final structured provenance must attach cleanly.
  - Pattern: `src/agent/evidence_builder.py:43-246` — current evidence collection/enrichment/routing pipeline to extend with stable citation payloads.
  - Pattern: `api/services/query_service.py:9-52` — SSE event shaping point for final normalized payloads.
  - API/Type: `api/schemas.py:103-173` — current `SourceSchema`, `MessageResponse`, and SSE schema definitions to extend without breaking compatibility.
  - Pattern: `frontend/src/pages/QueryPage.tsx:140-205` — current frontend source reconstruction from `tool_result.pages`, which should become a consumer of final structured sources instead.
  - Pattern: `frontend/src/stores/conversation-store.ts:125-199` — persisted message/source mapping that must stay compatible after schema expansion.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Final query payloads include structured `sources` entries with at least `pdf_name`, `page`, `type`, `chunk_id`, `paper_version`, and `heading`.
  - [ ] Persisted assistant messages store the same expanded source shape without losing current fields.
  - [ ] Queries with no sufficient evidence still return an empty or omitted `sources` array rather than malformed placeholders.
  - [ ] Existing SSE token streaming still works while final provenance arrives in a machine-readable event.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Query returns structured provenance
    Tool: Bash
    Steps: issue a known-answer query against a fixture paper, capture the final SSE event or persisted assistant message JSON, and inspect `sources`
    Expected: at least one source object contains `pdf_name`, `page`, `type`, `chunk_id`, `paper_version`, and `heading`; token streaming remains intact
    Evidence: .sisyphus/evidence/task-5-provenance.txt

  Scenario: Unsupported question does not fabricate citations
    Tool: Bash
    Steps: issue a query unrelated to indexed papers and inspect the final payload
    Expected: response reports insufficient evidence and returns no bogus `chunk_id`/page references
    Evidence: .sisyphus/evidence/task-5-provenance-error.txt
  ```

  **Commit**: YES | Message: `feat(agent): emit structured provenance for answers` | Files: `src/agent/graph.py`, `src/agent/evidence_builder.py`, `api/services/query_service.py`, `api/schemas.py`, tests

- [x] 6. Implement version-aware reindexing and current-version retrieval guarantees

  **What to do**: Introduce explicit paper-version lifecycle management so first ingestion creates version 1 and subsequent reindex operations create later versions while preserving prior versions as non-current history. Update vector-store metadata generation and retrieval filters so default search/list/detail/chunk/toc flows only surface `is_current=true`, while version history can still be queried intentionally. Add an explicit reindex entry point that creates a new version and job for an existing paper.
  **Must NOT do**: Do not let stale versions leak into default retrieval results. Do not delete prior versions during a successful reindex unless the plan explicitly says so. Do not change deterministic ID generation in a way that collides across versions.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: changes Qdrant metadata semantics, service filters, and reindex behavior.
  - Skills: `[]` — no extra skill required.
  - Omitted: `[]` — no specialty intentionally omitted.

  **Parallelization**: Can Parallel: PARTIAL | Wave 2 | Blocks: 7, 8, 9 | Blocked By: 2, 4

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `src/rag/vector_store.py:27-34` — current UUIDv5 scheme that must incorporate version-safe identity inputs.
  - Pattern: `src/rag/vector_store.py:104-210` — add/store payload generation where `paper_version` and `is_current` metadata must be written.
  - Pattern: `src/rag/vector_store.py:331-445` — metadata fetch/count/delete helpers that need version-aware filters.
  - Pattern: `api/services/paper_service.py:28-52` — filter builder that currently only scopes by `pdf_name` and `chunk_type`.
  - Pattern: `api/services/paper_service.py:90-181` — list/detail/chunk responses that must default to current version while optionally exposing version info.
  - Pattern: `api/services/paper_service.py:218-275` — TOC generation that must stay on the selected/current version.
  - Pattern: `src/core/ingestion.py:75-154` — metadata assembly point for inserting version/current markers.
  - Pattern: `main.py:28-49` — legacy CLI add path that must remain functional under version-aware ingestion.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Initial ingest creates version 1 and marks it current.
  - [ ] Reindexing an existing paper creates version 2+ and flips older versions to `is_current=false` without deleting history.
  - [ ] Default search/list/detail/chunk/toc paths only surface current-version data.
  - [ ] A version-history endpoint or service method exposes prior versions for explicit inspection.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Reindex creates a new current version without history loss
    Tool: Bash
    Steps: ingest a fixture paper, trigger reindex for the same paper, then query version history and default paper detail
    Expected: version history shows at least versions 1 and 2; default detail/search uses version 2 only
    Evidence: .sisyphus/evidence/task-6-versioning.txt

  Scenario: Old-version chunks do not leak into default retrieval
    Tool: Bash
    Steps: create distinguishable content across two versions, run a default query/list/chunk fetch without specifying version
    Expected: results reference only the current version; any old-version-only content is excluded unless version is explicitly requested
    Evidence: .sisyphus/evidence/task-6-versioning-error.txt
  ```

  **Commit**: YES | Message: `feat(rag): add version-aware reindex and current-version filtering` | Files: `src/rag/vector_store.py`, `src/core/ingestion.py`, `api/services/paper_service.py`, related routes/schemas/tests

- [x] 7. Update frontend upload, library, chat, and reader flows for jobs and deep-linked citations

  **What to do**: Move `PapersPage` to the new async upload flow, show job progress/failure/retry state in the paper library UX, and replace ad-hoc source reconstruction in `QueryPage` with rendering from final structured provenance. Add click-through behavior from a citation to the reader route with page preselection, and teach `PaperReaderPage` to honor query parameters or equivalent navigation state so the cited page opens directly.
  **Must NOT do**: Do not keep using `alert()` as the primary async status surface for uploads. Do not require users to manually locate the cited page after clicking a citation. Do not break existing conversation persistence.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` — Reason: user-facing workflow and citation UX changes span multiple React views.
  - Skills: `[]` — no extra skill required.
  - Omitted: `[]` — no specialty intentionally omitted.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 9 | Blocked By: 3, 5, 6

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `frontend/src/pages/PapersPage.tsx:27-115` — current synchronous upload flow and empty-state/upload-zone UI to convert to async job UX.
  - Pattern: `frontend/src/lib/api.ts:121-129` — current upload client API that will gain async job methods.
  - Pattern: `frontend/src/pages/QueryPage.tsx:140-205` — current step/source handling that should consume backend provenance directly.
  - Pattern: `frontend/src/stores/conversation-store.ts:160-199` — assistant-message persistence path that must preserve expanded source objects.
  - Pattern: `frontend/src/pages/PaperReaderPage.tsx:16-31` — reader state initialization that needs page/deep-link hydration.
  - Pattern: `frontend/src/pages/PaperReaderPage.tsx:118-130` — citation-driven reader/chat integration area.
  - Pattern: `frontend/src/components/reader/SelectionToolbar.tsx:32-65` — current contextual action style to mirror for citation actions if needed.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Uploading from the library uses the async endpoint and shows durable status/progress/retry UI without blocking the page.
  - [ ] Query results render citations from final structured `sources`, not from inferred page strings.
  - [ ] Clicking a citation opens the reader on the referenced paper and page.
  - [ ] Conversation reload from backend/local persistence keeps the expanded citation data intact.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Async upload progress is visible in the library UI
    Tool: Playwright
    Steps: open Papers page, upload `test-paper.pdf`, observe the job card/row, and wait for completion
    Expected: UI shows progress/stage updates, then converts to a completed paper state without full-page blocking alerts
    Evidence: .sisyphus/evidence/task-7-frontend-jobs.png

  Scenario: Citation click deep-links into reader
    Tool: Playwright
    Steps: ask a known-answer question on Query page, click a rendered citation chip/link, and inspect the reader route/state
    Expected: browser navigates to the cited paper reader with the referenced page preselected; no manual search is required
    Evidence: .sisyphus/evidence/task-7-frontend-jobs-error.png
  ```

  **Commit**: YES | Message: `feat(frontend): surface ingestion jobs and citation deep links` | Files: `frontend/src/pages/PapersPage.tsx`, `frontend/src/pages/QueryPage.tsx`, `frontend/src/pages/PaperReaderPage.tsx`, `frontend/src/lib/api.ts`, related components/tests

- [x] 8. Build an offline evaluation runner with version-aware and provenance-aware metrics

  **What to do**: Expand the current `tests/evaluation/retrieval_eval.py` script into a stable offline evaluation pipeline driven by fixture datasets and machine-readable JSON reports. Keep the default metric set deterministic and cheap: retrieval hit rate, page hit rate, keyword match rate, citation coverage rate, current-version leak rate, and failed-query rate. Make the runner CI-friendly, emit non-zero exit status when thresholds are missed, and store artifacts in a predictable path.
  **Must NOT do**: Do not require online judge models, LangSmith, or paid APIs for the default pipeline. Do not make evaluation results depend on nondeterministic timestamps/random seeds. Do not silently pass if no papers/dataset are available.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: combines evaluation design, reproducibility, and CI integration.
  - Skills: `[]` — no extra skill required.
  - Omitted: `[]` — no specialty intentionally omitted.

  **Parallelization**: Can Parallel: PARTIAL | Wave 2 | Blocks: 9, 10 | Blocked By: 1, 5, 6

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `tests/evaluation/retrieval_eval.py:14-160` — current seed script and existing metric/report structure.
  - Pattern: `src/rag/vector_store.py:212-253` — retrieval path whose outputs drive deterministic metrics.
  - Pattern: `api/schemas.py:123-173` — structured source/message schema to validate citation coverage.
  - Pattern: `src/agent/evidence_builder.py:170-246` — routed evidence surface to align provenance-aware metrics with actual final evidence.
  - Pattern: `config/settings.py:45-68` — retrieval knobs that evaluation runs may override explicitly.

  **Acceptance Criteria** (agent-executable only):
  - [ ] A single documented command runs the offline evaluation against a fixture dataset and writes a JSON report.
  - [ ] The JSON report includes deterministic metrics for retrieval, citation coverage, and current-version leakage.
  - [ ] The runner exits non-zero when configured thresholds are missed or the dataset/index is unavailable.
  - [ ] CI can consume the report path without custom manual steps.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: Offline evaluation produces machine-readable metrics
    Tool: Bash
    Steps: run the documented evaluation command against the fixture dataset and inspect the JSON output
    Expected: report file exists and contains retrieval hit rate, citation coverage rate, current-version leak rate, and threshold verdicts
    Evidence: .sisyphus/evidence/task-8-evaluation.json

  Scenario: Regression threshold failure returns non-zero status
    Tool: Bash
    Steps: run the evaluator with an intentionally impossible threshold or broken fixture dataset
    Expected: command exits non-zero and emits a sanitized failure summary rather than passing silently
    Evidence: .sisyphus/evidence/task-8-evaluation-error.txt
  ```

  **Commit**: YES | Message: `feat(eval): add deterministic offline regression evaluation` | Files: `tests/evaluation/**`, optional helper modules, docs/comments, tests

- [x] 9. Add regression tests covering jobs, versioning, provenance, and evaluation gates

  **What to do**: Use the Task-1 harness to add focused unit/integration coverage for the new roadmap capabilities. Cover: job state transitions, retry rules, staged-file retention, version-current flipping, retrieval filtering by current version, provenance schema persistence, and evaluation-runner pass/fail behavior. Include integration tests that hit FastAPI endpoints end-to-end with fakes/mocks where GPU/Qdrant/LLM calls would otherwise make tests flaky.
  **Must NOT do**: Do not rely on external APIs in default test runs. Do not leave the new features validated only by manual curl commands. Do not test only happy paths.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: broad regression coverage across API, service, and evaluation surfaces.
  - Skills: `[]` — no extra skill required.
  - Omitted: `[]` — no specialty intentionally omitted.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 10 | Blocked By: 3, 4, 5, 6, 7, 8

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `api/routes/papers.py:20-105` — upload/list/detail/chunk/pdf/toc endpoints to regression test around async + version-aware behavior.
  - Pattern: `api/routes/query.py:21-56` — query route whose final payload must now carry structured provenance.
  - Pattern: `api/services/query_service.py:23-52` — SSE event mapping to assert final provenance shape.
  - Pattern: `api/services/paper_service.py:54-275` — ingest/list/chunk/toc flows that now depend on jobs and versions.
  - Pattern: `src/rag/vector_store.py:331-445` — metadata fetch/count/delete helpers to verify current-version filtering.
  - Pattern: `tests/evaluation/retrieval_eval.py:44-108` — seed assertions to evolve into gated regression tests.

  **Acceptance Criteria** (agent-executable only):
  - [ ] Backend test suite includes unit + integration coverage for each of the four new backend capability areas.
  - [ ] At least one integration test verifies async upload → job polling → completed result end-to-end.
  - [ ] At least one integration test verifies query provenance payload shape end-to-end.
  - [ ] Evaluation-runner success and failure exit codes are both covered by tests.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: New regression suite passes end-to-end
    Tool: Bash
    Steps: run `pytest tests -q`
    Expected: tests covering jobs, versioning, provenance, and evaluation all pass with no flaky external dependency failures
    Evidence: .sisyphus/evidence/task-9-regression.txt

  Scenario: Failure-path assertions are enforced
    Tool: Bash
    Steps: run a targeted failure-path subset such as `pytest tests -q -k "retry or failed or version_leak"`
    Expected: the targeted suite passes and proves failure/edge-path coverage exists for retry/version/citation regressions
    Evidence: .sisyphus/evidence/task-9-regression-error.txt
  ```

  **Commit**: YES | Message: `test(regression): cover jobs versioning provenance and evaluation` | Files: `tests/**`, optional frontend helper tests

- [x] 10. Add GitHub Actions quality gates for backend, evaluation, and frontend verification

  **What to do**: Add a CI workflow that runs on pull requests and pushes to the main development branch, provisions the minimum dependencies needed for deterministic verification, and executes backend lint/tests, offline evaluation, and frontend lint/build. Prefer mocked or fixture-driven tests by default; if a live Qdrant service is required for a subset, provision it as a GitHub Actions service container. Publish evaluation JSON and coverage artifacts for failed runs.
  **Must NOT do**: Do not require GPU runners. Do not run real model downloads in CI. Do not make CI green when evaluation thresholds fail.

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: bounded automation/config task after the underlying checks already exist.
  - Skills: `[]` — no extra skill required.
  - Omitted: `[]` — no specialty intentionally omitted.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: F1-F4 | Blocked By: 1, 8, 9

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `README.md` — documented backend/frontend commands that CI should reflect.
  - Pattern: `config/settings.py:27-71` — env-driven knobs CI must override for deterministic execution.
  - Pattern: `api/main.py:30-60` — app entrypoint used by API smoke/integration tests.
  - Pattern: `frontend/README.md` — current frontend lint/build command expectations.
  - Pattern: `tests/evaluation/retrieval_eval.py:125-156` — report-writing flow whose output should become a CI artifact.

  **Acceptance Criteria** (agent-executable only):
  - [ ] CI workflow runs backend lint, backend tests, offline evaluation, frontend lint, and frontend build on every PR/push target.
  - [ ] CI uploads coverage/evaluation artifacts on failure.
  - [ ] CI fails when pytest fails, evaluation thresholds fail, or frontend lint/build fails.
  - [ ] CI configuration documents the minimum environment variables/services it expects.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```
  Scenario: CI workflow succeeds on the feature branch
    Tool: Bash
    Steps: trigger the workflow on the working branch and wait for completion using GitHub CLI
    Expected: all configured jobs complete successfully and artifacts are available when applicable
    Evidence: .sisyphus/evidence/task-10-ci.txt

  Scenario: CI fails on evaluation regression
    Tool: Bash
    Steps: temporarily run the workflow or local CI-equivalent command with an impossible evaluation threshold configuration
    Expected: the evaluation step fails, workflow/job status is red, and the failure artifact/log identifies the threshold miss
    Evidence: .sisyphus/evidence/task-10-ci-error.txt
  ```

  **Commit**: YES | Message: `ci: add automated quality gates for roadmap features` | Files: `.github/workflows/**`, optional helper scripts/config

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. Real Manual QA — unspecified-high (+ playwright if UI)
- [ ] F4. Scope Fidelity Check — deep

## Commit Strategy
- Prefer one commit per numbered task after its acceptance criteria pass.
- Suggested sequence:
  1. `test(infra): add backend/frontend test harness for roadmap work`
  2. `feat(api): add paper version and ingestion job persistence`
  3. `feat(api): add async ingestion status and retry endpoints`
  4. `feat(ingest): report ingestion progress and failure states`
  5. `feat(agent): emit structured provenance in query responses`
  6. `feat(rag): add version-aware reindex and current-version filtering`
  7. `feat(frontend): surface ingestion jobs and citation deep links`
  8. `feat(eval): add offline regression evaluation pipeline`
  9. `test(regression): cover jobs versioning citations and evaluation`
  10. `ci: add automated backend and frontend quality gates`

## Success Criteria
- Uploading a PDF via the new async flow returns immediately and produces durable job records.
- Failed ingestion jobs can be retried without leaving orphaned files or duplicate current-version chunks.
- Reindexing the same paper creates a new version while default retrieval only surfaces current-version evidence.
- Query responses expose structured provenance and frontend users can jump from a citation to the correct paper/page.
- A repeatable offline evaluation command produces JSON metrics and fails CI when regression thresholds are missed.
- Backend tests, frontend lint/build, and CI all run without manual intervention.
