/** Storefront shell: header, navigation, search, footer. */

import { useEffect, useRef, useState } from 'react'
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
  useSearchParams,
} from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Heart,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Search,
  ShoppingBag,
  Sun,
  User as UserIcon,
  X,
} from 'lucide-react'

import { cn } from '@/lib/cn'
import { get } from '@/lib/api'
import { useTheme, type Theme } from '@/hooks/useTheme'
import { useAuthStore } from '@/features/auth/store'
import { useCartStore } from '@/features/cart/store'
import { CartDrawer } from '@/features/cart/CartDrawer'
import { SupportWidget } from '@/features/support/SupportWidget'
import type { Category, SearchSuggestion } from '@/lib/types'

export function Wordmark({ className }: { className?: string }) {
  // Uses the brand logo at /brand/logo.png when present, and falls back to the
  // typeset wordmark otherwise, so nothing breaks before the asset is added.
  const [logoOk, setLogoOk] = useState(true)
  if (logoOk) {
    // Two takes on the real wordmark: the dark walnut original for light UI, a
    // grain-preserving light recolour for dark UI. CSS shows exactly one, keyed
    // to the same theme signals as the colour tokens, so it never inverts wrong.
    return (
      <span className={cn('inline-flex items-center', className)}>
        <img
          src="/brand/logo.png"
          alt="Woodcroft"
          className="wc-logo-light h-8 w-auto"
          onError={() => setLogoOk(false)}
        />
        <img
          src="/brand/logo-dark.png"
          alt=""
          aria-hidden
          className="wc-logo-dark h-8 w-auto"
        />
      </span>
    )
  }
  return (
    <span className={cn('inline-flex items-baseline gap-[0.1em]', className)}>
      <span
        className="font-display text-[1.15em] tracking-[0.02em]"
        style={{ fontVariationSettings: '"SOFT" 24, "WONK" 1, "opsz" 120' }}
      >
        Woodcroft
      </span>
    </span>
  )
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const options: { value: Theme; icon: typeof Sun; label: string }[] = [
    { value: 'light', icon: Sun, label: 'Light' },
    { value: 'dark', icon: Moon, label: 'Dark' },
    { value: 'system', icon: Monitor, label: 'System' },
  ]

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="inline-flex items-center gap-0.5 rounded-[2px] border border-line p-0.5"
    >
      {options.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          role="radio"
          aria-checked={theme === value}
          aria-label={label}
          title={label}
          onClick={() => setTheme(value)}
          className={cn(
            'flex size-7 items-center justify-center rounded-[2px] transition-colors',
            theme === value ? 'bg-sunken text-ink' : 'text-faint hover:text-ink',
          )}
        >
          <Icon size={14} strokeWidth={1.5} />
        </button>
      ))}
    </div>
  )
}

function SearchBar({ onClose }: { onClose?: () => void }) {
  const [params] = useSearchParams()
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const boxRef = useRef<HTMLDivElement>(null)

  const { data: suggestions = [] } = useQuery({
    queryKey: ['suggest', query],
    queryFn: () => get<SearchSuggestion[]>('/search/suggest', { q: query }),
    enabled: query.trim().length >= 2,
    staleTime: 30_000,
  })

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const submit = (value: string) => {
    if (!value.trim()) return
    setOpen(false)
    onClose?.()
    navigate(`/search?q=${encodeURIComponent(value.trim())}`)
  }

  return (
    <div ref={boxRef} className="relative w-full">
      <form
        role="search"
        onSubmit={(event) => {
          event.preventDefault()
          submit(query)
        }}
      >
        <Search
          size={15}
          strokeWidth={1.5}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
          aria-hidden
        />
        <input
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search products…"
          aria-label="Search products"
          className="wc-input pl-9 pr-3 py-2 text-sm bg-sunken border-transparent focus-visible:bg-surface"
        />
      </form>

      {open && query.trim().length >= 2 && suggestions.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-40 mt-1 overflow-hidden border border-line bg-raised shadow-lg">
          <ul>
            {suggestions.map((item, index) => (
              <li key={`${item.kind}-${item.slug}-${index}`}>
                <Link
                  to={
                    item.kind === 'category'
                      ? `/collections/${item.slug}`
                      : `/product/${item.slug}`
                  }
                  onClick={() => {
                    setOpen(false)
                    onClose?.()
                  }}
                  className="flex items-center gap-3 px-3 py-2.5 text-sm hover:bg-sunken"
                >
                  {item.image_url ? (
                    <img
                      src={item.image_url}
                      alt=""
                      className="size-9 object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <span className="flex size-9 items-center justify-center bg-sunken text-faint">
                      <Search size={13} strokeWidth={1.5} />
                    </span>
                  )}
                  <span className="flex-1 truncate">{item.label}</span>
                  <span className="wc-eyebrow text-[0.6rem]">{item.kind}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Header() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [cartOpen, setCartOpen] = useState(false)
  const location = useLocation()
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
  const itemCount = useCartStore((state) => state.itemCount())

  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: () => get<Category[]>('/categories'),
    staleTime: 10 * 60_000,
  })

  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  const primary = categories.slice(0, 6)

  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50
                   focus:bg-accent focus:px-4 focus:py-2 focus:text-on-accent"
      >
        Skip to content
      </a>

      <div className="bg-forest-600 text-[var(--forest-50)] wc-no-print">
        <div className="wc-container flex h-9 items-center justify-center text-[0.7rem] tracking-[0.1em] uppercase">
          Free delivery on orders over Rs 20,000
        </div>
      </div>

      <header className="sticky top-0 z-40 border-b border-line bg-canvas/95 backdrop-blur wc-no-print">
        <div className="wc-container">
          <div className="flex h-14 items-center gap-4">
            <button
              className="lg:hidden p-1 text-muted"
              onClick={() => setMenuOpen(true)}
              aria-label="Open menu"
            >
              <Menu size={20} strokeWidth={1.5} />
            </button>

            <Link to="/" className="shrink-0 text-xl" aria-label="Woodcroft home">
              <Wordmark />
            </Link>

            <nav className="hidden lg:flex items-center gap-5 ml-4" aria-label="Main">
              {primary.map((category, i) => (
                <NavLink
                  key={category.id}
                  to={`/collections/${category.slug}`}
                  className={({ isActive }) =>
                    cn(
                      'text-[0.8rem] tracking-wide transition-colors',
                      // Only the first four show below xl so the row does not
                      // overflow and clip the cart on mid-size laptops.
                      i >= 4 && 'hidden xl:inline',
                      isActive ? 'text-ink' : 'text-muted hover:text-ink',
                    )
                  }
                >
                  {category.name}
                </NavLink>
              ))}
              <NavLink
                to="/journal"
                className={({ isActive }) =>
                  cn('text-[0.8rem] tracking-wide transition-colors',
                     isActive ? 'text-ink' : 'text-muted hover:text-ink')
                }
              >
                Journal
              </NavLink>
            </nav>

            <div className="ml-auto hidden md:block min-w-0 flex-1 max-w-xs">
              <SearchBar />
            </div>

            <div className="ml-auto md:ml-0 flex items-center gap-1">
              <div className="hidden sm:block mr-1">
                <ThemeToggle />
              </div>

              <Link
                to="/account/wishlist"
                className="p-1.5 text-muted hover:text-ink transition-colors"
                aria-label="Wishlist"
              >
                <Heart size={18} strokeWidth={1.5} />
              </Link>

              {user ? (
                <div className="relative group">
                  <Link
                    to="/account"
                    className="flex items-center gap-1.5 p-1.5 text-muted hover:text-ink transition-colors"
                    aria-label="Your account"
                  >
                    <UserIcon size={18} strokeWidth={1.5} />
                  </Link>
                  <div className="invisible absolute right-0 top-full z-40 w-48 border border-line bg-raised py-1 opacity-0 shadow-lg transition-all group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100">
                    <p className="px-3 py-2 text-xs text-faint truncate border-b border-line">
                      {user.email}
                    </p>
                    <Link to="/account" className="block px-3 py-2 text-sm hover:bg-sunken">Account</Link>
                    <Link to="/account/orders" className="block px-3 py-2 text-sm hover:bg-sunken">Orders</Link>
                    {(user.role === 'admin' || user.role === 'staff') && (
                      <Link to="/admin" className="block px-3 py-2 text-sm hover:bg-sunken text-brass-ink">
                        Admin panel
                      </Link>
                    )}
                    <button
                      onClick={logout}
                      className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-sunken"
                    >
                      <LogOut size={13} strokeWidth={1.5} /> Sign out
                    </button>
                  </div>
                </div>
              ) : (
                <Link
                  to="/login"
                  className="p-1.5 text-muted hover:text-ink transition-colors"
                  aria-label="Sign in"
                >
                  <UserIcon size={18} strokeWidth={1.5} />
                </Link>
              )}

              <button
                onClick={() => setCartOpen(true)}
                className="relative p-1.5 text-muted hover:text-ink transition-colors"
                aria-label={`Cart, ${itemCount} items`}
              >
                <ShoppingBag size={18} strokeWidth={1.5} />
                {itemCount > 0 && (
                  <span className="absolute -right-0.5 -top-0.5 flex min-w-[17px] items-center justify-center rounded-full bg-[var(--wc-brass)] px-1 text-[0.6rem] font-semibold text-[var(--walnut-900)] tabular-nums">
                    {itemCount}
                  </span>
                )}
              </button>
            </div>
          </div>

          <div className="md:hidden pb-3">
            <SearchBar />
          </div>
        </div>
      </header>

      {menuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            className="absolute inset-0 bg-[var(--wc-scrim)]"
            onClick={() => setMenuOpen(false)}
            aria-label="Close menu"
            tabIndex={-1}
          />
          <nav
            className="absolute left-0 top-0 bottom-0 w-72 overflow-y-auto bg-surface p-5"
            aria-label="Mobile"
          >
            <div className="mb-6 flex items-center justify-between">
              <Wordmark className="text-lg" />
              <button onClick={() => setMenuOpen(false)} aria-label="Close">
                <X size={18} strokeWidth={1.5} />
              </button>
            </div>
            <ul className="space-y-1">
              {categories.map((category) => (
                <li key={category.id}>
                  <Link
                    to={`/collections/${category.slug}`}
                    className="flex items-center justify-between py-2 text-sm"
                  >
                    {category.name}
                    <span className="text-xs text-faint tabular-nums">
                      {category.product_count}
                    </span>
                  </Link>
                </li>
              ))}
              <li className="pt-3 mt-3 border-t border-line">
                <Link to="/journal" className="block py-2 text-sm">Journal</Link>
              </li>
              <li><Link to="/page/about" className="block py-2 text-sm">About</Link></li>
            </ul>
            <div className="mt-6 pt-4 border-t border-line">
              <ThemeToggle />
            </div>
          </nav>
        </div>
      )}

      <CartDrawer open={cartOpen} onClose={() => setCartOpen(false)} />
    </>
  )
}

function Footer() {
  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: () => get<Category[]>('/categories'),
    staleTime: 10 * 60_000,
  })

  return (
    <footer className="mt-auto border-t border-line bg-sunken wc-no-print">
      <div className="wc-container py-14">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <Wordmark className="text-xl" />
            <p className="mt-3 max-w-xs text-sm text-muted">
              Solid timber furniture and woodware, cut and joined by hand in
              Karachi since 2002.
            </p>
            <p className="mt-4 text-xs text-faint">
              Surjani Town, Karachi, Pakistan
              <br />
              hello@woodcroft.pk · 0300 1234567
            </p>
          </div>

          <div>
            <h3 className="wc-eyebrow mb-4">Shop</h3>
            <ul className="space-y-2 text-sm text-muted">
              {categories.slice(0, 6).map((category) => (
                <li key={category.id}>
                  <Link to={`/collections/${category.slug}`} className="hover:text-ink transition-colors">
                    {category.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className="wc-eyebrow mb-4">Help</h3>
            <ul className="space-y-2 text-sm text-muted">
              <li><Link to="/faq" className="hover:text-ink transition-colors">FAQ</Link></li>
              <li><Link to="/contact" className="hover:text-ink transition-colors">Contact us</Link></li>
              <li><Link to="/page/shipping" className="hover:text-ink transition-colors">Shipping</Link></li>
              <li><Link to="/page/returns" className="hover:text-ink transition-colors">Returns</Link></li>
              <li><Link to="/account/orders" className="hover:text-ink transition-colors">Track an order</Link></li>
            </ul>
          </div>

          <div>
            <h3 className="wc-eyebrow mb-4">Company</h3>
            <ul className="space-y-2 text-sm text-muted">
              <li><Link to="/page/about" className="hover:text-ink transition-colors">About</Link></li>
              <li><Link to="/journal" className="hover:text-ink transition-colors">Journal</Link></li>
              <li><Link to="/page/sustainability" className="hover:text-ink transition-colors">Sustainability</Link></li>
              <li><Link to="/page/terms" className="hover:text-ink transition-colors">Terms</Link></li>
              <li><Link to="/page/privacy" className="hover:text-ink transition-colors">Privacy</Link></li>
              <li><Link to="/page/accessibility" className="hover:text-ink transition-colors">Accessibility</Link></li>
            </ul>
          </div>
        </div>

        <div className="mt-12 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-6 text-xs text-faint">
          <p>© {new Date().getFullYear()} Woodcroft. All rights reserved.</p>
          <p>Cash on delivery across Pakistan. Prices include GST.</p>
        </div>
      </div>
    </footer>
  )
}

export function Layout() {
  const location = useLocation()

  // Move focus to the top on navigation. Without this a screen reader stays
  // where it was and the new page is effectively invisible.
  const mainRef = useRef<HTMLElement>(null)
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior })
    mainRef.current?.focus({ preventScroll: true })
  }, [location.pathname])

  return (
    <div className="flex min-h-dvh flex-col">
      <Header />
      <main id="main" ref={mainRef} tabIndex={-1} className="flex-1 outline-none">
        <Outlet />
      </main>
      <Footer />
      <SupportWidget />
    </div>
  )
}
