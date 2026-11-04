import { Link } from 'react-router-dom'
import { ShoppingBag, Trash2 } from 'lucide-react'

import { Drawer, EmptyState, QuantityStepper } from '@/components/ui'
import { formatPkr } from '@/lib/format'
import {
  lineTotalPaisa,
  linePersonalizationPaisa,
  useCartStore,
} from './store'

const FREE_SHIPPING_THRESHOLD = 2_000_000

export function CartDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const lines = useCartStore((state) => state.lines)
  const updateQuantity = useCartStore((state) => state.updateQuantity)
  const remove = useCartStore((state) => state.remove)
  const subtotal = useCartStore((state) => state.subtotalPaisa())

  const shortfall = FREE_SHIPPING_THRESHOLD - subtotal

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={`Your cart${lines.length ? ` (${lines.length})` : ''}`}
      footer={
        lines.length > 0 ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted">Subtotal</span>
              <span className="font-medium tabular-nums">{formatPkr(subtotal)}</span>
            </div>
            <p className="text-xs text-faint">
              Delivery and any discount are calculated at checkout. Prices
              include GST.
            </p>
            <Link
              to="/checkout"
              onClick={onClose}
              className="wc-btn wc-btn-primary w-full"
            >
              Checkout
            </Link>
            <Link
              to="/cart"
              onClick={onClose}
              className="block text-center text-xs text-muted hover:text-ink"
            >
              View full cart
            </Link>
          </div>
        ) : undefined
      }
    >
      {lines.length === 0 ? (
        <EmptyState
          icon={<ShoppingBag size={38} strokeWidth={1} />}
          title="Your cart is empty"
          description="Nothing here yet. Have a look at what is in the workshop."
          action={
            <Link to="/shop" onClick={onClose} className="wc-btn wc-btn-primary">
              Browse the collection
            </Link>
          }
        />
      ) : (
        <>
          {shortfall > 0 && (
            <div className="mb-4 border border-line bg-sunken px-3 py-2.5 text-xs">
              Add <strong>{formatPkr(shortfall)}</strong> more for free delivery.
              <div className="mt-2 h-1 overflow-hidden bg-[var(--wc-border-subtle)]">
                <div
                  className="h-full bg-[var(--wc-brass)] transition-[width] duration-500"
                  style={{
                    width: `${Math.min(100, (subtotal / FREE_SHIPPING_THRESHOLD) * 100)}%`,
                  }}
                />
              </div>
            </div>
          )}

          <ul className="divide-y divide-[var(--wc-border-subtle)]">
            {lines.map((line) => {
              const personalization = linePersonalizationPaisa(line)
              return (
                <li key={line.lineId} className="flex gap-3 py-4">
                  <Link
                    to={`/product/${line.productSlug}`}
                    onClick={onClose}
                    className="shrink-0"
                  >
                    {line.imageUrl ? (
                      <img
                        src={line.imageUrl}
                        alt=""
                        className="size-20 object-cover"
                        loading="lazy"
                        decoding="async"
                      />
                    ) : (
                      <div className="size-20 bg-sunken" />
                    )}
                  </Link>

                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/product/${line.productSlug}`}
                      onClick={onClose}
                      className="block text-sm font-medium leading-snug hover:text-[var(--wc-brass-text)]"
                    >
                      {line.productName}
                    </Link>
                    {line.variantName && (
                      <p className="mt-0.5 text-xs text-muted">{line.variantName}</p>
                    )}

                    {line.personalization.length > 0 && (
                      <ul className="mt-1 space-y-0.5">
                        {line.personalization.map((entry) => (
                          <li key={entry.key} className="text-xs text-[var(--wc-brass-text)]">
                            {entry.label}: “{entry.value}”
                            {entry.surchargePaisa > 0 && (
                              <span className="text-faint">
                                {' '}
                                +{formatPkr(entry.surchargePaisa)}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}

                    <div className="mt-2.5 flex items-center justify-between gap-2">
                      <QuantityStepper
                        value={line.quantity}
                        max={line.maxQuantity || 99}
                        onChange={(quantity) => updateQuantity(line.lineId, quantity)}
                      />
                      <div className="text-right">
                        <div className="text-sm font-medium tabular-nums">
                          {formatPkr(lineTotalPaisa(line))}
                        </div>
                        {personalization > 0 && (
                          <div className="text-[0.65rem] text-faint">
                            incl. {formatPkr(personalization * line.quantity)} personalisation
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={() => remove(line.lineId)}
                    aria-label={`Remove ${line.productName}`}
                    className="self-start p-1 text-faint hover:text-[var(--wc-danger)] transition-colors"
                  >
                    <Trash2 size={15} strokeWidth={1.5} />
                  </button>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </Drawer>
  )
}
