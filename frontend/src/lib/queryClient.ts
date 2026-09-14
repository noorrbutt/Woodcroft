import { QueryClient } from '@tanstack/react-query'

/* One shared client so non-React code (the Zustand stores) can invalidate
   queries after a mutation. main.tsx hands this same instance to the app. */
export const queryClient = new QueryClient({
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
