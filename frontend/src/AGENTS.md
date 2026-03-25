# AGENTS.md — Frontend

React 18 + TypeScript SPA：多模态 RAG 的现代化 Web 界面。

## Structure

```
frontend/src/
├── main.tsx              # React 应用入口
├── App.tsx               # 根组件，路由配置
├── pages/
│   ├── QueryPage.tsx     # 主查询界面（沉浸式聊天）
│   ├── PapersPage.tsx    # 论文列表
│   ├── PaperDetailPage.tsx
│   └── PaperReaderPage.tsx # PDF 阅读器
├── components/
│   ├── query/
│   │   ├── ThoughtProcess.tsx    # 可折叠思维过程
│   │   └── ConversationSidebar.tsx
│   ├── reader/
│   │   ├── PDFViewer.tsx         # PDF 渲染
│   │   ├── ChatPanel.tsx         # 阅读器内聊天
│   │   ├── TocSidebar.tsx        # 目录导航
│   │   └── SelectionToolbar.tsx  # 文本选择工具栏
│   ├── layout/
│   │   └── Header.tsx
│   └── ui/               # shadcn/ui 组件
├── stores/
│   ├── conversation-store.ts  # Zustand 状态管理
│   └── theme-store.ts
├── lib/
│   ├── api.ts            # API 客户端
│   └── utils.ts
└── index.css
```

## Key Patterns

### Component Conventions
- Functional components with explicit return types: `function Foo(): JSX.Element`
- PascalCase file names in `components/` or `pages/`
- Props destructuring in function signature

### State Management
```typescript
// Zustand store
export const useConversationStore = create<ConversationStore>((set, get) => ({
  conversations: [],
  // ...
}))

// Custom hooks: useThemeStore.ts in hooks/
```

### Server State
- 使用 `@tanstack/react-query` 进行服务器状态管理
- API 调用封装在 `lib/api.ts`

### LaTeX Support
- KaTeX 用于数学公式渲染
- `rehype-katex` + `remark-math` 插件

### PDF Integration
- `@react-pdf-viewer` 用于 PDF 渲染
- 支持跳转到引用页面

## Tech Stack

- React 19, TypeScript ~5.9
- Tailwind CSS 4.x, shadcn/ui
- Zustand 5.x (状态管理)
- React Query 5.x (服务器状态)
- KaTeX (LaTeX 渲染)
- Vite 8.x (构建工具)

## Commands

```bash
npm run dev     # http://localhost:5173
npm run build   # Production build
npm run lint    # ESLint
```
