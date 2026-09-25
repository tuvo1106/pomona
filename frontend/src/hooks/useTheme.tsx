import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type Theme = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'pomona-theme'

interface ThemeContextValue {
  theme: Theme
  /** 'system' resolved against the OS preference -- always a concrete light or dark. */
  resolvedTheme: 'light' | 'dark'
  setTheme: (theme: Theme) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

function applyTheme(theme: Theme) {
  const root = document.documentElement
  root.classList.remove('light', 'dark')
  if (theme !== 'system') root.classList.add(theme)
  // theme === 'system': no class -- index.css's prefers-color-scheme media query takes over.
}

/** Points <meta name="theme-color"> at whatever `--background` currently resolves to, so the
 * browser's own chrome (a phone's address bar, an installed window's title bar) matches the
 * page instead of staying white behind a dark dashboard.
 *
 * Read from the live token rather than written as a pair of hex literals in index.html: a
 * copy of index.css drifts from it, and a static `media="(prefers-color-scheme: ...)"` pair
 * can't see an explicit choice that disagrees with the OS -- picking Dark on a light-mode
 * machine has to darken the chrome too. The tag is created on first use so the value has
 * exactly one source.
 *
 * The token goes in as authored, `oklch(...)` and all -- theme-color takes any CSS <color>.
 * A browser too old to parse it ignores the tag, which is what it did before this existed.
 */
function syncThemeColorMeta() {
  const background = getComputedStyle(document.documentElement)
    .getPropertyValue('--background')
    .trim()
  if (!background) return
  let meta = document.head.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
  if (!meta) {
    meta = document.createElement('meta')
    meta.name = 'theme-color'
    document.head.appendChild(meta)
  }
  meta.content = background
}

function readStoredTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system'
}

function useSystemPrefersDark(): boolean {
  const [prefersDark, setPrefersDark] = useState(
    () => window.matchMedia('(prefers-color-scheme: dark)').matches,
  )

  useEffect(() => {
    const mql = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => setPrefersDark(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])

  return prefersDark
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readStoredTheme)
  const systemPrefersDark = useSystemPrefersDark()
  const resolvedTheme = theme === 'system' ? (systemPrefersDark ? 'dark' : 'light') : theme

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  // Declared after applyTheme's effect so it reads the token *after* the class lands. Keyed on
  // the resolved theme, not `theme`, so an OS flip while on "system" -- which changes no class
  // at all -- still updates the tag.
  useEffect(() => {
    syncThemeColorMeta()
  }, [resolvedTheme])

  const setTheme = (next: Theme) => {
    localStorage.setItem(STORAGE_KEY, next)
    setThemeState(next)
  }

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider')
  return ctx
}

/** Resolves 'system' against the OS preference, for consumers (e.g. the routes map's tile
 * choice) that need a concrete light/dark rather than the three-way theme setting itself.
 * The provider resolves it once and shares it, so consumers don't each open their own
 * `matchMedia` listener.
 */
export function useResolvedTheme(): 'light' | 'dark' {
  return useTheme().resolvedTheme
}
