/**
 * API client.
 *
 * Two things here are worth understanding:
 *
 * 1. The access token lives in memory, never in localStorage. A token sitting
 *    in localStorage is readable by any XSS on the page. The refresh token is
 *    persisted because it has to survive a reload, and it is single-use and
 *    rotating, so a stolen one is good for at most one request.
 *
 * 2. Refresh is single-flight. When a page fires six requests at once and the
 *    token has just expired, all six get a 401. Without a shared promise they
 *    would all try to refresh, five would present an already-rotated token,
 *    and the server would treat that as replay and log the user out. So the
 *    first 401 starts the refresh and the rest wait on the same promise.
 */

const GUEST_KEY = 'wc-guest-token'
const REFRESH_KEY = 'wc-refresh-token'

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: Record<string, unknown>,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  /** Field errors from a 422, shaped for react-hook-form. */
  get fieldErrors(): Record<string, string> {
    const fields = this.details?.fields
    return (fields && typeof fields === 'object' ? fields : {}) as Record<string, string>
  }
}

let accessToken: string | null = null
let refreshPromise: Promise<boolean> | null = null

type Listener = (authenticated: boolean) => void
const listeners = new Set<Listener>()

export const auth = {
  get token() {
    return accessToken
  },
  get isAuthenticated() {
    return accessToken !== null
  },
  setTokens(access: string, refresh: string) {
    accessToken = access
    safeSet(REFRESH_KEY, refresh)
    listeners.forEach((fn) => fn(true))
  },
  clear() {
    accessToken = null
    safeRemove(REFRESH_KEY)
    listeners.forEach((fn) => fn(false))
  },
  get refreshToken() {
    return safeGet(REFRESH_KEY)
  },
  subscribe(fn: Listener) {
    listeners.add(fn)
    return () => listeners.delete(fn)
  },
}

/* localStorage throws in private mode and when site data is blocked, and the
   whole app must keep working when it does. */
function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function safeSet(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* ignore */
  }
}
function safeRemove(key: string) {
  try {
    localStorage.removeItem(key)
  } catch {
    /* ignore */
  }
}

export const guest = {
  get token() {
    return safeGet(GUEST_KEY)
  },
  set(token: string) {
    safeSet(GUEST_KEY, token)
  },
  clear() {
    safeRemove(GUEST_KEY)
  },
}

async function refreshAccessToken(): Promise<boolean> {
  const token = auth.refreshToken
  if (!token) return false

  try {
    const response = await fetch('/api/v1/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: token }),
    })
    if (!response.ok) {
      auth.clear()
      return false
    }
    const data = await response.json()
    auth.setTokens(data.access_token, data.refresh_token)
    return true
  } catch {
    auth.clear()
    return false
  }
}

/** Single-flight: concurrent callers share one refresh. */
function refreshOnce(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = refreshAccessToken().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  /** Set internally to stop a refresh loop. */
  _retried?: boolean
}

export async function api<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { body, _retried, headers: extraHeaders, ...rest } = options

  const headers = new Headers(extraHeaders)
  if (body !== undefined && !(body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)

  // Guests carry their own identity header so cart and wishlist work without
  // an account.
  const guestToken = guest.token
  if (guestToken && !accessToken) headers.set('X-Guest-Token', guestToken)

  const url = path.startsWith('/api') ? path : `/api/v1${path}`

  const response = await fetch(url, {
    ...rest,
    headers,
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
  })

  if (response.status === 401 && !_retried && auth.refreshToken) {
    const refreshed = await refreshOnce()
    if (refreshed) {
      return api<T>(path, { ...options, _retried: true })
    }
  }

  if (response.status === 204) return undefined as T

  const text = await response.text()
  const payload = text ? JSON.parse(text) : null

  if (!response.ok) {
    const error = payload?.error ?? {}
    throw new ApiError(
      response.status,
      error.code ?? 'unknown_error',
      error.message ?? 'Something went wrong. Please try again.',
      error.details,
    )
  }

  return payload as T
}

export const get = <T>(path: string, params?: Record<string, unknown>) => {
  const query = params ? buildQuery(params) : ''
  return api<T>(`${path}${query}`)
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: 'POST', body })

export const patch = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: 'PATCH', body })

export const put = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: 'PUT', body })

export const del = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: 'DELETE', body })

/**
 * Download a file from an authenticated endpoint.
 *
 * A plain <a href> is a top-level navigation that cannot carry the in-memory
 * access token, so it lands on a JSON error for any endpoint behind auth. This
 * fetches with the token, then hands the blob to a programmatic anchor.
 */
export async function download(path: string, filename: string): Promise<void> {
  const headers = new Headers()
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  const url = path.startsWith('/api') ? path : `/api/v1${path}`

  let response = await fetch(url, { headers })
  if (response.status === 401 && auth.refreshToken && (await refreshOnce())) {
    const retryHeaders = new Headers()
    if (accessToken) retryHeaders.set('Authorization', `Bearer ${accessToken}`)
    response = await fetch(url, { headers: retryHeaders })
  }
  if (!response.ok) {
    throw new ApiError(response.status, 'download_failed', 'Could not download the file.')
  }

  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
}

/** Arrays repeat the key, which is what FastAPI's Query(list) expects. */
export function buildQuery(params: Record<string, unknown>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) {
      value.forEach((entry) => search.append(key, String(entry)))
    } else if (typeof value === 'boolean') {
      if (value) search.set(key, 'true')
    } else {
      search.set(key, String(value))
    }
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}

/** Make sure a guest identity exists before using the cart. */
export async function ensureGuestSession(): Promise<string | null> {
  if (auth.isAuthenticated) return null
  const existing = guest.token
  if (existing) return existing

  try {
    const data = await post<{ guest_token: string }>('/auth/guest')
    guest.set(data.guest_token)
    return data.guest_token
  } catch {
    return null
  }
}

/** Restore a session on boot, if a refresh token survived the reload. */
export async function bootstrapAuth(): Promise<boolean> {
  if (!auth.refreshToken) return false
  return refreshOnce()
}
