import { create } from "zustand"
import { persist } from "zustand/middleware"

interface ThemeState {
  theme: "light" | "dark"
  setTheme: (theme: "light" | "dark") => void
  toggleTheme: () => void
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: "light",
      setTheme: (theme) => {
        document.documentElement.classList.remove("light", "dark")
        document.documentElement.classList.add(theme)
        set({ theme })
      },
      toggleTheme: () =>
        set((state) => {
          const newTheme = state.theme === "light" ? "dark" : "light"
          document.documentElement.classList.remove("light", "dark")
          document.documentElement.classList.add(newTheme)
          return { theme: newTheme }
        }),
    }),
    { name: "theme-storage" }
  )
)
