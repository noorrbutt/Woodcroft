import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { Toaster } from 'sonner'

import '@fontsource-variable/fraunces'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import './styles/theme.css'
import './styles/base.css'

import { router } from './router'
import { bootstrapAuth } from './lib/api'
import { queryClient } from './lib/queryClient'
import { useAuthStore } from './features/auth/store'

/**
 * Restore the session before the first paint that could depend on it, so a
 * signed-in user does not briefly see the signed-out header.
 *
 * bootstrapAuth only exchanges the stored refresh token for an access token.
 * It does NOT load the user, and the auth store starts with loading = true.
 * Route guards block on that flag, so without the refreshUser call below both
 * /account and /admin sit on a spinner forever. refreshUser always clears the
 * flag, whether or not there was a session to restore.
 */
bootstrapAuth()
  .then(() => useAuthStore.getState().refreshUser())
  .catch(() => useAuthStore.getState().setUser(null))
  .finally(() => {
    createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: 'var(--wc-surface-raised)',
              color: 'var(--wc-text)',
              border: '1px solid var(--wc-border-subtle)',
              borderRadius: 'var(--wc-radius)',
              boxShadow: 'var(--wc-shadow-lg)',
              fontFamily: 'var(--font-sans)',
              fontSize: '0.875rem',
            },
          }}
        />
      </QueryClientProvider>
    </StrictMode>,
  )
})
