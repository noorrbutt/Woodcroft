/** Customer account: overview, orders, addresses, profile, wishlist, security. */

import { useEffect, useState, type FormEvent } from 'react'
import { Link, NavLink, Outlet, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Gift,
  Heart,
  LogOut,
  MapPin,
  Package,
  Shield,
  Sparkles,
  Trash2,
  User as UserIcon,
} from 'lucide-react'

import { ApiError, del, get, patch, post, put } from '@/lib/api'
import { cn } from '@/lib/cn'
import { formatDate, formatDateTime, formatPkr, relativeTime } from '@/lib/format'
import {
  Badge,
  Breadcrumbs,
  Button,
  Checkbox,
  EmptyState,
  Field,
  Input,
  Modal,
  QuantityStepper,
  Select,
  Skeleton,
  Textarea,
} from '@/components/ui'
import { useAuthStore } from '@/features/auth/store'
import { useWishlistStore } from '@/features/cart/store'
import { ProductGrid } from '@/features/catalog/ProductCard'
import {
  PROVINCES,
  type ApiMessage,
  type NotificationPreferences,
  type ProductCard,
  type Province,
  type Session,
} from '@/lib/types'

const NAV = [
  { to: '/account', label: 'Overview', icon: Sparkles, end: true },
  { to: '/account/orders', label: 'Orders', icon: Package },
  { to: '/account/wishlist', label: 'Wishlist', icon: Heart },
  { to: '/account/addresses', label: 'Addresses', icon: MapPin },
  { to: '/account/profile', label: 'Profile', icon: UserIcon },
  { to: '/account/security', label: 'Security', icon: Shield },
]

export function AccountLayout() {
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)

  return (
    <div className="wc-container py-10">
      <Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: 'Account' }]} />
      <h1 className="mt-6 mb-10 text-4xl">Your account</h1>

      <div className="grid gap-10 lg:grid-cols-[14rem_1fr]">
        <aside>
          <div className="mb-6 border-b border-line pb-5">
            <p className="font-medium">{user?.full_name}</p>
            <p className="truncate text-xs text-faint">{user?.email}</p>
            {user && !user.is_email_verified && (
              <Badge tone="warning" className="mt-2">Email not confirmed</Badge>
            )}
          </div>

          <nav className="space-y-0.5">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2.5 px-2.5 py-2 text-sm transition-colors',
                    isActive ? 'bg-sunken text-ink' : 'text-muted hover:text-ink',
                  )
                }
              >
                <Icon size={15} strokeWidth={1.5} />
                {label}
              </NavLink>
            ))}
            <button
              onClick={logout}
              className="flex w-full items-center gap-2.5 px-2.5 py-2 text-sm text-muted hover:text-ink"
            >
              <LogOut size={15} strokeWidth={1.5} /> Sign out
            </button>
          </nav>
        </aside>

        <div className="min-w-0">
          <Outlet />
        </div>
      </div>
    </div>
  )
}

/* ── Overview ────────────────────────────────────────────────────────────── */
interface OrderSummary {
  order_number: string
  status_label: string
  status: string
  placed_at: string
  total: { display: string }
  items: { id: string; product_name: string; image_url: string | null; quantity: number }[]
  is_cancellable: boolean
}

interface Loyalty {
  points_balance: number
  lifetime_points_earned: number
  tier: string
  redeemable: { display: string }
  transactions: { kind: string; delta_points: number; note: string | null; at: string }[]
}

interface Referrals {
  code: string | null
  invited: number
  qualified: number
  total_earned: { display: string }
  share_url: string
}

export function AccountOverview() {
  const user = useAuthStore((state) => state.user)
  const { data: orders = [] } = useQuery({
    queryKey: ['my-orders'],
    queryFn: () => get<OrderSummary[]>('/orders'),
  })
  const { data: loyalty } = useQuery({
    queryKey: ['loyalty'],
    queryFn: () => get<Loyalty>('/loyalty'),
  })
  const { data: referrals } = useQuery({
    queryKey: ['referrals'],
    queryFn: () => get<Referrals>('/referrals'),
  })

  return (
    <div className="space-y-10">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="wc-panel p-5">
          <p className="wc-eyebrow mb-2">Orders</p>
          <p className="font-display text-3xl">{orders.length}</p>
        </div>
        <div className="wc-panel p-5">
          <p className="wc-eyebrow mb-2">Loyalty points</p>
          <p className="font-display text-3xl">{loyalty?.points_balance ?? 0}</p>
          <p className="mt-1 text-xs text-faint">
            worth {loyalty?.redeemable.display ?? 'Rs 0'} · {loyalty?.tier ?? 'bronze'}
          </p>
        </div>
        <div className="wc-panel p-5">
          <p className="wc-eyebrow mb-2">Store credit</p>
          <p className="font-display text-3xl">{formatPkr(user?.store_credit_paisa ?? 0)}</p>
        </div>
      </div>

      {referrals?.code && (
        <div className="wc-panel p-5">
          <div className="flex items-start gap-3">
            <Gift size={18} strokeWidth={1.25} className="mt-0.5 text-[var(--wc-brass)]" />
            <div className="flex-1">
              <h2 className="font-display text-lg">Invite a friend</h2>
              <p className="mt-1 text-sm text-muted">
                They get 10% off their first order, you get Rs 500 credit once
                it is delivered.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <code className="border border-line bg-sunken px-3 py-1.5 font-mono text-sm">
                  {referrals.code}
                </code>
                <button
                  onClick={() => {
                    navigator.clipboard?.writeText(referrals.share_url)
                    toast.success('Invite link copied')
                  }}
                  className="text-xs text-muted hover:text-ink"
                >
                  Copy invite link
                </button>
              </div>
              <p className="mt-3 text-xs text-faint">
                {referrals.invited} invited · {referrals.qualified} qualified ·{' '}
                {referrals.total_earned.display} earned
              </p>
            </div>
          </div>
        </div>
      )}

      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-xl">Recent orders</h2>
          <Link to="/account/orders" className="text-sm text-muted hover:text-ink">View all</Link>
        </div>
        {orders.length === 0 ? (
          <EmptyState
            title="No orders yet"
            description="When you place an order it will appear here."
            action={<Link to="/shop" className="wc-btn wc-btn-primary">Start shopping</Link>}
          />
        ) : (
          <ul className="divide-y divide-[var(--wc-border-subtle)] border-y border-line">
            {orders.slice(0, 3).map((order) => (
              <li key={order.order_number}>
                <Link
                  to={`/account/orders/${order.order_number}`}
                  className="flex items-center gap-4 py-4"
                >
                  <div className="flex -space-x-3">
                    {order.items.slice(0, 3).map((item) =>
                      item.image_url ? (
                        <img
                          key={item.id}
                          src={item.image_url}
                          alt=""
                          className="size-12 border-2 border-[var(--wc-surface)] object-cover"
                        />
                      ) : null,
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-mono text-sm">{order.order_number}</p>
                    <p className="text-xs text-faint">{formatDate(order.placed_at)}</p>
                  </div>
                  <Badge tone={order.status === 'delivered' ? 'success' : 'neutral'}>
                    {order.status_label}
                  </Badge>
                  <span className="tabular-nums">{order.total.display}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {loyalty && loyalty.transactions.length > 0 && (
        <section>
          <h2 className="mb-4 font-display text-xl">Points history</h2>
          <ul className="divide-y divide-[var(--wc-border-subtle)] border-y border-line text-sm">
            {loyalty.transactions.slice(0, 6).map((entry, index) => (
              <li key={index} className="flex items-center justify-between py-3">
                <div>
                  <p>{entry.note ?? entry.kind}</p>
                  <p className="text-xs text-faint">{relativeTime(entry.at)}</p>
                </div>
                <span
                  className={cn(
                    'tabular-nums',
                    entry.delta_points > 0 ? 'text-[var(--wc-success)]' : 'text-muted',
                  )}
                >
                  {entry.delta_points > 0 ? '+' : ''}{entry.delta_points}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

/* ── Orders ──────────────────────────────────────────────────────────────── */
export function AccountOrders() {
  const { data: orders = [], isLoading } = useQuery({
    queryKey: ['my-orders'],
    queryFn: () => get<OrderSummary[]>('/orders'),
  })

  if (isLoading) return <Skeleton className="h-64 w-full" />

  if (orders.length === 0) {
    return (
      <EmptyState
        icon={<Package size={38} strokeWidth={1} />}
        title="No orders yet"
        description="When you place an order it will appear here."
        action={<Link to="/shop" className="wc-btn wc-btn-primary">Start shopping</Link>}
      />
    )
  }

  return (
    <ul className="space-y-4">
      {orders.map((order) => (
        <li key={order.order_number} className="wc-panel p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <Link
                to={`/account/orders/${order.order_number}`}
                className="font-mono text-sm hover:text-[var(--wc-brass-text)]"
              >
                {order.order_number}
              </Link>
              <p className="text-xs text-faint">{formatDate(order.placed_at)}</p>
            </div>
            <Badge tone={order.status === 'delivered' ? 'success' : 'neutral'}>
              {order.status_label}
            </Badge>
          </div>

          <ul className="mt-4 flex flex-wrap gap-3">
            {order.items.map((item) => (
              <li key={item.id} className="flex items-center gap-2">
                {item.image_url && (
                  <img src={item.image_url} alt="" className="size-12 object-cover" />
                )}
                <span className="text-xs text-muted">
                  {item.product_name} ×{item.quantity}
                </span>
              </li>
            ))}
          </ul>

          <div className="mt-4 flex items-center justify-between border-t border-line pt-4">
            <span className="text-sm tabular-nums">{order.total.display}</span>
            <Link
              to={`/account/orders/${order.order_number}`}
              className="wc-btn wc-btn-outline wc-btn-sm"
            >
              View details
            </Link>
          </div>
        </li>
      ))}
    </ul>
  )
}

interface OrderDetail {
  order_number: string
  status: string
  status_label: string
  placed_at: string
  is_cancellable: boolean
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
  shipping_address: Record<string, string>
  timeline: { message: string; at: string }[]
  tracking: { courier: string; tracking_number: string | null; url: string | null }[]
}

const RETURN_REASONS = [
  { value: 'damaged', label: 'Arrived damaged' },
  { value: 'defective', label: 'Faulty or defective' },
  { value: 'wrong_item', label: 'Wrong item sent' },
  { value: 'not_as_described', label: 'Not as described' },
  { value: 'size_issue', label: 'Size or fit issue' },
  { value: 'changed_mind', label: 'Changed my mind' },
  { value: 'other', label: 'Something else' },
]

interface Returnable {
  eligible: boolean
  reason: string | null
  window_days: number
  items: {
    order_item_id: string
    product_name: string
    variant_name: string | null
    returnable: number
    line_total: string
  }[]
}

function ReturnModal({
  orderNumber,
  open,
  onClose,
}: {
  orderNumber: string
  open: boolean
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [reason, setReason] = useState('changed_mind')
  const [note, setNote] = useState('')
  const [picked, setPicked] = useState<Record<string, number>>({})

  const { data: returnable, isLoading } = useQuery({
    queryKey: ['returnable', orderNumber],
    queryFn: () => get<Returnable>(`/orders/${orderNumber}/returnable`),
    enabled: open,
  })

  const submit = useMutation({
    mutationFn: () =>
      post<ApiMessage>(`/orders/${orderNumber}/returns`, {
        reason,
        customer_note: note || undefined,
        items: Object.entries(picked)
          .filter(([, qty]) => qty > 0)
          .map(([order_item_id, quantity]) => ({ order_item_id, quantity })),
      }),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['my-returns'] })
      onClose()
      setPicked({})
      setNote('')
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not start the return'),
  })

  const anyPicked = Object.values(picked).some((q) => q > 0)

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Request a return"
      footer={
        returnable?.eligible ? (
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button loading={submit.isPending} disabled={!anyPicked} onClick={() => submit.mutate()}>
              Start return
            </Button>
          </div>
        ) : undefined
      }
    >
      {isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : !returnable?.eligible ? (
        <p className="text-sm text-muted">
          {returnable?.reason === 'window_closed'
            ? `The ${returnable.window_days}-day return window for this order has closed.`
            : 'This order is not eligible for a return yet.'}
        </p>
      ) : (
        <div className="space-y-5">
          <div>
            <p className="wc-eyebrow mb-2">Which items?</p>
            <ul className="space-y-2">
              {returnable.items.map((item) => (
                <li key={item.order_item_id} className="flex items-center justify-between gap-3">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={(picked[item.order_item_id] ?? 0) > 0}
                      onChange={(e) =>
                        setPicked((c) => ({
                          ...c,
                          [item.order_item_id]: e.target.checked ? 1 : 0,
                        }))
                      }
                    />
                    <span>
                      {item.product_name}
                      {item.variant_name && (
                        <span className="text-faint"> ({item.variant_name})</span>
                      )}
                    </span>
                  </label>
                  {(picked[item.order_item_id] ?? 0) > 0 && item.returnable > 1 && (
                    <QuantityStepper
                      value={picked[item.order_item_id] ?? 1}
                      max={item.returnable}
                      onChange={(q) =>
                        setPicked((c) => ({ ...c, [item.order_item_id]: q }))
                      }
                    />
                  )}
                </li>
              ))}
            </ul>
          </div>

          <Field label="Reason" id="reason">
            <Select id="reason" value={reason} onChange={(e) => setReason(e.target.value)}>
              {RETURN_REASONS.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </Select>
          </Field>

          <Field label="Anything we should know?" id="rnote">
            <Textarea id="rnote" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
        </div>
      )}
    </Modal>
  )
}


export function AccountOrderDetail() {
  const { orderNumber } = useParams()
  const queryClient = useQueryClient()
  const [returnOpen, setReturnOpen] = useState(false)

  const { data: order, isLoading } = useQuery({
    queryKey: ['order', orderNumber],
    queryFn: () => get<OrderDetail>(`/orders/${orderNumber}`),
    enabled: Boolean(orderNumber),
  })

  const cancel = useMutation({
    mutationFn: () => post<ApiMessage>(`/orders/${orderNumber}/cancel`),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['order', orderNumber] })
      queryClient.invalidateQueries({ queryKey: ['my-orders'] })
    },
    onError: (error) =>
      toast.error(error instanceof ApiError ? error.message : 'Could not cancel'),
  })

  if (isLoading) return <Skeleton className="h-96 w-full" />
  if (!order) return <EmptyState title="Order not found" />

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/account/orders" className="text-xs text-muted hover:text-ink">
            ← All orders
          </Link>
          <h2 className="mt-2 font-mono text-xl">{order.order_number}</h2>
          <p className="text-xs text-faint">Placed {formatDate(order.placed_at)}</p>
        </div>
        <div className="flex items-center gap-3">
          <Badge tone={order.status === 'delivered' ? 'success' : 'neutral'}>
            {order.status_label}
          </Badge>
          {order.is_cancellable && (
            <Button
              variant="outline"
              size="sm"
              loading={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              Cancel order
            </Button>
          )}
          {order.status === 'delivered' && (
            <Button variant="outline" size="sm" onClick={() => setReturnOpen(true)}>
              Request a return
            </Button>
          )}
        </div>
      </div>

      <ReturnModal
        orderNumber={order.order_number}
        open={returnOpen}
        onClose={() => setReturnOpen(false)}
      />

      {order.tracking.length > 0 && (
        <div className="wc-panel p-5">
          <h3 className="wc-eyebrow mb-3">Tracking</h3>
          {order.tracking.map((shipment, index) => (
            <p key={index} className="text-sm">
              {shipment.courier}
              {shipment.tracking_number && (
                <> · <span className="font-mono">{shipment.tracking_number}</span></>
              )}
              {shipment.url && (
                <> · <a href={shipment.url} target="_blank" rel="noreferrer" className="wc-link">Track</a></>
              )}
            </p>
          ))}
        </div>
      )}

      <div className="wc-panel p-5">
        <ul className="divide-y divide-[var(--wc-border-subtle)]">
          {order.items.map((item) => (
            <li key={item.id} className="flex gap-4 py-4 first:pt-0">
              {item.image_url && (
                <img src={item.image_url} alt="" className="size-16 object-cover" />
              )}
              <div className="flex-1">
                <p className="text-sm font-medium">{item.product_name}</p>
                {item.variant_name && <p className="text-xs text-muted">{item.variant_name}</p>}
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
            <dt>Includes GST</dt>
            <dd className="tabular-nums">{order.tax.display}</dd>
          </div>
          <div className="flex justify-between border-t border-line pt-3 text-base">
            <dt className="font-display">Total</dt>
            <dd className="font-medium tabular-nums">{order.total.display}</dd>
          </div>
        </dl>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="wc-panel p-5">
          <h3 className="wc-eyebrow mb-3">Delivered to</h3>
          <address className="text-sm not-italic leading-relaxed text-muted">
            {order.shipping_address.name}<br />
            {order.shipping_address.line1}<br />
            {order.shipping_address.city}, {order.shipping_address.province}<br />
            {order.shipping_address.phone}
          </address>
        </div>
        <div className="wc-panel p-5">
          <h3 className="wc-eyebrow mb-3">Progress</h3>
          <ol className="space-y-2 text-sm">
            {order.timeline.map((event, index) => (
              <li key={index} className="flex gap-2.5">
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-[var(--wc-brass)]" />
                <div>
                  <p>{event.message}</p>
                  <p className="text-xs text-faint">{formatDateTime(event.at)}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  )
}

/* ── Addresses ───────────────────────────────────────────────────────────── */
interface AddressRecord {
  id: string
  label: string | null
  full_name: string
  phone: string
  line1: string
  line2: string | null
  area: string | null
  landmark: string | null
  city: string
  province: Province
  province_label: string
  postal_code: string | null
  is_default_shipping: boolean
  is_default_billing: boolean
}

const EMPTY_ADDRESS = {
  label: '', full_name: '', phone: '', line1: '', line2: '', area: '',
  landmark: '', city: '', province: 'punjab' as Province, postal_code: '',
  is_default_shipping: false, is_default_billing: false,
}

export function AccountAddresses() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<AddressRecord | null>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ ...EMPTY_ADDRESS })
  const [errors, setErrors] = useState<Record<string, string>>({})

  const { data: addresses = [], isLoading } = useQuery({
    queryKey: ['addresses'],
    queryFn: () => get<AddressRecord[]>('/addresses'),
  })

  const close = () => {
    setCreating(false)
    setEditing(null)
    setErrors({})
    setForm({ ...EMPTY_ADDRESS })
  }

  const save = useMutation({
    mutationFn: () =>
      editing
        ? put<AddressRecord>(`/addresses/${editing.id}`, form)
        : post<AddressRecord>('/addresses', form),
    onSuccess: () => {
      toast.success(editing ? 'Address updated' : 'Address saved')
      queryClient.invalidateQueries({ queryKey: ['addresses'] })
      close()
    },
    onError: (error) => {
      if (error instanceof ApiError) setErrors(error.fieldErrors)
      toast.error(error instanceof ApiError ? error.message : 'Could not save')
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => del<ApiMessage>(`/addresses/${id}`),
    onSuccess: () => {
      toast.success('Address removed')
      queryClient.invalidateQueries({ queryKey: ['addresses'] })
    },
  })

  const openEdit = (address: AddressRecord) => {
    setEditing(address)
    setForm({
      label: address.label ?? '', full_name: address.full_name, phone: address.phone,
      line1: address.line1, line2: address.line2 ?? '', area: address.area ?? '',
      landmark: address.landmark ?? '', city: address.city, province: address.province,
      postal_code: address.postal_code ?? '',
      is_default_shipping: address.is_default_shipping,
      is_default_billing: address.is_default_billing,
    })
  }

  const bind = (key: keyof typeof form) =>
    (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value }))

  if (isLoading) return <Skeleton className="h-64 w-full" />

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="font-display text-xl">Saved addresses</h2>
        <Button size="sm" onClick={() => setCreating(true)}>Add address</Button>
      </div>

      {addresses.length === 0 ? (
        <EmptyState
          icon={<MapPin size={36} strokeWidth={1} />}
          title="No addresses saved"
          description="Save one now and checkout will be quicker next time."
          action={<Button onClick={() => setCreating(true)}>Add your first address</Button>}
        />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {addresses.map((address) => (
            <li key={address.id} className="wc-panel p-5">
              <div className="mb-2 flex items-start justify-between gap-2">
                <span className="font-medium">{address.label || 'Address'}</span>
                <div className="flex gap-1">
                  {address.is_default_shipping && <Badge tone="neutral">Default</Badge>}
                </div>
              </div>
              <address className="text-sm not-italic leading-relaxed text-muted">
                {address.full_name}<br />
                {address.line1}<br />
                {address.area && <>{address.area}<br /></>}
                {address.landmark && <span className="text-faint">{address.landmark}<br /></span>}
                {address.city}, {address.province_label}
                {address.postal_code && <> {address.postal_code}</>}<br />
                {address.phone}
              </address>
              <div className="mt-4 flex gap-3 border-t border-line pt-3 text-xs">
                <button onClick={() => openEdit(address)} className="text-muted hover:text-ink">
                  Edit
                </button>
                <button
                  onClick={() => remove.mutate(address.id)}
                  className="flex items-center gap-1 text-muted hover:text-[var(--wc-danger)]"
                >
                  <Trash2 size={12} strokeWidth={1.5} /> Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal
        open={creating || editing !== null}
        onClose={close}
        title={editing ? 'Edit address' : 'Add address'}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={close}>Cancel</Button>
            {/* The footer sits outside the form element, so bind the button to
                it by id. Without this the Save button submitted with no owning
                form and skipped every required-field check. */}
            <Button type="submit" form="address-form" loading={save.isPending}>Save</Button>
          </div>
        }
      >
        <form
          id="address-form"
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            save.mutate()
          }}
        >
          <Field label="Label" id="label" hint="Home, Office">
            <Input id="label" value={form.label} onChange={bind('label')} />
          </Field>
          <Field label="Full name" id="full_name" error={errors.full_name} required>
            <Input id="full_name" required value={form.full_name} onChange={bind('full_name')} />
          </Field>
          <Field label="Mobile" id="phone" error={errors.phone} required>
            <Input id="phone" required placeholder="0300 1234567" value={form.phone} onChange={bind('phone')} />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Address" id="line1" error={errors.line1} required>
              <Input id="line1" required value={form.line1} onChange={bind('line1')} />
            </Field>
          </div>
          <Field label="Area" id="area">
            <Input id="area" value={form.area} onChange={bind('area')} />
          </Field>
          <Field label="Landmark" id="landmark">
            <Input id="landmark" value={form.landmark} onChange={bind('landmark')} />
          </Field>
          <Field label="City" id="city" error={errors.city} required>
            <Input id="city" required value={form.city} onChange={bind('city')} />
          </Field>
          <Field label="Province" id="province">
            <Select id="province" value={form.province} onChange={bind('province')}>
              {PROVINCES.map((province) => (
                <option key={province.value} value={province.value}>{province.label}</option>
              ))}
            </Select>
          </Field>
          <Field label="Postal code" id="postal_code" error={errors.postal_code}>
            <Input id="postal_code" maxLength={5} value={form.postal_code} onChange={bind('postal_code')} />
          </Field>
          <div className="sm:col-span-2 space-y-2">
            <Checkbox
              label="Default delivery address"
              checked={form.is_default_shipping}
              onChange={(event) =>
                setForm((c) => ({ ...c, is_default_shipping: event.target.checked }))
              }
            />
          </div>
        </form>
      </Modal>
    </>
  )
}

/* ── Profile ─────────────────────────────────────────────────────────────── */
export function AccountProfile() {
  const user = useAuthStore((state) => state.user)
  const setUser = useAuthStore((state) => state.setUser)
  const [form, setForm] = useState({
    full_name: user?.full_name ?? '',
    phone: user?.phone ?? '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})

  const { data: prefs } = useQuery({
    queryKey: ['notification-prefs'],
    queryFn: () => get<NotificationPreferences>('/auth/me/notifications'),
  })
  const queryClient = useQueryClient()

  const save = useMutation({
    mutationFn: () => patch<typeof user>('/auth/me', form),
    onSuccess: (updated) => {
      if (updated) setUser(updated)
      toast.success('Profile updated')
    },
    onError: (error) => {
      if (error instanceof ApiError) setErrors(error.fieldErrors)
      toast.error(error instanceof ApiError ? error.message : 'Could not save')
    },
  })

  const savePref = useMutation({
    mutationFn: (patchBody: Partial<NotificationPreferences>) =>
      patch<NotificationPreferences>('/auth/me/notifications', patchBody),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-prefs'] })
      toast.success('Preferences saved')
    },
  })

  const resend = useMutation({
    mutationFn: () => post<ApiMessage>('/auth/resend-verification'),
    onSuccess: (result) => toast.success(result.message),
  })

  const PREF_LABELS: [keyof NotificationPreferences, string][] = [
    ['email_order_updates', 'Order updates by email'],
    ['email_marketing', 'News and offers by email'],
    ['email_back_in_stock', 'Back in stock alerts'],
    ['email_price_drop', 'Price drop alerts'],
    ['email_review_reminder', 'Review reminders'],
    ['sms_order_updates', 'Order updates by SMS'],
    ['sms_marketing', 'Offers by SMS'],
  ]

  return (
    <div className="space-y-10">
      <section>
        <h2 className="mb-5 font-display text-xl">Your details</h2>
        <form
          className="max-w-md space-y-4"
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            setErrors({})
            save.mutate()
          }}
        >
          <Field label="Full name" id="full_name" error={errors.full_name}>
            <Input
              id="full_name"
              value={form.full_name}
              onChange={(event) => setForm((c) => ({ ...c, full_name: event.target.value }))}
            />
          </Field>
          <Field label="Mobile" id="phone" error={errors.phone}>
            <Input
              id="phone"
              placeholder="0300 1234567"
              value={form.phone}
              onChange={(event) => setForm((c) => ({ ...c, phone: event.target.value }))}
            />
          </Field>
          <Field label="Email" id="email" hint="Contact us to change your email address">
            <Input id="email" value={user?.email ?? ''} disabled />
          </Field>
          {user && !user.is_email_verified && (
            <div className="flex items-center gap-3 border border-line bg-warning-bg p-3 text-sm">
              <span className="flex-1">Your email is not confirmed yet.</span>
              <Button size="sm" variant="outline" loading={resend.isPending}
                      onClick={() => resend.mutate()}>
                Resend
              </Button>
            </div>
          )}
          <Button type="submit" loading={save.isPending}>Save changes</Button>
        </form>
      </section>

      <section>
        <h2 className="mb-5 font-display text-xl">Notifications</h2>
        <div className="max-w-md space-y-3">
          {prefs &&
            PREF_LABELS.map(([key, label]) => (
              <Checkbox
                key={key}
                label={label}
                checked={prefs[key]}
                onChange={(event) => savePref.mutate({ [key]: event.target.checked })}
              />
            ))}
        </div>
      </section>
    </div>
  )
}

/* ── Wishlist ────────────────────────────────────────────────────────────── */
export function AccountWishlist() {
  const hydrateWishlist = useWishlistStore((state) => state.hydrate)
  const { data: products = [], isLoading, isError } = useQuery({
    queryKey: ['wishlist'],
    queryFn: () => get<ProductCard[]>('/wishlist'),
  })

  // Sync the local heart state to what the server actually holds, so a fresh
  // device shows the right pieces as saved.
  useEffect(() => {
    if (products.length) hydrateWishlist(products.map((p) => p.slug))
  }, [products, hydrateWishlist])

  if (isLoading) return <Skeleton className="h-64 w-full" />
  if (isError) {
    return (
      <EmptyState
        icon={<Heart size={38} strokeWidth={1} />}
        title="We could not load your wishlist"
        description="Please refresh the page to try again."
      />
    )
  }

  if (products.length === 0) {
    return (
      <EmptyState
        icon={<Heart size={38} strokeWidth={1} />}
        title="Nothing saved yet"
        description="Tap the heart on any piece to save it here."
        action={<Link to="/shop" className="wc-btn wc-btn-primary">Browse the collection</Link>}
      />
    )
  }

  return (
    <>
      <h2 className="mb-6 font-display text-xl">Saved pieces</h2>
      <ProductGrid products={products} />
    </>
  )
}

/* ── Security ────────────────────────────────────────────────────────────── */
export function AccountSecurity() {
  const [form, setForm] = useState({ current_password: '', password: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const queryClient = useQueryClient()

  const { data: sessions = [] } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => get<Session[]>('/auth/sessions'),
  })

  const change = useMutation({
    mutationFn: () => post<ApiMessage>('/auth/change-password', form),
    onSuccess: (result) => {
      toast.success(result.message)
      setForm({ current_password: '', password: '' })
    },
    onError: (error) => {
      if (error instanceof ApiError) setErrors(error.fieldErrors)
      toast.error(error instanceof ApiError ? error.message : 'Could not change password')
    },
  })

  const revoke = useMutation({
    mutationFn: (id: string) => del<ApiMessage>(`/auth/sessions/${id}`),
    onSuccess: () => {
      toast.success('Session ended')
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })

  const logoutAll = useMutation({
    mutationFn: () => post<ApiMessage>('/auth/logout-all'),
    onSuccess: () => {
      toast.success('Signed out everywhere')
      window.location.href = '/login'
    },
  })

  return (
    <div className="space-y-10">
      <section>
        <h2 className="mb-5 font-display text-xl">Change password</h2>
        <form
          className="max-w-md space-y-4"
          onSubmit={(event: FormEvent) => {
            event.preventDefault()
            setErrors({})
            change.mutate()
          }}
        >
          <Field label="Current password" id="current" error={errors.current_password}>
            <Input
              id="current" type="password" required autoComplete="current-password"
              value={form.current_password}
              onChange={(e) => setForm((c) => ({ ...c, current_password: e.target.value }))}
            />
          </Field>
          <Field label="New password" id="new" error={errors.password} hint="At least 8 characters">
            <Input
              id="new" type="password" required autoComplete="new-password"
              value={form.password}
              onChange={(e) => setForm((c) => ({ ...c, password: e.target.value }))}
            />
          </Field>
          <Button type="submit" loading={change.isPending}>Change password</Button>
        </form>
      </section>

      <section>
        <div className="mb-5 flex items-center justify-between">
          <h2 className="font-display text-xl">Where you are signed in</h2>
          <Button variant="outline" size="sm" loading={logoutAll.isPending}
                  onClick={() => logoutAll.mutate()}>
            Sign out everywhere
          </Button>
        </div>
        <ul className="divide-y divide-[var(--wc-border-subtle)] border-y border-line">
          {sessions.map((session) => (
            <li key={session.session_id} className="flex items-center justify-between gap-4 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm">{session.user_agent ?? 'Unknown device'}</p>
                <p className="text-xs text-faint">
                  {session.ip_address} · started {relativeTime(session.created_at)}
                </p>
              </div>
              <button
                onClick={() => revoke.mutate(session.session_id)}
                className="shrink-0 text-xs text-muted hover:text-[var(--wc-danger)]"
              >
                End session
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
