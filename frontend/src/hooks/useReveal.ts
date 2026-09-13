import { useEffect, useRef } from 'react'
import { useReducedMotion } from './useTheme'

/**
 * Reveal on scroll.
 *
 * Skips the observer entirely under prefers-reduced-motion. A CSS-only
 * override is not enough: the element starts at opacity 0 waiting to be
 * revealed, so without this it would simply never appear, which is far worse
 * than the animation it was trying to avoid.
 */
export function useReveal<T extends HTMLElement = HTMLDivElement>(threshold = 0.15) {
  const ref = useRef<T>(null)
  const reduced = useReducedMotion()

  useEffect(() => {
    const element = ref.current
    if (!element) return

    if (reduced) {
      element.classList.add('is-visible')
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible')
            observer.unobserve(entry.target)
          }
        }
      },
      { threshold, rootMargin: '0px 0px -60px 0px' },
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [threshold, reduced])

  return ref
}
