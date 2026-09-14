/** Cart, checkout, order confirmation and compare. */

import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Check,
  ChevronLeft,
  Lock,
  PackageCheck,
  ShieldCheck,
  ShoppingBag,
  Trash2,
  Truck,
} from 'lucide-react'

import { ApiError, get, post } from '@/lib/api'
import { cn } from '@/lib/cn'
import { formatDate, formatPkr } from '@/lib/format'
import {
  Badge,
  Breadcrumbs,
  Button,
  Checkbox,
  EmptyState,
  Field,
  Input,
  Price,
  QuantityStepper,
  Select,
  Skeleton,
  Textarea,
} from '@/components/ui'
import { useAuthStore } from '@/features/auth/store'
import {
  lineTotalPaisa,
  linePersonalizationPaisa,
  useCartStore,
  useCompareStore,
} from '@/features/cart/store'
import { PROVINCES, type ProductDetail, type Province } from '@/lib/types'

/* ── Shared types for the quote endpoint ─────────────────────────────────── */
interface QuoteLine {
  variant_id: string
  product_name: string
  variant_name: string | null
  sku: string
  image_url: string | null
  quantity: number
  unit_price: { paisa: number; display: string }
  personalization_surcharge: { paisa: number; display: string }
  line_total: { paisa: number; display: string }
  in_stock: boolean
  available: number
}

interface Quote {
  lines: QuoteLine[]
  subtotal: { paisa: number; display: string }
  discount: { paisa: number; display: string }
  shipping: { paisa: number; display: string }
  cod_surcharge: { paisa: number; display: string }
  gift_wrap: { paisa: number; display: string }
  tax: { paisa: number; display: string }
  total: { paisa: number; display: string }
  tax_mode: 'inclusive' | 'exclusive'
  coupon_code: string | null
  coupon_error: string | null
  loyalty_points_earned: number
  free_shipping: boolean
  cod_available: boolean
  item_count: number
}

interface PaymentMethod {
  code: string
  name: string
  description: string | null
  enabled: boolean
  unavailable_label: string | null
  surcharge_paisa: number
}

function useQuotePayload(province?: Province) {
  const lines = useCartStore((state) => state.lines)
  const couponCode = useCartStore((state) => state.couponCode)
  const giftWrap = useCartStore((state) => state.giftWrap)

  return useMemo(
    () => ({
      lines: lines.map((line) => ({
        variant_id: line.variantId,
        quantity: line.quantity,
        personalization: Object.fromEntries(
          line.personalization.map((entry) => [entry.key, entry.value]),
        ),
      })),
      province,
      coupon_code: couponCode ?? undefined,
      payment_method: 'cod' as const,
      gift_wrap: giftWrap,
    }),
    [lines, province, couponCode, giftWrap],
  )
}

/* ── Cart ────────────────────────────────────────────────────────────────── */
export function CartPage() {
  const lines = useCartStore((state) => state.lines)
  const updateQuantity = useCartStore((state) => state.updateQuantity)
  const remove = useCartStore((state) => state.remove)
  const subtotal = useCartStore((state) => state.subtotalPaisa())
  const couponCode = useCartStore((state) => state.couponCode)
  const setCoupon = useCartStore((state) => state.setCoupon)
  const giftWrap = useCartStore((state) => state.giftWrap)
  const setGiftWrap = useCartStore((state) => state.setGiftWrap)

  const [code, setCode] = useState(couponCode ?? '')
  const payload = useQuotePayload()

  const { data: quote } = useQuery({
    queryKey: ['quote', payload],
    queryFn: () => post<Quote>('/checkout/quote', payload),
    enabled: lines.length > 0,
  })

  if (lines.length === 0) {
    return (
      <div className="wc-container py-16">
        <EmptyState
          icon={<ShoppingBag size={40} strokeWidth={1} />}
          title="Your cart is empty"
          description="Nothing here yet. Have a look at what is in the workshop."
          action={<Link to="/shop" className="wc-btn wc-btn-primary">Browse the collection</Link>}
        />
      </div>
    )
  }

  return (
    <div className="wc-container py-10">
      <Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: 'Cart' }]} />
      <h1 className="mt-6 mb-10 text-4xl">Your cart</h1>

      <div className="grid gap-12 lg:grid-cols-[1fr_22rem]">
        <div>
          <ul className="divide-y divide-[var(--wc-border-subtle)] border-y border-line">
            {lines.map((line) => {
              const quoteLine = quote?.lines.find((l) => l.variant_id === line.variantId)
              const outOfStock = quoteLine && !quoteLine.in_stock
              return (
                <li key={line.lineId} className="flex gap-4 py-6">
                  <Link to={`/product/${line.productSlug}`} className="shrink-0">
                    {line.imageUrl ? (
                      <img src={line.imageUrl} alt="" className="size-28 object-cover" />
                    ) : (
                      <div className="size-28 bg-sunken" />
                    )}
                  </Link>

                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/product/${line.productSlug}`}
                      className="font-medium hover:text-[var(--wc-brass-text)]"
                    >
                      {line.productName}
                    </Link>
                    {line.variantName && (
                      <p className="mt-0.5 text-sm text-muted">{line.variantName}</p>
                    )}
                    <p className="mt-0.5 font-mono text-[0.7rem] text-faint">{line.sku}</p>

                    {line.personalization.length > 0 && (
                      <ul className="mt-2 space-y-0.5">
                        {line.personalization.map((entry) => (
                          <li key={entry.key} className="text-xs text-[var(--wc-brass-text)]">
                            {entry.label}: “{entry.value}” (+{formatPkr(entry.surchargePaisa)})
                          </li>
                        ))}
                      </ul>
                    )}

                    {outOfStock && (
                      <div className="mt-2">
                        <Badge tone="out">
                          Only {quoteLine.available} available
                        </Badge>
                      </div>
                    )}

                    <div className="mt-4 flex items-center gap-4">
                      <QuantityStepper
                        value={line.quantity}
                        max={line.maxQuantity || 99}
                        onChange={(quantity) => updateQuantity(line.lineId, quantity)}
                      />
                      <button
                        onClick={() => remove(line.lineId)}
                        className="flex items-center gap-1.5 text-xs text-muted hover:text-[var(--wc-danger)]"
                      >
                        <Trash2 size={13} strokeWidth={1.5} /> Remove
                      </button>
                    </div>
                  </div>

                  <div className="text-right">
                    <div className="font-medium tabular-nums">
                      {formatPkr(lineTotalPaisa(line))}
                    </div>
                    <div className="mt-0.5 text-xs text-faint tabular-nums">
                      {formatPkr(line.unitPricePaisa + linePersonalizationPaisa(line))} each
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>

          <div className="mt-6">
            <Checkbox
              label={`Gift wrap this order (${formatPkr(35_000)})`}
              checked={giftWrap}
              onChange={(event) => setGiftWrap(event.target.checked)}
            />
          </div>

          <Link to="/shop" className="mt-8 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
            <ChevronLeft size={14} strokeWidth={1.5} /> Continue shopping
          </Link>
        </div>

        <aside className="lg:sticky lg:top-28 lg:self-start">
          <div className="wc-panel p-5">
            <h2 className="wc-eyebrow mb-4">Order summary</h2>

            <form
              className="mb-5 flex gap-2"
              onSubmit={(event) => {
                event.preventDefault()
                setCoupon(code.trim() || null)
              }}
            >
              <Input
                placeholder="Discount code"
                value={code}
                onChange={(event) => setCode(event.target.value.toUpperCase())}
                className="py-2 text-sm"
              />
              <Button type="submit" variant="outline" size="sm" className="shrink-0">
                Apply
              </Button>
            </form>

            {quote?.coupon_error && (
              <p className="mb-3 text-xs text-[var(--wc-danger)]">
                That code is not valid for this order.
              </p>
            )}
            {quote && quote.discount.paisa > 0 && (
              <p className="mb-3 text-xs text-[var(--wc-success)]">
                {quote.coupon_code} applied
              </p>
            )}

            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted">Subtotal</dt>
                <dd className="tabular-nums">{quote?.subtotal.display ?? formatPkr(subtotal)}</dd>
              </div>
              {quote && quote.discount.paisa > 0 && (
                <div className="flex justify-between text-[var(--wc-success)]">
                  <dt>Discount</dt>
                  <dd className="tabular-nums">−{quote.discount.display}</dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-muted">Delivery</dt>
                <dd className="tabular-nums">
                  {quote?.free_shipping ? 'Free' : (quote?.shipping.display ?? 'At checkout')}
                </dd>
              </div>
              {quote && quote.gift_wrap.paisa > 0 && (
                <div className="flex justify-between">
                  <dt className="text-muted">Gift wrap</dt>
                  <dd className="tabular-nums">{quote.gift_wrap.display}</dd>
                </div>
              )}
              {quote && (
                <div className="flex justify-between text-xs text-faint">
                  <dt>{quote.tax_mode === 'inclusive' ? 'Includes GST' : 'GST'}</dt>
                  <dd className="tabular-nums">{quote.tax.display}</dd>
                </div>
              )}
            </dl>

            <div className="mt-4 flex items-baseline justify-between border-t border-line pt-4">
              <span className="font-display text-lg">Total</span>
              <span className="text-xl font-medium tabular-nums">
                {quote?.total.display ?? formatPkr(subtotal)}
              </span>
            </div>

            <Link to="/checkout" className="wc-btn wc-btn-primary wc-btn-lg mt-5 w-full">
              <Lock size={13} strokeWidth={1.5} /> Checkout
            </Link>

            {quote && quote.loyalty_points_earned > 0 && (
              <p className="mt-3 text-center text-xs text-[var(--wc-brass-text)]">
                Earn {quote.loyalty_points_earned} loyalty points on this order
              </p>
            )}
          </div>

          <div className="mt-4 space-y-2 px-1 text-xs text-faint">
            <p className="flex items-center gap-2"><ShieldCheck size={13} strokeWidth={1.5} /> Cash on delivery available</p>
            <p className="flex items-center gap-2"><Truck size={13} strokeWidth={1.5} /> Free delivery over Rs 20,000</p>
            <p className="flex items-center gap-2"><PackageCheck size={13} strokeWidth={1.5} /> 14 day returns</p>
          </div>
        </aside>
      </div>
    </div>
  )
}

interface SavedAddress {
  id: string
  label: string | null
  full_name: string
  phone: string
  line1: string
  line2: string | null
  area: string | null
  landmark: string | null
  city: string
  province: string
  postal_code: string | null
  is_default_shipping: boolean
}

/* ── Checkout ────────────────────────────────────────────────────────────── */
export function CheckoutPage() {
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)
  const lines = useCartStore((state) => state.lines)
  const clearCart = useCartStore((state) => state.clear)
  const giftMessage = useCartStore((state) => state.giftMessage)

  const [form, setForm] = useState({
    full_name: user?.full_name ?? '',
    phone: user?.phone ?? '',
    line1: '',
    line2: '',
    area: '',
    landmark: '',
    city: '',
    province: 'punjab' as Province,
    postal_code: '',
  })
  const [email, setEmail] = useState(user?.email ?? '')
  const [note, setNote] = useState('')
  const [method, setMethod] = useState('cod')
  const [terms, setTerms] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [prefilled, setPrefilled] = useState(false)

  // Signed-in customers should not retype an address they already saved.
  const { data: savedAddresses = [] } = useQuery({
    queryKey: ['addresses'],
    queryFn: () => get<SavedAddress[]>('/addresses'),
    enabled: Boolean(user),
  })

  const applyAddress = (addr: SavedAddress) => {
    setForm((f) => ({
      ...f,
      full_name: addr.full_name,
      phone: addr.phone,
      line1: addr.line1,
      line2: addr.line2 ?? '',
      area: addr.area ?? '',
      landmark: addr.landmark ?? '',
      city: addr.city,
      province: addr.province as Province,
      postal_code: addr.postal_code ?? '',
    }))
  }

  useEffect(() => {
    // Prefill once from the default (or first) saved address.
    if (prefilled || savedAddresses.length === 0) return
    const def = savedAddresses.find((a) => a.is_default_shipping) ?? savedAddresses[0]
    if (def) applyAddress(def)
    setPrefilled(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedAddresses, prefilled])

  const payload = useQuotePayload(form.province)

  const { data: quote, isLoading: quoting, isError: quoteError } = useQuery({
    queryKey: ['quote', payload],
    queryFn: () => post<Quote>('/checkout/quote', payload),
    enabled: lines.length > 0,
  })

  const { data: methods = [] } = useQuery({
    queryKey: ['payment-methods'],
    queryFn: () => get<PaymentMethod[]>('/checkout/payment-methods'),
  })

  const placeOrder = useMutation({
    mutationFn: () =>
      post<{ order_number: string; access_token: string | null }>('/orders', {
        ...payload,
        shipping: form,
        email: user ? undefined : email,
        customer_note: note || undefined,
        gift_message: giftMessage || undefined,
        payment_method: method,
        accept_terms: terms,
      }),
    onSuccess: (order) => {
      clearCart()
      toast.success('Order placed. Thank you.')
      // A guest order is only viewable with its access token, so carry it in the
      // confirmation URL. A signed-in order needs no token.
      const suffix = order.access_token
        ? `?token=${encodeURIComponent(order.access_token)}`
        : ''
      navigate(`/order/${order.order_number}${suffix}`, { replace: true })
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        setErrors(error.fieldErrors)
        setFormError(Object.keys(error.fieldErrors).length ? null : error.message)
      } else {
        setFormError('Could not place your order. Please try again.')
      }
    },
  })

  useEffect(() => {
    if (lines.length === 0 && !placeOrder.isSuccess) navigate('/cart', { replace: true })
  }, [lines.length, navigate, placeOrder.isSuccess])

  const bind = (key: keyof typeof form) =>
    (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value }))

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setErrors({})
    setFormError(null)
    if (!terms) {
      setFormError('Please accept the terms to continue.')
      return
    }
    placeOrder.mutate()
  }

  const codBlocked = method === 'cod' && quote && !quote.cod_available

  return (
    <div className="wc-container py-10">
      <Breadcrumbs
        items={[{ label: 'Home', to: '/' }, { label: 'Cart', to: '/cart' }, { label: 'Checkout' }]}
      />
      <h1 className="mt-6 mb-10 text-4xl">Checkout</h1>

      <form onSubmit={submit} className="grid gap-12 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-10">
          {formError && (
            <div role="alert" className="border border-[var(--wc-danger)] bg-danger-bg px-4 py-3 text-sm text-[var(--wc-danger)]">
              {formError}
            </div>
          )}

          <section>
            <h2 className="mb-5 flex items-center gap-3 font-display text-xl">
              <span className="wc-numeral">01</span> Contact
            </h2>
            {!user && (
              <>
                <Field label="Email" id="email" error={errors.email}
                       hint="We send your order confirmation here." required>
                  <Input id="email" type="email" required autoComplete="email"
                         value={email} onChange={(event) => setEmail(event.target.value)} />
                </Field>
                <p className="mt-2 text-xs text-muted">
                  Have an account?{' '}
                  <Link to="/login?next=/checkout" className="wc-link">Sign in</Link> for
                  faster checkout.
                </p>
              </>
            )}
            {user && (
              <p className="text-sm text-muted">
                Signed in as <strong className="text-ink">{user.email}</strong>
              </p>
            )}
          </section>

          <section>
            <h2 className="mb-5 flex items-center gap-3 font-display text-xl">
              <span className="wc-numeral">02</span> Delivery address
            </h2>
            {savedAddresses.length > 0 && (
              <div className="mb-4">
                <Field label="Use a saved address" id="saved-address">
                  <Select
                    id="saved-address"
                    onChange={(e) => {
                      const addr = savedAddresses.find((a) => a.id === e.target.value)
                      if (addr) applyAddress(addr)
                    }}
                  >
                    <option value="">Enter a new address</option>
                    {savedAddresses.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.label ? `${a.label} — ` : ''}{a.line1}, {a.city}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Full name" id="name" error={errors['shipping.full_name']} required>
                <Input id="name" required autoComplete="name" value={form.full_name} onChange={bind('full_name')} />
              </Field>
              <Field label="Mobile" id="phone" error={errors['shipping.phone']}
                     hint="For delivery updates" required>
                <Input id="phone" required placeholder="0300 1234567" autoComplete="tel"
                       value={form.phone} onChange={bind('phone')} />
              </Field>
              <div className="sm:col-span-2">
                <Field label="Address" id="line1" error={errors['shipping.line1']} required>
                  <Input id="line1" required placeholder="House 12, Street 4"
                         autoComplete="address-line1" value={form.line1} onChange={bind('line1')} />
                </Field>
              </div>
              <Field label="Area or sector" id="area">
                <Input id="area" placeholder="Gulberg III" value={form.area} onChange={bind('area')} />
              </Field>
              <Field label="Nearest landmark" id="landmark" hint="Couriers rely on this">
                <Input id="landmark" placeholder="Near the park" value={form.landmark} onChange={bind('landmark')} />
              </Field>
              <Field label="City" id="city" error={errors['shipping.city']} required>
                <Input id="city" required autoComplete="address-level2" value={form.city} onChange={bind('city')} />
              </Field>
              <Field label="Province" id="province" required>
                <Select id="province" value={form.province} onChange={bind('province')}>
                  {PROVINCES.map((province) => (
                    <option key={province.value} value={province.value}>{province.label}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Postal code" id="postal" error={errors['shipping.postal_code']}>
                <Input id="postal" placeholder="54000" maxLength={5}
                       value={form.postal_code} onChange={bind('postal_code')} />
              </Field>
            </div>

            <div className="mt-4">
              <Field label="Delivery instructions" id="note">
                <Textarea id="note" rows={2} placeholder="Anything the courier should know"
                          value={note} onChange={(event) => setNote(event.target.value)} />
              </Field>
            </div>
          </section>

          <section>
            <h2 className="mb-5 flex items-center gap-3 font-display text-xl">
              <span className="wc-numeral">03</span> Payment
            </h2>
            <div className="space-y-2.5">
              {methods.map((option) => (
                <label
                  key={option.code}
                  className={cn(
                    'flex cursor-pointer items-start gap-3 border p-4 transition-colors',
                    method === option.code && option.enabled
                      ? 'border-[var(--wc-border-strong)] bg-sunken'
                      : 'border-line',
                    !option.enabled && 'cursor-not-allowed opacity-55',
                  )}
                >
                  <input
                    type="radio"
                    name="payment"
                    value={option.code}
                    checked={method === option.code}
                    disabled={!option.enabled}
                    onChange={() => setMethod(option.code)}
                    className="mt-1"
                  />
                  <span className="flex-1">
                    <span className="flex items-center gap-2 font-medium">
                      {option.name}
                      {!option.enabled && option.unavailable_label && (
                        <Badge tone="neutral">{option.unavailable_label}</Badge>
                      )}
                    </span>
                    {option.description && (
                      <span className="mt-0.5 block text-xs text-muted">{option.description}</span>
                    )}
                    {option.enabled && option.surcharge_paisa > 0 && (
                      <span className="mt-0.5 block text-xs text-faint">
                        {formatPkr(option.surcharge_paisa)} handling fee
                      </span>
                    )}
                  </span>
                </label>
              ))}
            </div>

            {codBlocked && (
              <p className="mt-3 text-sm text-[var(--wc-danger)]">
                Cash on delivery is not available for this order. It may exceed
                the limit for your area.
              </p>
            )}
          </section>
        </div>

        <aside className="lg:sticky lg:top-28 lg:self-start">
          <div className="wc-panel p-5">
            <h2 className="wc-eyebrow mb-4">Your order</h2>

            {quoting && !quote ? (
              <div className="space-y-3">
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
              </div>
            ) : (
              <ul className="mb-5 space-y-3">
                {quote?.lines.map((line) => (
                  <li key={line.variant_id} className="flex gap-3">
                    {line.image_url ? (
                      <img src={line.image_url} alt="" className="size-14 shrink-0 object-cover" />
                    ) : (
                      <div className="size-14 shrink-0 bg-sunken" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm">{line.product_name}</p>
                      <p className="text-xs text-faint">
                        {line.variant_name} · ×{line.quantity}
                      </p>
                    </div>
                    <span className="text-sm tabular-nums">{line.line_total.display}</span>
                  </li>
                ))}
              </ul>
            )}

            <dl className="space-y-2 border-t border-line pt-4 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted">Subtotal</dt>
                <dd className="tabular-nums">{quote?.subtotal.display}</dd>
              </div>
              {quote && quote.discount.paisa > 0 && (
                <div className="flex justify-between text-[var(--wc-success)]">
                  <dt>Discount</dt>
                  <dd className="tabular-nums">−{quote.discount.display}</dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-muted">Delivery</dt>
                <dd className="tabular-nums">
                  {quote?.free_shipping ? 'Free' : quote?.shipping.display}
                </dd>
              </div>
              {quote && quote.cod_surcharge.paisa > 0 && (
                <div className="flex justify-between">
                  <dt className="text-muted">Cash on delivery fee</dt>
                  <dd className="tabular-nums">{quote.cod_surcharge.display}</dd>
                </div>
              )}
              {quote && (
                <div className="flex justify-between text-xs text-faint">
                  <dt>{quote.tax_mode === 'inclusive' ? 'Includes GST' : 'GST'}</dt>
                  <dd className="tabular-nums">{quote.tax.display}</dd>
                </div>
              )}
            </dl>

            <div className="mt-4 flex items-baseline justify-between border-t border-line pt-4">
              <span className="font-display text-lg">Total</span>
              <span className="text-xl font-medium tabular-nums">{quote?.total.display}</span>
            </div>

            <div className="mt-5">
              <Checkbox
                checked={terms}
                onChange={(event) => setTerms(event.target.checked)}
                label={
                  <>
                    I accept the{' '}
                    <Link to="/page/terms" className="wc-link" target="_blank">Terms</Link> and{' '}
                    <Link to="/page/returns" className="wc-link" target="_blank">Return Policy</Link>.
                  </>
                }
              />
            </div>

            {quoteError && (
              <p className="mt-4 border border-[var(--wc-danger)]/40 bg-[var(--wc-danger)]/10 p-3 text-sm text-[var(--wc-danger)]">
                One or more items in your cart are no longer available. Please
                return to your cart and remove anything marked unavailable.
              </p>
            )}
            <Button
              type="submit"
              size="lg"
              fullWidth
              className="mt-5"
              loading={placeOrder.isPending}
              disabled={!terms || !quote || Boolean(codBlocked)}
            >
              <Lock size={13} strokeWidth={1.5} /> Place order
            </Button>

            <p className="mt-3 text-center text-xs text-faint">
              You will not be charged online. Pay the courier on delivery.
            </p>
          </div>
        </aside>
      </form>
    </div>
  )
}

/* ── Order confirmation ──────────────────────────────────────────────────── */
interface OrderResponse {
  order_number: string
  status_label: string
  placed_at: string
  items: {
    id: string
    product_name: string
    variant_name: string | null
    quantity: number
    line_total: { display: string }
    image_url: string | null
    personalization: Record<string, { label: string; value: string }>
  }[]
  subtotal: { display: string }
  discount: { paisa: number; display: string }
  shipping: { display: string }
  cod_surcharge: { paisa: number; display: string }
  tax: { display: string }
  total: { display: string }
  tax_mode: string
  shipping_address: Record<string, string | null>
  courier: string | null
  timeline: { message: string; at: string }[]
  payment_method: string
}

export function OrderConfirmationPage() {
  const { orderNumber } = useParams()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const { data: order, isLoading } = useQuery({
    queryKey: ['order', orderNumber, token],
    queryFn: () =>
      get<OrderResponse>(
        `/orders/${orderNumber}`,
        token ? { token } : undefined,
      ),
    enabled: Boolean(orderNumber),
  })

  if (isLoading) {
    return (
      <div className="wc-container py-16">
        <Skeleton className="mx-auto h-64 w-full max-w-2xl" />
      </div>
    )
  }

  if (!order) {
    return (
      <div className="wc-container py-16 text-center">
        <h1 className="text-3xl">We could not find that order</h1>
        <Link to="/" className="wc-btn wc-btn-primary mt-8">Back to home</Link>
      </div>
    )
  }

  return (
    <div className="wc-container py-14">
      <div className="mx-auto max-w-2xl">
        <div className="mb-10 text-center">
          <span className="mx-auto mb-5 flex size-14 items-center justify-center rounded-full bg-success-bg text-[var(--wc-success)]">
            <Check size={26} strokeWidth={1.5} />
          </span>
          <h1 className="text-3xl">Thank you for your order</h1>
          <p className="mt-3 text-sm text-muted">
            We have emailed a confirmation. We will be in touch to confirm
            delivery.
          </p>
          <p className="wc-numeral mt-6">{order.order_number}</p>
        </div>

        <div className="wc-panel p-6">
          <ul className="divide-y divide-[var(--wc-border-subtle)]">
            {order.items.map((item) => (
              <li key={item.id} className="flex gap-4 py-4 first:pt-0">
                {item.image_url ? (
                  <img src={item.image_url} alt="" className="size-16 object-cover" />
                ) : (
                  <div className="size-16 bg-sunken" />
                )}
                <div className="flex-1">
                  <p className="text-sm font-medium">{item.product_name}</p>
                  {item.variant_name && (
                    <p className="text-xs text-muted">{item.variant_name}</p>
                  )}
                  {Object.values(item.personalization ?? {}).map((entry) => (
                    <p key={entry.label} className="text-xs text-[var(--wc-brass-text)]">
                      {entry.label}: “{entry.value}”
                    </p>
                  ))}
                  <p className="mt-1 text-xs text-faint">Quantity {item.quantity}</p>
                </div>
                <span className="text-sm tabular-nums">{item.line_total.display}</span>
              </li>
            ))}
          </ul>

          <dl className="mt-4 space-y-2 border-t border-line pt-4 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted">Subtotal</dt>
              <dd className="tabular-nums">{order.subtotal.display}</dd>
            </div>
            {order.discount.paisa > 0 && (
              <div className="flex justify-between text-[var(--wc-success)]">
                <dt>Discount</dt>
                <dd className="tabular-nums">−{order.discount.display}</dd>
              </div>
            )}
            <div className="flex justify-between">
              <dt className="text-muted">Delivery</dt>
              <dd className="tabular-nums">{order.shipping.display}</dd>
            </div>
            {order.cod_surcharge.paisa > 0 && (
              <div className="flex justify-between">
                <dt className="text-muted">Cash on delivery fee</dt>
                <dd className="tabular-nums">{order.cod_surcharge.display}</dd>
              </div>
            )}
            <div className="flex justify-between text-xs text-faint">
              <dt>{order.tax_mode === 'inclusive' ? 'Includes GST' : 'GST'}</dt>
              <dd className="tabular-nums">{order.tax.display}</dd>
            </div>
            <div className="flex justify-between border-t border-line pt-3 text-base">
              <dt className="font-display">Total</dt>
              <dd className="font-medium tabular-nums">{order.total.display}</dd>
            </div>
          </dl>

          {order.payment_method === 'cod' && (
            <p className="mt-5 border border-line bg-sunken p-3 text-sm">
              Please have <strong>{order.total.display}</strong> ready in cash
              for the courier.
            </p>
          )}
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <div className="wc-panel p-5">
            <h2 className="wc-eyebrow mb-3">Delivering to</h2>
            <address className="text-sm not-italic leading-relaxed text-muted">
              {order.shipping_address.name}<br />
              {order.shipping_address.line1}<br />
              {order.shipping_address.area && <>{order.shipping_address.area}<br /></>}
              {order.shipping_address.landmark && (
                <span className="text-faint">{order.shipping_address.landmark}<br /></span>
              )}
              {order.shipping_address.city}, {order.shipping_address.province}<br />
              {order.shipping_address.phone}
            </address>
          </div>
          <div className="wc-panel p-5">
            <h2 className="wc-eyebrow mb-3">Progress</h2>
            <ol className="space-y-2 text-sm">
              {order.timeline.map((event, index) => (
                <li key={index} className="flex gap-2.5">
                  <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-[var(--wc-brass)]" />
                  <div>
                    <p>{event.message}</p>
                    <p className="text-xs text-faint">{formatDate(event.at)}</p>
                  </div>
                </li>
              ))}
            </ol>
            {order.courier && (
              <p className="mt-4 text-xs text-faint">Shipping with {order.courier}</p>
            )}
          </div>
        </div>

        <div className="mt-8 flex justify-center gap-3">
          <Link to="/shop" className="wc-btn wc-btn-outline">Continue shopping</Link>
          <Link to="/account/orders" className="wc-btn wc-btn-primary">View your orders</Link>
        </div>
      </div>
    </div>
  )
}

/* ── Compare ─────────────────────────────────────────────────────────────── */
export function ComparePage() {
  const [params] = useSearchParams()
  const stored = useCompareStore((state) => state.slugs)
  const clear = useCompareStore((state) => state.clear)
  const slugs = params.getAll('slug').length ? params.getAll('slug') : stored

  const { data: products = [] } = useQuery({
    queryKey: ['compare', slugs],
    queryFn: async () =>
      Promise.all(slugs.map((slug) => get<ProductDetail>(`/products/${slug}`))),
    enabled: slugs.length > 0,
  })

  if (slugs.length === 0) {
    return (
      <div className="wc-container py-16">
        <EmptyState
          title="Nothing to compare yet"
          description="Add two or more pieces to see them side by side."
          action={<Link to="/shop" className="wc-btn wc-btn-primary">Browse the collection</Link>}
        />
      </div>
    )
  }

  const rows: { label: string; render: (p: ProductDetail) => React.ReactNode }[] = [
    { label: 'Price', render: (p) => <Price value={p.price} compareAt={p.compare_at_price} size="sm" /> },
    { label: 'Timber', render: (p) => p.wood_species_label ?? '—' },
    {
      label: 'Dimensions',
      render: (p) =>
        p.dimensions
          ? `${p.dimensions.length_cm ?? '—'} × ${p.dimensions.width_cm ?? '—'} × ${p.dimensions.height_cm ?? '—'} cm`
          : '—',
    },
    { label: 'Weight', render: (p) => (p.weight_g ? `${(p.weight_g / 1000).toFixed(1)} kg` : '—') },
    { label: 'Rating', render: (p) => (p.rating_count ? `${p.rating_average} (${p.rating_count})` : 'No reviews') },
    { label: 'Availability', render: (p) => (p.is_in_stock ? 'In stock' : 'Out of stock') },
    { label: 'Personalisation', render: (p) => p.personalization_options.map((o) => o.label).join(', ') || '—' },
  ]

  return (
    <div className="wc-container py-10">
      <Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: 'Compare' }]} />
      <div className="mt-6 mb-8 flex items-center justify-between">
        <h1 className="text-4xl">Compare</h1>
        <button onClick={clear} className="text-sm text-muted hover:text-ink">Clear all</button>
      </div>

      <div className="wc-scroll-x">
        <table className="w-full min-w-[40rem] border-collapse text-sm">
          <thead>
            <tr>
              <th className="w-32" />
              {products.map((product) => (
                <th key={product.id} className="p-3 text-left align-top">
                  <Link to={`/product/${product.slug}`}>
                    {product.primary_image && (
                      <img
                        src={product.primary_image.thumb_url}
                        alt=""
                        className="mb-2 aspect-4/5 w-full object-cover"
                      />
                    )}
                    <span className="font-medium">{product.name}</span>
                  </Link>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-t border-line">
                <th className="p-3 text-left align-top wc-eyebrow">{row.label}</th>
                {products.map((product) => (
                  <td key={product.id} className="p-3 align-top">{row.render(product)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
