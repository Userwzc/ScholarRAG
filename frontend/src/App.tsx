import { useEffect } from "react"
import { BrowserRouter, Routes, Route } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Header } from "./components/layout/Header"
import { useThemeStore } from "./stores/theme-store"
import QueryPage from "./pages/QueryPage"
import PapersPage from "./pages/PapersPage"
import PaperDetailPage from "./pages/PaperDetailPage"
import PaperReaderPage from "./pages/PaperReaderPage"

const queryClient = new QueryClient()

function App() {
  const { theme } = useThemeStore()

  useEffect(() => {
    document.documentElement.classList.remove("light", "dark")
    document.documentElement.classList.add(theme)
  }, [theme])

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen bg-background">
          <Header />
          <main>
            <Routes>
              <Route path="/" element={<QueryPage />} />
              <Route path="/papers" element={<PapersPage />} />
              <Route path="/papers/:pdfName" element={<PaperDetailPage />} />
              <Route path="/papers/:pdfName/read" element={<PaperReaderPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
