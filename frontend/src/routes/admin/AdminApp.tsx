/**
 * Admin panel.
 *
 * Lives in the same Vite app but behind a lazy route, so a shopper never
 * downloads the charts and data tables. Same design tokens as the storefront,
 * but a denser rhythm: Fraunces appears in exactly two places here, the page
 * heading and the dashboard KPI values. Everything else is Inter, or the tool
 * starts looking precious instead of usable.
 */

import { useRef, useState, type ChangeEvent, type ReactNode } from 'react'
import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  AlertTriangle,
  ArrowLeft,
  Boxes,
  FileText,
  Gift,
  LifeBuoy,
  Newspaper,
  Ticket,
  Undo2,
  Upload,
  ClipboardList,
  LayoutDashboard,
  Mail,
  MessageSquare,
  Package,
  Search,
  Settings as SettingsIcon,
  Star,
  Users,
} from 'lucide-react'

import { api, ApiError, del, download, get, patch, post, put } from '@/lib/api'
import { cn } from '@/lib/cn'
import { formatDate, formatDateTime, relativeTime } from '@/lib/format'
import {
  Badge,
  Button,
  Checkbox,
  EmptyState,
  Field,
  Input,
  Modal,
  Select,
  Skeleton,
  Textarea,
} from '@/components/ui'
import { useChartColors } from '@/hooks/useChartColors'
import { useAuthStore } from '@/features/auth/store'
import { Wordmark } from '@/components/Layout'
import {
  AdminBlog,
  AdminCoupons,
  AdminGiftCards,
  AdminImport,
  AdminPages,
  AdminReturns,
  AdminTickets,
} from './content'
import type { ApiMessage } from '@/lib/types'

const NAV = [
  { to: '/admin', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/admin/orders', label: 'Orders', icon: ClipboardList },
  { to: '/admin/products', label: 'Products', icon: Package },
  { to: '/admin/inventory', label: 'Inventory', icon: Boxes },
  { to: '/admin/customers', label: 'Customers', icon: Users },
  { to: '/admin/returns', label: 'Returns', icon: Undo2 },
  { to: '/admin/reviews', label: 'Reviews', icon: Star },
  { to: '/admin/tickets', label: 'Support', icon: LifeBuoy },
  { to: '/admin/coupons', label: 'Coupons', icon: Ticket },
  { to: '/admin/gift-cards', label: 'Gift cards', icon: Gift },
  { to: '/admin/blog', label: 'Journal', icon: Newspaper },
  { to: '/admin/pages', label: 'Pages', icon: FileText },
  { to: '/admin/import', label: 'Bulk import', icon: Upload },
  { to: '/admin/notifications', label: 'Notifications', icon: Mail },
  { to: '/admin/audit', label: 'Audit log', icon: MessageSquare },
  { to: '/admin/settings', label: 'Settings', icon: SettingsIcon },
]

function Shell({ children }: { children: ReactNode }) {
  const user = useAuthStore((state) => state.user)

  return (
    <div className="flex min-h-dvh bg-canvas">
      {/* The one place a fixed dark surface is allowed regardless of theme:
          an admin sidebar reads as chrome, not as content. */}
      <aside className="hidden w-52 shrink-0 flex-col border-r border-line bg-sunken lg:flex">
        <div className="border-b border-line px-5 py-4">
          <Link to="/" className="text-lg"><Wordmark /></Link>
          <p className="wc-eyebrow mt-1 text-[0.6rem]">Admin</p>
        </div>

        <nav className="flex-1 space-y-0.5 p-3">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 rounded-[2px] px-2.5 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-surface text-ink shadow-sm'
                    : 'text-muted hover:text-ink',
                )
              }
            >
              <Icon size={15} strokeWidth={1.5} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-line p-3">
          <p className="truncate px-2.5 text-xs text-faint">{user?.email}</p>
          <Link
            to="/"
            className="mt-2 flex items-center gap-2 px-2.5 py-1.5 text-xs text-muted hover:text-ink"
          >
            <ArrowLeft size={12} strokeWidth={1.5} /> Back to store
          </Link>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <nav className="flex gap-1 overflow-x-auto border-b border-line bg-sunken px-3 py-2 lg:hidden wc-no-scrollbar">
          {NAV.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn('whitespace-nowrap px-3 py-1.5 text-xs',
                   isActive ? 'bg-surface text-ink' : 'text-muted')
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-5 lg:p-8">{children}</div>
      </div>
    </div>
  )
}

function PageHeading({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      {/* One of only two places Fraunces appears in admin. */}
      <h1 className="font-display text-2xl">{title}</h1>
      {action}
    </div>
  )
}

function StatTile({
  label, value, sub, change,
}: {
  label: string
  value: string
  sub?: string
  change?: number | null
}) {
  return (
    <div className="wc-panel p-4">
      <p className="wc-eyebrow mb-2">{label}</p>
      {/* The other place Fraunces appears. */}
      <p className="font-display text-2xl">{value}</p>
      <div className="mt-1 flex items-center gap-2 text-xs">
        {sub && <span className="text-faint">{sub}</span>}
        {change !== null && change !== undefined && (
          <span className={change >= 0 ? 'text-[var(--wc-success)]' : 'text-[var(--wc-danger)]'}>
            {change >= 0 ? '+' : ''}{change}%
          </span>
        )}
      </div>
    </div>
  )
}

function DataTable<T>({
  columns, rows, loading, empty,
}: {
  columns: { key: string; label: string; render: (row: T) => ReactNode; className?: string }[]
  rows: T[] | undefined
  loading?: boolean
  empty?: string
}) {
  if (loading) return <Skeleton className="h-64 w-full" />
  if (!rows?.length) return <EmptyState title={empty ?? 'Nothing here yet'} />

  return (
    <div className="wc-scroll-x wc-panel">
      <table className="w-full min-w-[44rem] border-collapse text-sm">
        <thead>
          <tr className="border-b border-line">
            {columns.map((column) => (
              <th key={column.key}
                  className={cn('px-4 py-3 text-left wc-eyebrow', column.className)}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-line last:border-0 hover:bg-sunken">
              {columns.map((column) => (
                <td key={column.key} className={cn('px-4 py-3', column.className)}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ── Dashboard ───────────────────────────────────────────────────────────── */
function Dashboard() {
  const [days, setDays] = useState(30)
  const colors = useChartColors()
  const { data, isLoading } = useQuery({
    queryKey: ['admin-dashboard', days],
    queryFn: () => get<any>('/admin/dashboard', { days }),
  })

  if (isLoading || !data) return <Skeleton className="h-96 w-full" />

  return (
    <>
      <PageHeading
        title="Dashboard"
        action={
          <Select value={days} onChange={(e) => setDays(Number(e.target.value))}
                  className="w-auto py-1.5 text-xs">
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </Select>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Revenue" value={data.revenue.display}
                  change={data.revenue.change_percent} sub={`last ${days} days`} />
        <StatTile label="Orders" value={String(data.orders.count)}
                  change={data.orders.change_percent} />
        <StatTile label="Average order" value={data.average_order_value.display} />
        <StatTile label="New customers" value={String(data.new_customers)} />
      </div>

      {(data.attention.pending_reviews > 0 ||
        data.attention.open_returns > 0 ||
        data.attention.flagged_orders > 0) && (
        <div className="mt-4 flex flex-wrap gap-2">
          {data.attention.pending_reviews > 0 && (
            <Link to="/admin/reviews" className="wc-badge wc-badge-low">
              <AlertTriangle size={11} /> {data.attention.pending_reviews} reviews awaiting moderation
            </Link>
          )}
          {data.attention.open_returns > 0 && (
            <span className="wc-badge bg-info-bg text-info">
              {data.attention.open_returns} open returns
            </span>
          )}
          {data.attention.flagged_orders > 0 && (
            <Link to="/admin/orders?flagged=true" className="wc-badge bg-danger-bg text-danger">
              {data.attention.flagged_orders} flagged orders
            </Link>
          )}
        </div>
      )}

      <div className="mt-6 wc-panel p-5">
        <h2 className="wc-eyebrow mb-4">Revenue</h2>
        <div style={{ height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.series} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
              <defs>
                <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={colors.series[0]} stopOpacity={0.32} />
                  <stop offset="100%" stopColor={colors.series[0]} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={colors.grid} vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: colors.axis }}
                     tickLine={false} axisLine={false}
                     tickFormatter={(v) => String(v).slice(5)} minTickGap={24} />
              <YAxis tick={{ fontSize: 10, fill: colors.axis }}
                     tickLine={false} axisLine={false}
                     tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
              <Tooltip
                contentStyle={{
                  background: colors.surface,
                  border: `1px solid ${colors.border}`,
                  borderRadius: 2, fontSize: 12, color: colors.text,
                }}
                formatter={(value) => [`Rs ${Number(value).toLocaleString()}`, 'Revenue']}
              />
              {/* Animation off. It is rAF driven, so it never completes in a
                  headless render and the series paints as nothing at all. It
                  is also just noise on a dashboard somebody reloads all day. */}
              <Area type="monotone" dataKey="revenue_rupees" stroke={colors.series[0]}
                    strokeWidth={2} fill="url(#rev)" isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="wc-panel p-5">
          <h2 className="wc-eyebrow mb-4">Best sellers</h2>
          <ul className="space-y-2.5 text-sm">
            {data.best_sellers.map((item: any) => (
              <li key={item.name} className="flex items-center justify-between gap-3">
                <span className="truncate">{item.name}</span>
                <span className="shrink-0 text-xs text-faint tabular-nums">
                  {item.units} units · {item.revenue}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="wc-panel p-5">
          <h2 className="wc-eyebrow mb-4">Running low</h2>
          {data.low_stock.length === 0 ? (
            <p className="text-sm text-faint">Nothing is low on stock.</p>
          ) : (
            <ul className="space-y-2.5 text-sm">
              {data.low_stock.map((item: any) => (
                <li key={item.sku} className="flex items-center justify-between gap-3">
                  <span className="truncate">{item.product}</span>
                  <Badge tone={item.available === 0 ? 'out' : 'low'}>
                    {item.available === 0 ? 'Out' : `${item.available} left`}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {data.zero_result_searches.length > 0 && (
        <div className="mt-4 wc-panel p-5">
          <h2 className="wc-eyebrow mb-2">Searches with no results</h2>
          <p className="mb-4 text-xs text-faint">
            Demand the catalogue cannot currently meet.
          </p>
          <div className="flex flex-wrap gap-2">
            {data.zero_result_searches.map((item: any) => (
              <span key={item.query} className="wc-badge bg-sunken text-muted">
                {item.query} <span className="text-faint">×{item.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </>
  )
}

/* ── Orders ──────────────────────────────────────────────────────────────── */
const ORDER_STATUSES = [
  'pending', 'confirmed', 'processing', 'shipped',
  'out_for_delivery', 'delivered', 'cancelled', 'refunded',
]

function Orders() {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<any>(null)
  const [newStatus, setNewStatus] = useState('')
  const [tracking, setTracking] = useState('')
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin-orders', q, status, page],
    queryFn: () => get<any>('/admin/orders', { q, status, page, per_page: 25 }),
  })

  const update = useMutation({
    mutationFn: () =>
      post<ApiMessage>(`/admin/orders/${selected.id}/status`, {
        status: newStatus,
        tracking_number: tracking || undefined,
      }),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-orders'] })
      setSelected(null)
      setTracking('')
    },
    onError: (error) =>
      toast.error(error instanceof ApiError ? error.message : 'Could not update'),
  })

  return (
    <>
      <PageHeading
        title="Orders"
        action={
          <Button
            variant="outline"
            size="sm"
            onClick={() => download('/admin/orders/export', 'orders.csv')}
          >
            Export CSV
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[14rem]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
          <Input placeholder="Order number, name or city" value={q}
                 onChange={(e) => { setQ(e.target.value); setPage(1) }}
                 className="pl-9 py-2 text-sm" />
        </div>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}
                className="w-auto py-2 text-sm">
          <option value="">All statuses</option>
          {ORDER_STATUSES.map((s) => (
            <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
          ))}
        </Select>
      </div>

      <DataTable
        loading={isLoading}
        rows={data?.items}
        empty="No orders match"
        columns={[
          { key: 'number', label: 'Order',
            render: (row: any) => (
              <span className="font-mono text-xs">{row.order_number}</span>
            ) },
          { key: 'customer', label: 'Customer',
            render: (row: any) => (
              <div>
                <p>{row.customer}</p>
                <p className="text-xs text-faint">{row.city}</p>
              </div>
            ) },
          { key: 'date', label: 'Placed',
            render: (row: any) => (
              <span className="text-xs text-muted">{formatDate(row.placed_at)}</span>
            ) },
          { key: 'items', label: 'Items', className: 'text-center',
            render: (row: any) => <span className="tabular-nums">{row.item_count}</span> },
          { key: 'total', label: 'Total', className: 'text-right',
            render: (row: any) => (
              <span className="tabular-nums">{row.total.display}</span>
            ) },
          { key: 'status', label: 'Status',
            render: (row: any) => (
              <div className="flex items-center gap-1.5">
                <Badge tone={
                  row.status === 'delivered' ? 'success'
                  : row.status === 'cancelled' || row.status === 'refunded' ? 'danger'
                  : 'neutral'
                }>
                  {row.status_label}
                </Badge>
                {row.is_flagged && <AlertTriangle size={13} className="text-[var(--wc-danger)]" />}
              </div>
            ) },
          { key: 'actions', label: '', className: 'text-right',
            render: (row: any) => (
              <button
                onClick={() => { setSelected(row); setNewStatus(row.status) }}
                className="text-xs text-muted hover:text-ink"
              >
                Update
              </button>
            ) },
        ]}
      />

      {data && data.pages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2 text-sm">
          <Button size="sm" variant="outline" disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span className="text-xs text-faint tabular-nums">
            Page {data.page} of {data.pages} · {data.total} orders
          </span>
          <Button size="sm" variant="outline" disabled={page >= data.pages}
                  onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      )}

      <Modal
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={`Update ${selected?.order_number ?? ''}`}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setSelected(null)}>Cancel</Button>
            <Button loading={update.isPending} onClick={() => update.mutate()}>Save</Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Field label="Status" id="status">
            <Select id="status" value={newStatus} onChange={(e) => setNewStatus(e.target.value)}>
              {ORDER_STATUSES.map((s) => (
                <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
              ))}
            </Select>
          </Field>
          {newStatus === 'shipped' && (
            <Field label="Tracking number" id="tracking"
                   hint="Creates a shipment and emails the customer">
              <Input id="tracking" value={tracking} onChange={(e) => setTracking(e.target.value)} />
            </Field>
          )}
          {newStatus === 'cancelled' && (
            <p className="text-xs text-muted">
              Cancelling returns the stock and records why in the inventory ledger.
            </p>
          )}
        </div>
      </Modal>
    </>
  )
}

/* ── Products ────────────────────────────────────────────────────────────── */
const WOOD_SPECIES = [
  'sheesham', 'walnut', 'teak', 'mango', 'acacia', 'deodar', 'oak', 'pine',
]

const EMPTY_PRODUCT = {
  name: '', category_id: '', base_price_pkr: '', sku: '',
  initial_stock: '0', wood_species: '', status: 'draft',
}

function Products() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [imagesFor, setImagesFor] = useState<any>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ ...EMPTY_PRODUCT })
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin-products', q, page],
    queryFn: () => get<any>('/admin/products', { q, page, per_page: 25 }),
  })

  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: () => get<any[]>('/categories'),
    staleTime: 10 * 60_000,
  })

  const toggleFeatured = useMutation({
    mutationFn: ({ id, value }: { id: string; value: boolean }) =>
      patch<ApiMessage>(`/admin/products/${id}`, { is_featured: value }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-products'] })
      toast.success('Product updated')
    },
  })

  const create = useMutation({
    mutationFn: () =>
      post<{ message: string }>('/admin/products', {
        name: form.name,
        category_id: form.category_id,
        base_price_paisa: Math.round(Number(form.base_price_pkr) * 100),
        sku: form.sku,
        initial_stock: Number(form.initial_stock) || 0,
        wood_species: form.wood_species || null,
        status: form.status,
      }),
    onSuccess: (r) => {
      toast.success(r.message)
      queryClient.invalidateQueries({ queryKey: ['admin-products'] })
      setCreating(false)
      setForm({ ...EMPTY_PRODUCT })
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not create product'),
  })

  const canCreate =
    form.name.trim().length >= 2 &&
    form.category_id &&
    Number(form.base_price_pkr) > 0 &&
    form.sku.trim().length >= 2

  return (
    <>
      <PageHeading
        title="Products"
        action={
          <Button size="sm" onClick={() => setCreating(true)}>New product</Button>
        }
      />

      <div className="mb-4 relative max-w-md">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
        <Input placeholder="Search products" value={q}
               onChange={(e) => { setQ(e.target.value); setPage(1) }}
               className="pl-9 py-2 text-sm" />
      </div>

      <DataTable
        loading={isLoading}
        rows={data?.items}
        columns={[
          { key: 'name', label: 'Product',
            render: (row: any) => (
              <div>
                <Link to={`/product/${row.slug}`} target="_blank"
                      className="hover:text-[var(--wc-brass-text)]">{row.name}</Link>
                <p className="text-xs text-faint">{row.category}</p>
              </div>
            ) },
          { key: 'price', label: 'Price', className: 'text-right',
            render: (row: any) => <span className="tabular-nums">{row.price.display}</span> },
          { key: 'variants', label: 'Variants', className: 'text-center',
            render: (row: any) => <span className="tabular-nums">{row.variant_count}</span> },
          { key: 'stock', label: 'Stock', className: 'text-center',
            render: (row: any) => (
              <span className={cn('tabular-nums', row.stock === 0 && 'text-[var(--wc-danger)]')}>
                {row.stock}
              </span>
            ) },
          { key: 'rating', label: 'Rating', className: 'text-center',
            render: (row: any) => (
              <span className="tabular-nums text-xs text-muted">
                {row.rating_average > 0 ? row.rating_average.toFixed(1) : '—'}
              </span>
            ) },
          { key: 'status', label: 'Status',
            render: (row: any) => (
              <Badge tone={row.status === 'active' ? 'success' : 'neutral'}>{row.status}</Badge>
            ) },
          { key: 'featured', label: 'Featured', className: 'text-center',
            render: (row: any) => (
              <Checkbox
                label={null}
                checked={row.is_featured}
                aria-label={`Feature ${row.name}`}
                onChange={(e) =>
                  toggleFeatured.mutate({ id: row.id, value: e.target.checked })
                }
              />
            ) },
          { key: 'images', label: 'Images', className: 'text-right',
            render: (row: any) => (
              <Button size="sm" variant="ghost" onClick={() => setImagesFor(row)}>
                Manage
              </Button>
            ) },
        ]}
      />

      {imagesFor && (
        <ProductImagesModal product={imagesFor} onClose={() => setImagesFor(null)} />
      )}

      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title="New product"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setCreating(false)}>Cancel</Button>
            <Button
              form="new-product-form"
              type="submit"
              loading={create.isPending}
              disabled={!canCreate}
            >
              Create
            </Button>
          </div>
        }
      >
        <form
          id="new-product-form"
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => { e.preventDefault(); if (canCreate) create.mutate() }}
        >
          <Field label="Name" id="np-name" required>
            <Input id="np-name" required value={form.name}
                   onChange={(e) => setForm((c) => ({ ...c, name: e.target.value }))} />
          </Field>
          <Field label="Category" id="np-cat" required>
            <Select id="np-cat" value={form.category_id}
                    onChange={(e) => setForm((c) => ({ ...c, category_id: e.target.value }))}>
              <option value="">Choose…</option>
              {categories.map((c: any) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </Select>
          </Field>
          <Field label="Base price (Rs)" id="np-price" required>
            <Input id="np-price" type="number" min="1" required value={form.base_price_pkr}
                   onChange={(e) => setForm((c) => ({ ...c, base_price_pkr: e.target.value }))} />
          </Field>
          <Field label="SKU" id="np-sku" required hint="Unique stock code">
            <Input id="np-sku" required value={form.sku}
                   onChange={(e) => setForm((c) => ({ ...c, sku: e.target.value }))} />
          </Field>
          <Field label="Initial stock" id="np-stock">
            <Input id="np-stock" type="number" min="0" value={form.initial_stock}
                   onChange={(e) => setForm((c) => ({ ...c, initial_stock: e.target.value }))} />
          </Field>
          <Field label="Wood" id="np-wood">
            <Select id="np-wood" value={form.wood_species}
                    onChange={(e) => setForm((c) => ({ ...c, wood_species: e.target.value }))}>
              <option value="">Not specified</option>
              {WOOD_SPECIES.map((w) => (
                <option key={w} value={w}>{w[0].toUpperCase() + w.slice(1)}</option>
              ))}
            </Select>
          </Field>
          <Field label="Status" id="np-status">
            <Select id="np-status" value={form.status}
                    onChange={(e) => setForm((c) => ({ ...c, status: e.target.value }))}>
              <option value="draft">Draft</option>
              <option value="active">Active (published)</option>
            </Select>
          </Field>
        </form>
        <p className="mt-3 text-xs text-faint">
          Creates the product with one variant and a placeholder image. Add real
          photos and more variants after saving.
        </p>
      </Modal>

      {data && data.pages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <Button size="sm" variant="outline" disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span className="text-xs text-faint">Page {data.page} of {data.pages}</span>
          <Button size="sm" variant="outline" disabled={page >= data.pages}
                  onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      )}
    </>
  )
}

interface AdminImage {
  id: string
  url: string
  thumb_url: string
  alt_text: string
  is_primary: boolean
  source: string
}

function ProductImagesModal({ product, onClose }: { product: any; onClose: () => void }) {
  const queryClient = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  const { data: images = [], isLoading } = useQuery({
    queryKey: ['admin-product-images', product.id],
    queryFn: () => get<AdminImage[]>(`/admin/products/${product.id}/images`),
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['admin-product-images', product.id] })
    queryClient.invalidateQueries({ queryKey: ['admin-products'] })
  }

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      await api(`/admin/products/${product.id}/images`, { method: 'POST', body: form })
      toast.success('Image uploaded')
      refresh()
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : 'Upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const setPrimary = useMutation({
    mutationFn: (id: string) => post<ApiMessage>(`/admin/products/images/${id}/primary`),
    onSuccess: () => { toast.success('Primary image set'); refresh() },
  })
  const remove = useMutation({
    mutationFn: (id: string) => del<ApiMessage>(`/admin/products/images/${id}`),
    onSuccess: () => { toast.success('Image removed'); refresh() },
    onError: () => toast.error('Could not remove the image'),
  })

  return (
    <Modal
      open
      onClose={onClose}
      title={`Images — ${product.name}`}
      footer={<Button variant="ghost" onClick={onClose}>Done</Button>}
    >
      <p className="mb-4 text-sm text-muted">
        Upload the actual product photos here. The first image becomes the main
        one shown on the storefront; use “Make main” to change it.
      </p>

      <div className="mb-5">
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          onChange={onFile}
          className="hidden"
        />
        <Button
          variant="outline"
          size="sm"
          loading={uploading}
          onClick={() => fileRef.current?.click()}
        >
          Upload image
        </Button>
      </div>

      {isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : images.length === 0 ? (
        <p className="text-sm text-faint">No images yet.</p>
      ) : (
        <div className="grid grid-cols-3 gap-3">
          {images.map((image) => (
            <div key={image.id} className="border border-line p-2">
              <img
                src={image.thumb_url}
                alt={image.alt_text}
                className="aspect-4/5 w-full object-cover"
                loading="lazy"
              />
              <div className="mt-2 flex items-center justify-between gap-1">
                {image.is_primary ? (
                  <Badge tone="success">Main</Badge>
                ) : (
                  <button
                    className="text-xs text-muted hover:text-ink"
                    onClick={() => setPrimary.mutate(image.id)}
                  >
                    Make main
                  </button>
                )}
                <button
                  className="text-xs text-[var(--wc-danger)] hover:underline"
                  onClick={() => remove.mutate(image.id)}
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}

/* ── Inventory ───────────────────────────────────────────────────────────── */
function Inventory() {
  const [lowOnly, setLowOnly] = useState(false)
  const [adjusting, setAdjusting] = useState<any>(null)
  const [delta, setDelta] = useState('')
  const [reason, setReason] = useState('restock')
  const [note, setNote] = useState('')
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin-inventory', lowOnly],
    queryFn: () => get<any>('/admin/inventory', { low_only: lowOnly, per_page: 100 }),
  })

  const adjust = useMutation({
    mutationFn: () =>
      post<ApiMessage>('/admin/inventory/adjust', {
        variant_id: adjusting.variant_id,
        delta: Number(delta),
        reason,
        note: note || undefined,
      }),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-inventory'] })
      setAdjusting(null)
      setDelta('')
      setNote('')
    },
    onError: (error) =>
      toast.error(error instanceof ApiError ? error.message : 'Could not adjust stock'),
  })

  return (
    <>
      <PageHeading
        title="Inventory"
        action={
          <Button size="sm" variant={lowOnly ? 'primary' : 'outline'}
                  onClick={() => setLowOnly((v) => !v)}>
            {lowOnly ? 'Showing low stock' : 'Show low stock only'}
          </Button>
        }
      />

      <DataTable
        loading={isLoading}
        rows={data?.items}
        columns={[
          { key: 'sku', label: 'SKU',
            render: (row: any) => <span className="font-mono text-xs">{row.sku}</span> },
          { key: 'product', label: 'Product',
            render: (row: any) => (
              <div>
                <p className="truncate">{row.product}</p>
                <p className="text-xs text-faint">{row.variant}</p>
              </div>
            ) },
          { key: 'on_hand', label: 'On hand', className: 'text-center',
            render: (row: any) => <span className="tabular-nums">{row.on_hand}</span> },
          { key: 'reserved', label: 'Reserved', className: 'text-center',
            render: (row: any) => (
              <span className="tabular-nums text-muted">{row.reserved}</span>
            ) },
          { key: 'available', label: 'Available', className: 'text-center',
            render: (row: any) => (
              <span className={cn('tabular-nums font-medium',
                row.available === 0 && 'text-[var(--wc-danger)]',
                row.is_low && row.available > 0 && 'text-[var(--wc-warning)]')}>
                {row.available}
              </span>
            ) },
          { key: 'actions', label: '', className: 'text-right',
            render: (row: any) => (
              <button onClick={() => setAdjusting(row)}
                      className="text-xs text-muted hover:text-ink">Adjust</button>
            ) },
        ]}
      />

      <Modal
        open={adjusting !== null}
        onClose={() => setAdjusting(null)}
        title="Adjust stock"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setAdjusting(null)}>Cancel</Button>
            <Button loading={adjust.isPending} onClick={() => adjust.mutate()}>Apply</Button>
          </div>
        }
      >
        <div className="space-y-4">
          <p className="text-sm text-muted">
            {adjusting?.product} · <span className="font-mono text-xs">{adjusting?.sku}</span>
            <br />
            Currently {adjusting?.on_hand} on hand, {adjusting?.reserved} reserved.
          </p>
          <Field label="Change" id="delta" hint="Positive to add, negative to remove">
            <Input id="delta" type="number" value={delta}
                   onChange={(e) => setDelta(e.target.value)} placeholder="e.g. 10 or -3" />
          </Field>
          <Field label="Reason" id="reason">
            <Select id="reason" value={reason} onChange={(e) => setReason(e.target.value)}>
              <option value="restock">Restock</option>
              <option value="damage">Damage</option>
              <option value="correction">Stocktake correction</option>
              <option value="return">Return to stock</option>
            </Select>
          </Field>
          <Field label="Note" id="note">
            <Textarea id="note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <p className="text-xs text-faint">
            Every adjustment is recorded in the ledger with your name against it.
          </p>
        </div>
      </Modal>
    </>
  )
}

/* ── Customers ───────────────────────────────────────────────────────────── */
function Customers() {
  const [q, setQ] = useState('')
  const { data, isLoading } = useQuery({
    queryKey: ['admin-customers', q],
    queryFn: () => get<any>('/admin/customers', { q, per_page: 50 }),
  })

  return (
    <>
      <PageHeading title="Customers" />
      <div className="mb-4 relative max-w-md">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
        <Input placeholder="Search by name or email" value={q}
               onChange={(e) => setQ(e.target.value)} className="pl-9 py-2 text-sm" />
      </div>

      <DataTable
        loading={isLoading}
        rows={data?.items}
        columns={[
          { key: 'name', label: 'Customer',
            render: (row: any) => (
              <div>
                <p>{row.name}</p>
                <p className="text-xs text-faint">{row.email}</p>
              </div>
            ) },
          { key: 'segment', label: 'Segment',
            render: (row: any) => (
              <Badge tone={row.segment === 'vip' ? 'success' : 'neutral'}>{row.segment}</Badge>
            ) },
          { key: 'orders', label: 'Orders', className: 'text-center',
            render: (row: any) => <span className="tabular-nums">{row.orders}</span> },
          { key: 'ltv', label: 'Lifetime value', className: 'text-right',
            render: (row: any) => (
              <span className="tabular-nums">{row.lifetime_value}</span>
            ) },
          { key: 'joined', label: 'Joined',
            render: (row: any) => (
              <span className="text-xs text-muted">{formatDate(row.joined)}</span>
            ) },
          { key: 'status', label: 'Status',
            render: (row: any) => (
              <div className="flex gap-1">
                {!row.is_active && <Badge tone="danger">Inactive</Badge>}
                {!row.verified && <Badge tone="warning">Unverified</Badge>}
                {row.role !== 'customer' && <Badge tone="info">{row.role}</Badge>}
              </div>
            ) },
        ]}
      />
    </>
  )
}

/* ── Reviews ─────────────────────────────────────────────────────────────── */
function Reviews() {
  const [status, setStatus] = useState('pending')
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['admin-reviews', status],
    queryFn: () => get<any>('/admin/reviews', { status, per_page: 50 }),
  })

  const moderate = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: string }) =>
      post<ApiMessage>(`/admin/reviews/${id}/moderate`, { status: decision }),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-reviews'] })
    },
  })

  return (
    <>
      <PageHeading
        title="Reviews"
        action={
          <Select value={status} onChange={(e) => setStatus(e.target.value)}
                  className="w-auto py-1.5 text-xs">
            <option value="pending">Awaiting moderation</option>
            <option value="approved">Published</option>
            <option value="rejected">Rejected</option>
          </Select>
        }
      />

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : !data?.items.length ? (
        <EmptyState title="Nothing to moderate" description="The queue is clear." />
      ) : (
        <ul className="space-y-3">
          {data.items.map((review: any) => (
            <li key={review.id} className="wc-panel p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{review.product}</span>
                    <span className="text-[var(--wc-brass)]">
                      {'★'.repeat(review.rating)}{'☆'.repeat(5 - review.rating)}
                    </span>
                    {review.verified_purchase && <Badge tone="success">Verified purchase</Badge>}
                  </div>
                  {review.title && <p className="text-sm font-medium">{review.title}</p>}
                  <p className="mt-1 text-sm text-muted">{review.body}</p>
                  <p className="mt-2 text-xs text-faint">
                    {review.author} · {relativeTime(review.created_at)}
                  </p>
                </div>
                {status === 'pending' && (
                  <div className="flex shrink-0 gap-2">
                    <Button size="sm"
                            onClick={() => moderate.mutate({ id: review.id, decision: 'approved' })}>
                      Approve
                    </Button>
                    <Button size="sm" variant="outline"
                            onClick={() => moderate.mutate({ id: review.id, decision: 'rejected' })}>
                      Reject
                    </Button>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

/* ── Notifications ───────────────────────────────────────────────────────── */
function Notifications() {
  const [reading, setReading] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['admin-notifications'],
    queryFn: () => get<any>('/admin/notifications', { per_page: 50 }),
  })

  const { data: message } = useQuery({
    queryKey: ['admin-notification', reading],
    queryFn: () => get<any>(`/admin/notifications/${reading}`),
    enabled: Boolean(reading),
  })

  return (
    <>
      <PageHeading title="Notifications" />
      <p className="mb-4 text-sm text-muted">
        Every email and SMS the store has sent. With no SMTP configured they
        live here, which is also a permanent audit trail.
      </p>

      <DataTable
        loading={isLoading}
        rows={data?.items}
        columns={[
          { key: 'channel', label: 'Channel',
            render: (row: any) => <Badge tone="neutral">{row.channel}</Badge> },
          { key: 'template', label: 'Type',
            render: (row: any) => (
              <span className="text-xs">{row.template?.replace(/_/g, ' ')}</span>
            ) },
          { key: 'recipient', label: 'To',
            render: (row: any) => <span className="text-xs">{row.recipient}</span> },
          { key: 'subject', label: 'Subject',
            render: (row: any) => (
              <span className="text-xs text-muted">{row.subject ?? '—'}</span>
            ) },
          { key: 'status', label: 'Status',
            render: (row: any) => (
              <Badge tone={
                row.status === 'sent' ? 'success'
                : row.status === 'failed' ? 'danger' : 'neutral'
              }>
                {row.status}
              </Badge>
            ) },
          { key: 'at', label: 'Sent',
            render: (row: any) => (
              <span className="text-xs text-faint">{relativeTime(row.at)}</span>
            ) },
          { key: 'actions', label: '', className: 'text-right',
            render: (row: any) => (
              <button onClick={() => setReading(row.id)}
                      className="text-xs text-muted hover:text-ink">Read</button>
            ) },
        ]}
      />

      <Modal open={reading !== null} onClose={() => setReading(null)}
             title={message?.subject ?? 'Message'} size="lg">
        {message && (
          <>
            <p className="mb-4 text-xs text-faint">
              To {message.recipient} · {formatDateTime(message.at)} · {message.status}
            </p>
            {message.body_html ? (
              <div className="border border-line bg-white p-2">
                <iframe
                  title="Message preview"
                  srcDoc={message.body_html}
                  sandbox=""
                  className="h-[26rem] w-full border-0"
                />
              </div>
            ) : (
              <pre className="whitespace-pre-wrap border border-line bg-sunken p-4 text-sm">
                {message.body_text}
              </pre>
            )}
          </>
        )}
      </Modal>
    </>
  )
}

/* ── Audit ───────────────────────────────────────────────────────────────── */
function Audit() {
  const { data, isLoading } = useQuery({
    queryKey: ['admin-audit'],
    queryFn: () => get<any[]>('/admin/audit', { limit: 100 }),
  })

  return (
    <>
      <PageHeading title="Audit log" />
      <p className="mb-4 text-sm text-muted">
        Every change an administrator has made, appended and never edited.
      </p>
      <DataTable
        loading={isLoading}
        rows={data}
        columns={[
          { key: 'at', label: 'When',
            render: (row: any) => (
              <span className="text-xs text-faint">{formatDateTime(row.at)}</span>
            ) },
          { key: 'actor', label: 'Who',
            render: (row: any) => <span className="text-xs">{row.actor}</span> },
          { key: 'action', label: 'Action',
            render: (row: any) => (
              <span className="font-mono text-xs">{row.action}</span>
            ) },
          { key: 'summary', label: 'Summary',
            render: (row: any) => <span className="text-sm">{row.summary}</span> },
        ]}
      />
    </>
  )
}

/* ── Settings ────────────────────────────────────────────────────────────── */
function Settings() {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['admin-settings'],
    queryFn: () => get<any[]>('/admin/settings'),
  })

  const save = useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) =>
      put<ApiMessage>(`/admin/settings/${key}`, { value }),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-settings'] })
    },
    onError: (error) =>
      toast.error(error instanceof ApiError ? error.message : 'Could not save'),
  })

  if (isLoading) return <Skeleton className="h-96 w-full" />

  const groups = (data ?? []).reduce<Record<string, any[]>>((acc, setting) => {
    ;(acc[setting.group] ??= []).push(setting)
    return acc
  }, {})

  return (
    <>
      <PageHeading title="Settings" />
      <div className="max-w-2xl space-y-8">
        {Object.entries(groups).map(([group, settings]) => (
          <section key={group}>
            <h2 className="wc-eyebrow mb-3">{group}</h2>
            <div className="wc-panel divide-y divide-[var(--wc-border-subtle)]">
              {settings.map((setting) => (
                <div key={setting.key} className="flex items-center gap-4 p-4">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm">{setting.label}</p>
                    {setting.description && (
                      <p className="text-xs text-faint">{setting.description}</p>
                    )}
                    {setting.key === 'tax_mode' && (
                      <p className="mt-1 text-xs text-[var(--wc-warning)]">
                        Changes how every catalogue price is read. Inclusive means
                        the shelf price already contains GST; exclusive adds 18% on
                        top at checkout.
                      </p>
                    )}
                  </div>
                  <div className="w-48 shrink-0">
                    {setting.value_type === 'bool' ? (
                      <input
                        type="checkbox"
                        defaultChecked={Boolean(setting.value)}
                        onChange={(e) =>
                          save.mutate({ key: setting.key, value: e.target.checked })
                        }
                      />
                    ) : setting.key === 'tax_mode' ? (
                      <Select
                        defaultValue={String(setting.value ?? '')}
                        onChange={(e) => {
                          // Switching this does not just relabel the invoice. It
                          // changes how every catalogue price is read, so the
                          // same Rs 14,460 either contains GST or has 18% added
                          // on top. Nobody should be able to do that by accident.
                          const next = e.target.value
                          const current = String(setting.value ?? '')
                          if (next === current) return
                          const warning =
                            next === 'exclusive'
                              ? [
                                  'Switching to exclusive treats every catalogue price as PRE-tax.',
                                  '18% GST will be ADDED at checkout, so every product effectively',
                                  'becomes 18% more expensive unless you also reprice the catalogue.',
                                  '',
                                  'Continue?',
                                ].join(' ')
                              : [
                                  'Switching to inclusive treats every catalogue price as already',
                                  'containing GST, so what customers pay will drop by the tax',
                                  'component.',
                                  '',
                                  'Continue?',
                                ].join(' ')
                          if (window.confirm(warning)) {
                            save.mutate({ key: setting.key, value: next })
                          } else {
                            e.target.value = current
                          }
                        }}
                        className="py-1.5 text-sm"
                      >
                        <option value="inclusive">Inclusive (prices include GST)</option>
                        <option value="exclusive">Exclusive (GST added at checkout)</option>
                      </Select>
                    ) : (
                      <Input
                        defaultValue={String(setting.value ?? '')}
                        onBlur={(e) => {
                          if (e.target.value !== String(setting.value ?? '')) {
                            save.mutate({ key: setting.key, value: e.target.value })
                          }
                        }}
                        className="py-1.5 text-sm"
                      />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  )
}

export default function AdminApp() {
  return (
    <Shell>
      <Routes>
        <Route index element={<Dashboard />} />
        <Route path="orders" element={<Orders />} />
        <Route path="products" element={<Products />} />
        <Route path="inventory" element={<Inventory />} />
        <Route path="customers" element={<Customers />} />
        <Route path="returns" element={<AdminReturns />} />
        <Route path="reviews" element={<Reviews />} />
        <Route path="tickets" element={<AdminTickets />} />
        <Route path="coupons" element={<AdminCoupons />} />
        <Route path="gift-cards" element={<AdminGiftCards />} />
        <Route path="blog" element={<AdminBlog />} />
        <Route path="pages" element={<AdminPages />} />
        <Route path="import" element={<AdminImport />} />
        <Route path="notifications" element={<Notifications />} />
        <Route path="audit" element={<Audit />} />
        <Route path="settings" element={<Settings />} />
      </Routes>
    </Shell>
  )
}
