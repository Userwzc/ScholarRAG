import { create } from "zustand"
import { persist } from "zustand/middleware"
import {
  fetchConversations,
  fetchConversation,
  createConversation as createConversationAPI,
  deleteConversation as deleteConversationAPI,
  addMessage as addMessageAPI,
} from "../lib/api"

export interface AgentStep {
  type: "thinking" | "tool_call" | "tool_result" | "observation" | "answer" | "agent_visual_context"
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

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  steps?: AgentStep[]
  sources?: Source[]
  createdAt: number
}

export interface Conversation {
  id: string
  title: string
  messages: Message[]
  createdAt: number
  updatedAt: number
}

interface ConversationState {
  conversations: Conversation[]
  activeConversationId: string | null
  sidebarOpen: boolean
  isSynced: boolean
  
  createConversation: () => Promise<string>
  deleteConversation: (id: string) => Promise<void>
  setActiveConversation: (id: string | null) => void
  loadConversationMessages: (id: string) => Promise<void>
  addMessage: (conversationId: string, message: Message) => Promise<void>
  updateConversationTitle: (id: string, title: string) => void
  clearAllConversations: () => void
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  syncWithBackend: () => Promise<void>
}

const generateId = () => `conv_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`

const generateTitle = (firstMessage: string): string => {
  const maxLength = 40
  const cleaned = firstMessage.replace(/\n/g, " ").trim()
  if (cleaned.length <= maxLength) return cleaned
  return cleaned.substring(0, maxLength) + "..."
}

export const useConversationStore = create<ConversationState>()(
  persist(
    (set, get) => ({
      conversations: [],
      activeConversationId: null,
      sidebarOpen: true,
      isSynced: false,

      createConversation: async () => {
        const id = generateId()
        const newConversation: Conversation = {
          id,
          title: "New Chat",
          messages: [],
          createdAt: Date.now(),
          updatedAt: Date.now(),
        }
        set((state) => ({
          conversations: [newConversation, ...state.conversations],
          activeConversationId: id,
        }))
        
        // 同步到后端
        try {
          await createConversationAPI(id, "New Chat")
        } catch (error) {
          console.error("Failed to sync conversation to backend:", error)
        }
        
        return id
      },

      deleteConversation: async (id) => {
        set((state) => {
          const newConversations = state.conversations.filter((c) => c.id !== id)
          const newActiveId = state.activeConversationId === id
            ? (newConversations.length > 0 ? newConversations[0].id : null)
            : state.activeConversationId
          return {
            conversations: newConversations,
            activeConversationId: newActiveId,
          }
        })
        
        // 同步到后端
        try {
          await deleteConversationAPI(id)
        } catch (error) {
          console.error("Failed to delete conversation from backend:", error)
        }
      },

      setActiveConversation: (id) => {
        set({ activeConversationId: id })
      },

      loadConversationMessages: async (id) => {
        const conv = get().conversations.find((c) => c.id === id)
        if (!conv || conv.messages.length > 0) return
        
        try {
          const detail = await fetchConversation(id)
          const messages: Message[] = detail.messages.map((m) => ({
            id: m.id,
            role: m.role as "user" | "assistant",
            content: m.content,
            steps: m.steps?.map((s) => ({
              type: s.type as AgentStep["type"],
              tool: s.tool,
              text: s.text,
              count: s.count,
              pages: s.pages,
            })),
            sources: m.sources?.map((s) => ({
              pdf_name: s.pdf_name,
              page: s.page,
              type: s.type,
              chunk_id: s.chunk_id,
              paper_version: s.paper_version,
              heading: s.heading,
              supporting_text: s.supporting_text,
            })),
            createdAt: m.created_at,
          }))
          
          set((state) => ({
            conversations: state.conversations.map((c) =>
              c.id === id ? { ...c, messages } : c
            ),
          }))
        } catch (error) {
          console.error("Failed to load conversation messages:", error)
        }
      },

      addMessage: async (conversationId, message) => {
        set((state) => {
          const conversations = state.conversations.map((conv) => {
            if (conv.id !== conversationId) return conv

            const newMessages = [...conv.messages, message]
            let newTitle = conv.title

            if (conv.messages.length === 0 && message.role === "user") {
              newTitle = generateTitle(message.content)
            }

            return {
              ...conv,
              messages: newMessages,
              title: newTitle,
              updatedAt: Date.now(),
            }
          })

          conversations.sort((a, b) => b.updatedAt - a.updatedAt)

          return { conversations }
        })
        
        // 同步助手消息到后端
        if (message.role === "assistant") {
          try {
            await addMessageAPI(conversationId, {
              role: message.role,
              content: message.content,
              steps: message.steps,
              sources: message.sources,
              created_at: message.createdAt,
            })
          } catch (error) {
            console.error("Failed to sync message to backend:", error)
          }
        }
      },

      updateConversationTitle: (id, title) => {
        set((state) => ({
          conversations: state.conversations.map((conv) =>
            conv.id === id ? { ...conv, title, updatedAt: Date.now() } : conv
          ),
        }))
      },

      clearAllConversations: () => {
        set({ conversations: [], activeConversationId: null })
      },

      toggleSidebar: () => {
        set((state) => ({ sidebarOpen: !state.sidebarOpen }))
      },

      setSidebarOpen: (open) => {
        set({ sidebarOpen: open })
      },

      syncWithBackend: async () => {
        // 避免重复同步
        if (get().isSynced) return
        
        try {
          const response = await fetchConversations()
          
          // 将后端数据转换为前端格式
          const backendConversations: Conversation[] = response.conversations.map((item) => ({
            id: item.id,
            title: item.title,
            messages: [], // 列表接口不返回消息，需要单独获取
            createdAt: item.created_at,
            updatedAt: item.updated_at,
          }))
          
          // 合并本地和后端数据（以 updatedAt 为准去重）
          const localConversations = get().conversations
          const mergedMap = new Map<string, Conversation>()
          
          // 先添加本地数据
          for (const conv of localConversations) {
            mergedMap.set(conv.id, conv)
          }
          
          // 用后端数据覆盖（后端数据更新）
          for (const conv of backendConversations) {
            const existing = mergedMap.get(conv.id)
            if (!existing || conv.updatedAt > existing.updatedAt) {
              mergedMap.set(conv.id, conv)
            }
          }
          
          const mergedConversations = Array.from(mergedMap.values())
            .sort((a, b) => b.updatedAt - a.updatedAt)
          
          set({ 
            conversations: mergedConversations, 
            isSynced: true,
            activeConversationId: mergedConversations.length > 0 
              ? (get().activeConversationId || mergedConversations[0].id)
              : null,
          })
        } catch (error) {
          console.error("Failed to sync with backend:", error)
          // 即使同步失败，也标记为已尝试，避免无限重试
          set({ isSynced: true })
        }
      },
    }),
    {
      name: "scholar-rag-conversations",
      version: 1,
    }
  )
)
