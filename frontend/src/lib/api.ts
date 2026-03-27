const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api"

export interface PaperItem {
  pdf_name: string
  title: string
  authors: string
  chunk_count: number
  created_at?: string
}

export interface PaperDetail {
  pdf_name: string
  title: string
  authors: string
  chunk_count: number
  metadata: Record<string, unknown>
}

export interface ChunkItem {
  id: string
  content: string
  chunk_type: string
  page_idx?: number
  heading?: string
  score?: number
  image?: string
}

export interface ChunkListResponse {
  chunks: ChunkItem[]
  total: number
  page: number
  limit: number
}

export interface QueryRequest {
  question: string
  conversation_id?: string
  history?: MessageHistory[]
}

export interface MessageHistory {
  role: string
  content: string
}

export interface AgentStep {
  type: string
  tool?: string
  text?: string
  count?: number
  pages?: string[]
}

export interface Source {
  pdf_name: string
  page: number
  type: string
  chunk_id?: string
  paper_version?: number
  heading?: string
  supporting_text?: string
}

export interface MessageResponse {
  id: string
  role: string
  content: string
  steps?: AgentStep[]
  sources?: Source[]
  created_at: number
}

export interface ConversationListItem {
  id: string
  title: string
  created_at: number
  updated_at: number
  message_count: number
}

export interface ConversationListResponse {
  conversations: ConversationListItem[]
}

export interface ConversationDetail {
  id: string
  title: string
  created_at: number
  updated_at: number
  messages: MessageResponse[]
}

export async function fetchPapers(): Promise<PaperItem[]> {
  const res = await fetch(`${API_BASE}/papers`)
  if (!res.ok) throw new Error("Failed to fetch papers")
  const data = await res.json()
  return data.papers
}

export async function fetchPaper(pdfName: string): Promise<PaperDetail> {
  const res = await fetch(`${API_BASE}/papers/${pdfName}`)
  if (!res.ok) throw new Error("Failed to fetch paper")
  return res.json()
}

export async function deletePaper(pdfName: string): Promise<void> {
  const res = await fetch(`${API_BASE}/papers/${pdfName}`, { method: "DELETE" })
  if (!res.ok) throw new Error("Failed to delete paper")
}

export async function fetchChunks(
  pdfName: string,
  page = 1,
  limit = 20,
  type?: string
): Promise<ChunkListResponse> {
  const params = new URLSearchParams({ page: String(page), limit: String(limit) })
  if (type) params.set("type", type)
  const res = await fetch(`${API_BASE}/papers/${pdfName}/chunks?${params}`)
  if (!res.ok) throw new Error("Failed to fetch chunks")
  return res.json()
}

export async function uploadPaper(file: File): Promise<{ pdf_name: string; title: string; authors: string; chunk_count: number }> {
  const formData = new FormData()
  formData.append("file", file)
  const res = await fetch(`${API_BASE}/papers/upload`, {
    method: "POST",
    body: formData,
  })
  if (!res.ok) throw new Error("Failed to upload paper")
  return res.json()
}

export type SSEEventType = 
  | "status" 
  | "tool_call" 
  | "tool_result" 
  | "agent_observation" 
  | "agent_visual_context" 
  | "answer_started" 
  | "answer_token" 
  | "answer_done"

export interface SSEEvent {
  type: SSEEventType
  [key: string]: unknown
}

export interface TOCItem {
  id: string
  level: number
  text: string
  page_idx: number
  chunk_type: string  // "section" | "image" | "table"
}

export interface TOCResponse {
  items: TOCItem[]
  total_pages: number
}

export function getPdfUrl(pdfName: string): string {
  return `${API_BASE}/papers/${pdfName}/pdf`
}

export async function fetchToc(pdfName: string): Promise<TOCResponse> {
  const res = await fetch(`${API_BASE}/papers/${pdfName}/toc`)
  if (!res.ok) throw new Error("Failed to fetch TOC")
  return res.json()
}

export function createQueryStream(
  question: string,
  onEvent: (event: SSEEvent) => void,
  onError: (error: Error) => void,
  conversationId?: string,
  history?: MessageHistory[]
): () => void {
  const controller = new AbortController()
  
  const body: QueryRequest = { question }
  if (conversationId) {
    body.conversation_id = conversationId
  }
  if (history && history.length > 0) {
    body.history = history
  }
  
  fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then((res) => {
      if (!res.ok) throw new Error("Query failed")
      const reader = res.body?.getReader()
      if (!reader) throw new Error("No response body")
      
      const decoder = new TextDecoder()
      let buffer = ""
      let currentEvent = ""
      
      function read() {
        reader!.read().then(({ done, value }) => {
          if (done) {
            controller.abort()
            return
          }
          
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split("\n")
          buffer = lines.pop() || ""
          
          for (const line of lines) {
            if (line.startsWith("event: ")) {
              currentEvent = line.slice(7).trim()
            } else if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6))
                if (currentEvent) {
                  data.type = currentEvent
                  currentEvent = "" // Reset after use
                }
                onEvent(data as SSEEvent)
              } catch {
                // Skip invalid JSON
              }
            }
          }
          
          read()
        })
      }
      
      read()
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        onError(err)
      }
    })
  
  return () => controller.abort()
}

export async function fetchConversations(): Promise<ConversationListResponse> {
  const res = await fetch(`${API_BASE}/conversations`)
  if (!res.ok) throw new Error("Failed to fetch conversations")
  return res.json()
}

export async function fetchConversation(id: string): Promise<ConversationDetail> {
  const res = await fetch(`${API_BASE}/conversations/${id}`)
  if (!res.ok) throw new Error("Failed to fetch conversation")
  return res.json()
}

export async function createConversation(id: string, title = "New Chat"): Promise<void> {
  const res = await fetch(`${API_BASE}/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, title }),
  })
  if (!res.ok) throw new Error("Failed to create conversation")
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/conversations/${id}`, { method: "DELETE" })
  if (!res.ok) throw new Error("Failed to delete conversation")
}

export async function addMessage(
  conversationId: string,
  message: Omit<MessageResponse, "id">
): Promise<MessageResponse> {
  const res = await fetch(`${API_BASE}/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
      ...message,
    }),
  })
  if (!res.ok) throw new Error("Failed to add message")
  return res.json()
}

// Async upload job types
export interface IngestionJobResult {
  pdf_name: string
  title: string
  authors: string
  chunk_count: number
  paper_version?: number
}

export interface IngestionJobResponse {
  job_id: string
  status: "pending" | "processing" | "completed" | "failed"
  stage: string
  progress: number
  retry_count: number
  error_message?: string
  result?: IngestionJobResult
  created_at: number
  updated_at: number
}

export interface IngestionJobListItem {
  job_id: string
  pdf_name: string
  status: "pending" | "processing" | "completed" | "failed"
  stage: string
  progress: number
  retry_count: number
  created_at: number
  updated_at: number
}

export interface IngestionJobListResponse {
  jobs: IngestionJobListItem[]
  total: number
}

export interface IngestionJobCreateResponse {
  job_id: string
  status: string
  filename: string
  message: string
}

export interface IngestionJobRetryResponse {
  job_id: string
  status: string
  message: string
}

// Async upload API methods
export async function uploadPaperAsync(file: File): Promise<IngestionJobCreateResponse> {
  const formData = new FormData()
  formData.append("file", file)
  const res = await fetch(`${API_BASE}/papers/uploads`, {
    method: "POST",
    body: formData,
  })
  if (!res.ok) throw new Error("Failed to start async upload")
  return res.json()
}

export async function getJobStatus(jobId: string): Promise<IngestionJobResponse> {
  const res = await fetch(`${API_BASE}/papers/uploads/${jobId}`)
  if (!res.ok) throw new Error("Failed to get job status")
  return res.json()
}

export async function listJobs(limit = 20): Promise<IngestionJobListResponse> {
  const res = await fetch(`${API_BASE}/papers/uploads?limit=${limit}`)
  if (!res.ok) throw new Error("Failed to list jobs")
  return res.json()
}

export async function retryJob(jobId: string): Promise<IngestionJobRetryResponse> {
  const res = await fetch(`${API_BASE}/papers/uploads/${jobId}/retry`, {
    method: "POST",
  })
  if (!res.ok) throw new Error("Failed to retry job")
  return res.json()
}

// Paper version types
export interface PaperVersion {
  id: number
  version_number: number
  source_hash: string
  created_at: number
  is_current: boolean
}

// Paper version API methods
export async function fetchVersions(pdfName: string): Promise<PaperVersion[]> {
  const res = await fetch(`${API_BASE}/papers/${encodeURIComponent(pdfName)}/versions`)
  if (!res.ok) throw new Error("Failed to fetch versions")
  return res.json()
}

export async function reindexPaper(pdfName: string): Promise<void> {
  const res = await fetch(`${API_BASE}/papers/${encodeURIComponent(pdfName)}/reindex`, {
    method: "POST",
  })
  if (!res.ok) throw new Error("Failed to reindex paper")
}
