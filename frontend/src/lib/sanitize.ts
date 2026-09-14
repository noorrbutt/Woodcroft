import DOMPurify from 'dompurify'

/**
 * Sanitize admin-authored HTML before it is injected into the page.
 *
 * The blog, static page and FAQ bodies are rendered with dangerouslySetInnerHTML.
 * Even though only an admin can author them today, one compromised admin session
 * would otherwise become persistent script on every storefront page. This strips
 * scripts, event handlers and other active content while keeping normal markup.
 */
export function sanitizeHtml(html: string | null | undefined): string {
  if (!html) return ''
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['style', 'script', 'iframe', 'object', 'embed', 'form'],
    FORBID_ATTR: ['style', 'onerror', 'onload', 'onclick'],
  })
}
