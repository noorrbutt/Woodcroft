import { useEffect, useState } from 'react'

/**
 * Resolve the chart colour tokens to concrete hex values.
 *
 * Recharts sets `stroke` and `fill` as SVG presentation attributes, and
 * `var()` is not substituted there. Passing `var(--wc-chart-1)` straight
 * through silently produces an invisible line: the axes and the computed
 * domain all render correctly, so the chart looks like it has no data rather
 * than like it has a colour problem.
 *
 * Reading the computed value keeps the palette in one place (theme.css) while
 * still handing Recharts something it can actually paint. The values are
 * re-read when the theme changes, so dark mode gets its own set.
 */

const TOKENS = [
  '--wc-chart-1',
  '--wc-chart-2',
  '--wc-chart-3',
  '--wc-chart-4',
  '--wc-chart-5',
  '--wc-chart-6',
] as const

const AXIS_TOKENS = {
  grid: '--wc-border-subtle',
  axis: '--wc-text-tertiary',
  surface: '--wc-surface-raised',
  border: '--wc-border-subtle',
  text: '--wc-text',
} as const

export interface ChartColors {
  series: string[]
  grid: string
  axis: string
  surface: string
  border: string
  text: string
}

function read(): ChartColors {
  const styles = getComputedStyle(document.documentElement)
  const value = (token: string, fallback: string) =>
    styles.getPropertyValue(token).trim() || fallback

  return {
    series: TOKENS.map((token, index) =>
      value(token, ['#1F3D2F', '#C9963F', '#8A6B4C', '#74A088', '#A33A2A', '#2F5F82'][index]!),
    ),
    grid: value(AXIS_TOKENS.grid, '#E8DFD1'),
    axis: value(AXIS_TOKENS.axis, '#8A7862'),
    surface: value(AXIS_TOKENS.surface, '#FFFFFF'),
    border: value(AXIS_TOKENS.border, '#E8DFD1'),
    text: value(AXIS_TOKENS.text, '#2E2419'),
  }
}

export function useChartColors(): ChartColors {
  const [colors, setColors] = useState<ChartColors>(read)

  useEffect(() => {
    const refresh = () => setColors(read())

    // The explicit toggle stamps data-theme on <html>.
    const observer = new MutationObserver(refresh)
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })

    // And "system" follows the OS, which can change while the page is open.
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    media.addEventListener('change', refresh)

    return () => {
      observer.disconnect()
      media.removeEventListener('change', refresh)
    }
  }, [])

  return colors
}
