import { useCallback, useEffect, useState } from 'react'

export type Theme = 'light' | 'dark' | 'system'

const KEY = 'wc-theme'

function read(): Theme {
  try {
    const saved = localStorage.getItem(KEY)
    return saved === 'light' || saved === 'dark' ? saved : 'system'
  } catch {
    return 'system'
  }
}

/**
 * Tri-state theme: light, dark, or follow the system.
 *
 * The initial paint is handled by an inline script in index.html, before React
 * mounts. Doing it here alone would flash the light theme on every load, which
 * is the quickest way to make a site feel cheap.
 */
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(read)

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next)
    try {
      if (next === 'system') {
        localStorage.removeItem(KEY)
        document.documentElement.removeAttribute('data-theme')
      } else {
        localStorage.setItem(KEY, next)
        document.documentElement.setAttribute('data-theme', next)
      }
    } catch {
      /* storage blocked: the attribute still applies for this session */
      if (next === 'system') document.documentElement.removeAttribute('data-theme')
      else document.documentElement.setAttribute('data-theme', next)
    }
  }, [])

  // Keep the browser UI (address bar) in step with the resolved theme.
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      const dark = theme === 'dark' || (theme === 'system' && media.matches)
      document
        .querySelector('meta[name="theme-color"]')
        ?.setAttribute('content', dark ? '#16120D' : '#FBF7F0')
    }
    apply()
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [theme])

  return { theme, setTheme }
}

/** True when the visitor has asked for less motion. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReduced(media.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])
  return reduced
}
