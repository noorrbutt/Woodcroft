import { create } from 'zustand'
import { toast } from 'sonner'

import { auth, get, post } from '@/lib/api'
import type { AuthResponse, User } from '@/lib/types'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string, rememberMe?: boolean) => Promise<void>
  register: (input: {
    email: string
    password: string
    full_name: string
    phone?: string
    referral_code?: string
    email_marketing?: boolean
  }) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  setUser: (user: User | null) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,

  login: async (email, password, rememberMe = false) => {
    const data = await post<AuthResponse>('/auth/login', {
      email,
      password,
      remember_me: rememberMe,
    })
    auth.setTokens(data.tokens.access_token, data.tokens.refresh_token)
    set({ user: data.user, loading: false })
  },

  register: async (input) => {
    const data = await post<AuthResponse>('/auth/register', input)
    auth.setTokens(data.tokens.access_token, data.tokens.refresh_token)
    set({ user: data.user, loading: false })
  },

  logout: async () => {
    const refresh = auth.refreshToken
    // Fire and forget: the local session must end even if the call fails,
    // otherwise a network blip leaves someone apparently signed in.
    if (refresh) {
      post('/auth/logout', { refresh_token: refresh }).catch(() => {})
    }
    auth.clear()
    set({ user: null, loading: false })
    toast.success('Signed out')
  },

  refreshUser: async () => {
    if (!auth.isAuthenticated) {
      set({ user: null, loading: false })
      return
    }
    try {
      const user = await get<User>('/auth/me')
      set({ user, loading: false })
    } catch {
      set({ user: null, loading: false })
    }
  },

  setUser: (user) => set({ user, loading: false }),
}))

// Keep the store in step with token changes made by the API client, such as a
// refresh failing and clearing the session mid-session.
auth.subscribe((authenticated) => {
  if (!authenticated) useAuthStore.getState().setUser(null)
})
