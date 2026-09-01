import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";

export type Theme = "light" | "dark";
const KEY = "ccr_theme";

function initialTheme(): Theme {
  const saved = localStorage.getItem(KEY) as Theme | null;
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function apply(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  localStorage.setItem(KEY, theme);
}

interface ThemeCtx {
  theme: Theme;
  toggle: () => void;
}

const Ctx = createContext<ThemeCtx | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    const t = initialTheme();
    apply(t);
    return t;
  });

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      apply(next);
      return next;
    });
  }, []);

  return <Ctx.Provider value={{ theme, toggle }}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
