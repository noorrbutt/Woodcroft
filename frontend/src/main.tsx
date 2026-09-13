import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { Toaster } from 'sonner'

import '@fontsource-variable/fraunces'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import './styles/theme.css'
import './styles/base.css'

import { router } from './router'
import { bootstrapAuth } from './lib/api'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Catalogue data changes rarely and re-fetching on every window focus
      // makes a browsing session feel twitchy.
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        // Never retry a 4xx: the request was wrong, not unlucky.
        const status = (error as { status?: number })?.status
        if (status && status >= 400 && status < 500) return false
        return failureCount < 2
      },
    },
  },
})

// Restore the session before the first paint that could depend on it, so a
// signed-in user does not briefly see the signed-out header.
bootstrapAuth().finally(() => {
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
