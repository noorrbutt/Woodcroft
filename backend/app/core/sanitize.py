"""Server-side HTML sanitisation for admin-authored content.

The blog, static page and FAQ bodies are stored as HTML and rendered into the
storefront. Sanitising on write means the stored value is already safe whatever
reads it later, so the client sanitiser is a second line of defence, not the only
one. Scripts, event handlers, styles and framing elements are stripped; ordinary
formatting, links, images, headings, lists and tables survive.
"""

from __future__ import annotations

import bleach

ALLOWED_TAGS = [
    "p", "br", "hr", "span", "div", "blockquote", "pre", "code",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "sub", "sup", "mark",
    "ul", "ol", "li", "dl", "dt", "dd",
    "a", "img", "figure", "figcaption",
    "table", "thead", "tbody", "tr", "th", "td", "caption",
]

ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height", "loading"],
    "*": ["class"],
}

#: http/https/mailto and relative links only; no javascript: or data: URLs.
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def clean_html(html: str | None) -> str:
    """Strip unsafe HTML, keeping ordinary formatting. Never returns None."""
    if not html:
        return ""
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
