/**
 * UI primitives.
 *
 * Everything themes through semantic tokens. If a component here needs a
 * `dark:` utility, the right fix is almost always a missing token.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import { Link } from 'react-router-dom'
import { Check, ChevronRight, Star, X } from 'lucide-react'

import { cn } from '@/lib/cn'
import { formatPkr } from '@/lib/format'
import type { Money } from '@/lib/types'

/* ── Button ──────────────────────────────────────────────────────────────── */
type ButtonVariant = 'primary' | 'brass' | 'outline' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  fullWidth?: boolean
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading,
  fullWidth,
  className,
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        'wc-btn',
        variant === 'primary' && 'wc-btn-primary',
        variant === 'brass' && 'wc-btn-brass',
        variant === 'outline' && 'wc-btn-outline',
        variant === 'ghost' && 'wc-btn-ghost',
        variant === 'danger' && 'bg-[var(--wc-danger)] text-on-danger hover:brightness-110',
        size === 'sm' && 'wc-btn-sm',
        size === 'lg' && 'wc-btn-lg',
        fullWidth && 'w-full',
        className,
      )}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && <Spinner className="size-3.5" />}
      {children}
    </button>
  )
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cn('animate-spin size-4', className)} viewBox="0 0 24 24" aria-hidden>
      <circle
        className="opacity-25"
        cx="12" cy="12" r="10"
        stroke="currentColor" strokeWidth="3" fill="none"
      />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z"
      />
    </svg>
  )
}

/* ── Form fields ─────────────────────────────────────────────────────────── */
interface FieldProps {
  label?: string
  error?: string
  hint?: string
  required?: boolean
  children: ReactNode
  id?: string
}

export function Field({ label, error, hint, required, children, id }: FieldProps) {
  return (
    <div>
      {label && (
        <label htmlFor={id} className="wc-label">
          {label}
          {required && <span className="text-[var(--wc-danger)]"> *</span>}
        </label>
      )}
      {children}
      {hint && !error && (
        <p className="mt-1 text-xs text-faint">{hint}</p>
      )}
      {error && (
        <p role="alert" className="mt-1 text-xs text-[var(--wc-danger)]">
          {error}
        </p>
      )}
    </div>
  )
}

export const Input = ({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) => (
  <input className={cn('wc-input', className)} {...props} />
)

export const Textarea = ({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea className={cn('wc-textarea', className)} rows={4} {...props} />
)

export const Select = ({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className={cn('wc-select', className)} {...props}>
    {children}
  </select>
)

export function Checkbox({
  label,
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  const id = useId()
  return (
    <label htmlFor={id} className={cn('flex items-start gap-2.5 cursor-pointer', className)}>
      <span className="relative flex items-center justify-center mt-0.5">
        <input
          id={id}
          type="checkbox"
          className="peer appearance-none size-4 rounded-[2px] border border-control bg-surface
                     checked:bg-accent checked:border-accent transition-colors"
          {...props}
        />
        <Check
          className="pointer-events-none absolute size-3 text-on-accent opacity-0 peer-checked:opacity-100"
          strokeWidth={3}
          aria-hidden
        />
      </span>
      <span className="text-sm leading-snug">{label}</span>
    </label>
  )
}

/* ── Price ───────────────────────────────────────────────────────────────── */
export function Price({
  value,
  compareAt,
  size = 'md',
  className,
}: {
  value: Money | number
  compareAt?: Money | number | null
  size?: 'sm' | 'md' | 'lg'
  className?: string
}) {
  const current = typeof value === 'number' ? formatPkr(value) : value.display
  const was =
    compareAt == null
      ? null
      : typeof compareAt === 'number'
        ? formatPkr(compareAt)
        : compareAt.display

  return (
    <span className={cn('inline-flex items-baseline gap-2 whitespace-nowrap', className)}>
      {/* Inter with tabular numerals, not mono. Mono prices on a consumer
          storefront look like a developer console. */}
      <span
        className={cn(
          'font-medium tabular-nums',
          size === 'sm' && 'text-sm',
          size === 'md' && 'text-base',
          size === 'lg' && 'text-2xl',
        )}
      >
        {current}
      </span>
      {was && (
        <span
          className={cn(
            'text-faint line-through tabular-nums',
            size === 'lg' ? 'text-base' : 'text-xs',
          )}
        >
          {was}
        </span>
      )}
    </span>
  )
}

/* ── Rating ──────────────────────────────────────────────────────────────── */
export function Rating({
  value,
  count,
  size = 14,
  showCount = true,
}: {
  value: number | string
  count?: number
  size?: number
  showCount?: boolean
}) {
  const rating = typeof value === 'string' ? parseFloat(value) : value
  return (
    <span className="inline-flex items-center gap-1.5" aria-label={`${rating.toFixed(1)} out of 5`}>
      <span className="flex" aria-hidden>
        {[1, 2, 3, 4, 5].map((star) => (
          <Star
            key={star}
            size={size}
            strokeWidth={1.5}
            /* Brass, never the default amber. A yellow star on this palette
               is the single most obvious template tell. */
            className={
              star <= Math.round(rating)
                ? 'fill-[var(--wc-brass)] text-[var(--wc-brass)]'
                : 'fill-none text-[var(--walnut-300)]'
            }
          />
        ))}
      </span>
      {showCount && count !== undefined && (
        <span className="text-xs text-faint tabular-nums">({count})</span>
      )}
    </span>
  )
}

/* ── Badge ───────────────────────────────────────────────────────────────── */
export function Badge({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: 'neutral' | 'sale' | 'new' | 'out' | 'low' | 'success' | 'warning' | 'danger' | 'info'
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        'wc-badge',
        tone === 'sale' && 'wc-badge-sale',
        tone === 'new' && 'wc-badge-new',
        tone === 'out' && 'wc-badge-out',
        tone === 'low' && 'wc-badge-low',
        tone === 'success' && 'bg-success-bg text-success',
        tone === 'warning' && 'bg-warning-bg text-warning',
        tone === 'danger' && 'bg-danger-bg text-danger',
        tone === 'info' && 'bg-info-bg text-info',
        tone === 'neutral' && 'bg-sunken text-muted',
        className,
      )}
    >
      {children}
    </span>
  )
}

/* ── Skeleton ────────────────────────────────────────────────────────────── */
export function Skeleton({
  className,
  style,
}: {
  className?: string
  style?: React.CSSProperties
}) {
  return <div className={cn('wc-skeleton', className)} style={style} aria-hidden />
}

/* ── Breadcrumbs ─────────────────────────────────────────────────────────── */
export function Breadcrumbs({
  items,
}: {
  items: { label: string; to?: string }[]
}) {
  return (
    <nav aria-label="Breadcrumb" className="text-xs text-muted">
      <ol className="flex flex-wrap items-center gap-1.5">
        {items.map((item, index) => (
          <li key={`${item.label}-${index}`} className="flex items-center gap-1.5">
            {index > 0 && <ChevronRight size={12} className="text-faint" aria-hidden />}
            {item.to && index < items.length - 1 ? (
              <Link to={item.to} className="hover:text-ink transition-colors">
                {item.label}
              </Link>
            ) : (
              <span aria-current={index === items.length - 1 ? 'page' : undefined}
                    className={index === items.length - 1 ? 'text-ink' : undefined}>
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  )
}

/* ── Empty state ─────────────────────────────────────────────────────────── */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      {icon && <div className="mb-5 text-faint">{icon}</div>}
      <h3 className="font-display text-xl">{title}</h3>
      {description && (
        <p className="mt-2 max-w-sm text-sm text-muted">{description}</p>
      )}
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}

/* ── Drawer ──────────────────────────────────────────────────────────────────
   Focus is moved into the panel on open and restored on close, Escape closes,
   and the page behind is locked. Without these a drawer is a keyboard trap. */
export function Drawer({
  open,
  onClose,
  title,
  side = 'right',
  children,
  footer,
}: {
  open: boolean
  onClose: () => void
  title: string
  side?: 'left' | 'right'
  children: ReactNode
  footer?: ReactNode
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const restoreRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return

    restoreRef.current = document.activeElement as HTMLElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)

    const timer = window.setTimeout(() => {
      panelRef.current?.querySelector<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      )?.focus()
    }, 60)

    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
      window.clearTimeout(timer)
      restoreRef.current?.focus()
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 wc-no-print">
      <button
        className="absolute inset-0 bg-[var(--wc-scrim)] animate-[fadeIn_200ms_ease]"
        onClick={onClose}
        aria-label="Close"
        tabIndex={-1}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          'absolute top-0 bottom-0 flex w-full max-w-md flex-col bg-surface shadow-xl',
          side === 'right' ? 'right-0' : 'left-0',
        )}
        style={{
          animation: `wcSlide${side === 'right' ? 'Right' : 'Left'} 280ms var(--wc-ease-out)`,
        }}
      >
        <header className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="font-display text-lg">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="p-1 text-muted hover:text-ink">
            <X size={18} strokeWidth={1.5} />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="border-t border-line px-5 py-4">{footer}</div>}
      </div>
    </div>
  )
}

/* ── Modal ───────────────────────────────────────────────────────────────── */
export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  size = 'md',
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg'
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 wc-no-print">
      <button
        className="absolute inset-0 bg-[var(--wc-scrim)]"
        onClick={onClose}
        aria-label="Close"
        tabIndex={-1}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          'relative w-full bg-raised shadow-xl',
          size === 'sm' && 'max-w-sm',
          size === 'md' && 'max-w-lg',
          size === 'lg' && 'max-w-3xl',
        )}
        style={{ animation: 'wcPop 220ms var(--wc-ease-out)' }}
      >
        <header className="flex items-center justify-between border-b border-line px-6 py-4">
          <h2 className="font-display text-lg">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="p-1 text-muted hover:text-ink">
            <X size={18} strokeWidth={1.5} />
          </button>
        </header>
        <div className="max-h-[70vh] overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="border-t border-line px-6 py-4">{footer}</div>}
      </div>
    </div>
  )
}

/* ── Tabs ────────────────────────────────────────────────────────────────── */
interface TabsContextValue {
  active: string
  setActive: (value: string) => void
}
const TabsContext = createContext<TabsContextValue | null>(null)

export function Tabs({
  defaultValue,
  children,
  className,
}: {
  defaultValue: string
  children: ReactNode
  className?: string
}) {
  const [active, setActive] = useState(defaultValue)
  return (
    <TabsContext.Provider value={{ active, setActive }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  )
}

export function TabList({ children }: { children: ReactNode }) {
  return (
    <div role="tablist" className="flex gap-6 border-b border-line">
      {children}
    </div>
  )
}

export function Tab({ value, children }: { value: string; children: ReactNode }) {
  const ctx = useContext(TabsContext)!
  const selected = ctx.active === value
  return (
    <button
      role="tab"
      aria-selected={selected}
      onClick={() => ctx.setActive(value)}
      className={cn(
        'relative -mb-px border-b-2 pb-3 text-sm transition-colors',
        selected
          ? 'border-[var(--wc-brass)] text-ink'
          : 'border-transparent text-muted hover:text-ink',
      )}
    >
      {children}
    </button>
  )
}

export function TabPanel({ value, children }: { value: string; children: ReactNode }) {
  const ctx = useContext(TabsContext)!
  if (ctx.active !== value) return null
  return <div role="tabpanel" className="pt-6">{children}</div>
}

/* ── Accordion ───────────────────────────────────────────────────────────── */
export function Accordion({
  title,
  children,
  defaultOpen = false,
}: {
  title: ReactNode
  children: ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-b border-line">
      <button
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center justify-between py-4 text-left"
      >
        <span className="text-sm font-medium">{title}</span>
        <ChevronRight
          size={16}
          strokeWidth={1.5}
          className={cn('text-faint transition-transform', open && 'rotate-90')}
          aria-hidden
        />
      </button>
      {open && <div className="pb-5 text-sm text-muted">{children}</div>}
    </div>
  )
}

/* ── Pagination ──────────────────────────────────────────────────────────────
   Real anchor links, not buttons. Infinite scroll destroys the footer, breaks
   the back button and hurts SEO on a catalogue that needs to rank. */
export function Pagination({
  page,
  pages,
  makeHref,
}: {
  page: number
  pages: number
  makeHref: (page: number) => string
}) {
  if (pages <= 1) return null

  const window_ = 2
  const numbers: (number | '…')[] = []
  for (let i = 1; i <= pages; i += 1) {
    if (i === 1 || i === pages || (i >= page - window_ && i <= page + window_)) {
      numbers.push(i)
    } else if (numbers[numbers.length - 1] !== '…') {
      numbers.push('…')
    }
  }

  return (
    <nav aria-label="Pagination" className="flex items-center justify-center gap-1 pt-12">
      {page > 1 && (
        <Link to={makeHref(page - 1)} className="wc-btn wc-btn-outline wc-btn-sm">
          Previous
        </Link>
      )}
      {numbers.map((entry, index) =>
        entry === '…' ? (
          <span key={`gap-${index}`} className="px-2 text-faint">…</span>
        ) : (
          <Link
            key={entry}
            to={makeHref(entry)}
            aria-current={entry === page ? 'page' : undefined}
            className={cn(
              'flex size-9 items-center justify-center rounded-[2px] text-sm tabular-nums transition-colors',
              entry === page
                ? 'bg-ink text-canvas'
                : 'text-muted hover:bg-sunken hover:text-ink',
            )}
          >
            {entry}
          </Link>
        ),
      )}
      {page < pages && (
        <Link to={makeHref(page + 1)} className="wc-btn wc-btn-outline wc-btn-sm">
          Next
        </Link>
      )}
    </nav>
  )
}

/* ── Section heading ─────────────────────────────────────────────────────── */
export function SectionHeading({
  numeral,
  eyebrow,
  title,
  description,
  action,
  ghost = false,
}: {
  numeral?: string
  eyebrow?: string
  title: string
  description?: string
  action?: ReactNode
  /** Render the numeral once more, oversized and ghosted, behind the heading. */
  ghost?: boolean
}) {
  return (
    <div className="relative mb-10">
      {ghost && numeral && (
        <span
          aria-hidden
          className="pointer-events-none absolute -top-10 right-0 select-none font-display leading-none text-ink opacity-[0.05] text-[clamp(6rem,18vw,15rem)]"
          style={{ fontVariationSettings: '"SOFT" 40, "WONK" 1, "opsz" 144' }}
        >
          {numeral}
        </span>
      )}
      <div className="relative z-10 flex flex-wrap items-end justify-between gap-4">
        <div>
          {numeral && (
            <div className="mb-3 flex items-center gap-3">
              <span className="wc-numeral">{numeral}</span>
              <span className="h-px w-10 bg-[var(--wc-brass)]" aria-hidden />
            </div>
          )}
          {eyebrow && <p className="wc-eyebrow mb-2">{eyebrow}</p>}
          <h2>{title}</h2>
          {description && (
            <p className="mt-3 max-w-xl text-sm text-muted">{description}</p>
          )}
        </div>
        {action}
      </div>
    </div>
  )
}

/* ── Quantity stepper ────────────────────────────────────────────────────── */
export function QuantityStepper({
  value,
  onChange,
  max = 99,
  min = 1,
  disabled,
}: {
  value: number
  onChange: (value: number) => void
  max?: number
  min?: number
  disabled?: boolean
}) {
  const clamp = useCallback(
    (next: number) => Math.max(min, Math.min(max, next)),
    [min, max],
  )
  return (
    <div className="inline-flex items-center border border-control rounded-[2px]">
      <button
        onClick={() => onChange(clamp(value - 1))}
        disabled={disabled || value <= min}
        aria-label="Decrease quantity"
        className="px-3 py-2 text-muted hover:text-ink disabled:opacity-35 disabled:cursor-not-allowed"
      >
        −
      </button>
      <span className="w-10 text-center text-sm tabular-nums" aria-live="polite">
        {value}
      </span>
      <button
        onClick={() => onChange(clamp(value + 1))}
        disabled={disabled || value >= max}
        aria-label="Increase quantity"
        className="px-3 py-2 text-muted hover:text-ink disabled:opacity-35 disabled:cursor-not-allowed"
      >
        +
      </button>
    </div>
  )
}
