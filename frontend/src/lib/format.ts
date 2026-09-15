/** Formatting helpers. */

/**
 * Format paisa as a PKR string.
 *
 * Deliberately NOT Intl.NumberFormat with style:'currency', currency:'PKR'.
 * That renders as "PKR 24,999", "Rs 24,999" or "₨ 24,999" depending on the ICU
 * version, the browser and the OS, so the same price would read differently
 * for different customers and would not match what the backend renders.
 * The prefix is hardcoded, and grouping comes from a locale that is stable.
 */
export function formatPkr(paisa: number | null | undefined, withDecimals = false): string {
  if (paisa === null || paisa === undefined) return 'Rs 0'
  const negative = paisa < 0
  const amount = Math.abs(paisa)

  let body: string
  if (withDecimals) {
    body = (amount / 100).toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  } else {
    body = Math.round(amount / 100).toLocaleString('en-US')
  }
  return `${negative ? '-' : ''}Rs ${body}`
}

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return ''
  const date = typeof value === 'string' ? new Date(value) : value
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'Asia/Karachi',
  })
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return ''
  const date = typeof value === 'string' ? new Date(value) : value
  return date.toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Karachi',
  })
}

export function relativeTime(value: string | Date | null | undefined): string {
  if (!value) return ''
  const date = typeof value === 'string' ? new Date(value) : value
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)

  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, 'second'],
    [3600, 'minute'],
    [86400, 'hour'],
    [604800, 'day'],
    [2629800, 'week'],
    [31557600, 'month'],
  ]
  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

  let previous = 1
  for (const [limit, unit] of units) {
    if (seconds < limit) return formatter.format(-Math.round(seconds / previous), unit)
    previous = limit
  }
  return formatter.format(-Math.round(seconds / 31557600), 'year')
}

export function formatDimensions(d: Record<string, number | null> | null): string {
  if (!d) return ''
  const parts = [d.length_cm, d.width_cm, d.height_cm].filter(Boolean)
  return parts.length ? `${parts.join(' × ')} cm` : ''
}

export function formatWeight(grams: number | null | undefined): string {
  if (!grams) return ''
  return grams >= 1000 ? `${(grams / 1000).toFixed(1)} kg` : `${grams} g`
}
