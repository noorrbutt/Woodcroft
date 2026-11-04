import { formatPkr } from '@/lib/format'

export function FreeShippingProgress({
  subtotal,
  threshold,
}: {
  subtotal: number
  threshold: number
}) {
  const remaining = Math.max(0, threshold - subtotal)

  return (
    <div className="border border-line bg-sunken px-3 py-2.5 text-xs">
      {remaining > 0 ? (
        <>Add <strong>{formatPkr(remaining)}</strong> more for free shipping</>
      ) : (
        <span>You've got free shipping</span>
      )}
      <div
        className="mt-2 h-1 overflow-hidden bg-[var(--wc-border-subtle)]"
        role="progressbar"
        aria-label="Progress towards free shipping"
        aria-valuemin={0}
        aria-valuemax={Math.max(1, threshold)}
        aria-valuenow={Math.min(subtotal, threshold)}
      >
        <div
          className="h-full bg-[var(--wc-brass)] transition-[width] duration-500"
          style={{ width: `${threshold > 0 ? Math.min(100, (subtotal / threshold) * 100) : 100}%` }}
        />
      </div>
    </div>
  )
}
