import { useEffect } from 'react'

/**
 * Set the browser tab title. Kept short ("Woodcroft", "Woodcroft Admin",
 * "Woodcroft Bedroom") so it never gets truncated in the tab.
 */
export function useDocumentTitle(title: string) {
  useEffect(() => {
    if (title) document.title = title
  }, [title])
}
