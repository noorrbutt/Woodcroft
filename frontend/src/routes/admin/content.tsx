/** Admin: CMS, coupons, gift cards, returns, tickets, bulk import. */

import { useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { FileUp, Plus } from 'lucide-react'

import { ApiError, api, del, download, get, post, put } from '@/lib/api'
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
import type { ApiMessage } from '@/lib/types'

export function PageHeading({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <h1 className="font-display text-2xl">{title}</h1>
      {action}
    </div>
  )
}

function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="wc-scroll-x wc-panel">
      <table className="w-full min-w-[44rem] border-collapse text-sm">
        <thead>
          <tr className="border-b border-line">
            {head.map((label) => (
              <th key={label} className="px-4 py-3 text-left wc-eyebrow">{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

const ROW = 'border-b border-line last:border-0 hover:bg-sunken'

/* ── Blog ────────────────────────────────────────────────────────────────── */
const EMPTY_POST = {
  title: '', slug: '', excerpt: '', body_html: '', category: 'Craft',
  author_name: 'Woodcroft Workshop', is_published: false,
  reading_minutes: 5, meta_title: '', meta_description: '',
}

export function AdminBlog() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ ...EMPTY_POST })

  const { data: posts, isLoading } = useQuery({
    queryKey: ['admin-blog'],
    queryFn: () => get<any[]>('/admin/blog'),
  })

  const open = async (id: string) => {
    const post = await get<any>(`/admin/blog/${id}`)
    setForm({ ...EMPTY_POST, ...post })
    setEditing(id)
  }

  const close = () => {
    setEditing(null)
    setCreating(false)
    setForm({ ...EMPTY_POST })
  }

  const save = useMutation({
    mutationFn: () =>
      editing
        ? put<ApiMessage>(`/admin/blog/${editing}`, form)
        : post<ApiMessage>('/admin/blog', form),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-blog'] })
      close()
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not save'),
  })

  const remove = useMutation({
    mutationFn: (id: string) => del<ApiMessage>(`/admin/blog/${id}`),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-blog'] })
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not delete'),
  })

  const bind = (key: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setForm((c) => ({ ...c, [key]: e.target.value }))

  return (
    <>
      <PageHeading
        title="Journal"
        action={
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus size={13} strokeWidth={2} /> New article
          </Button>
        }
      />

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : !posts?.length ? (
        <EmptyState title="No articles yet" />
      ) : (
        <Table head={['Title', 'Category', 'Status', 'Published', 'Views', '']}>
          {posts.map((post) => (
            <tr key={post.id} className={ROW}>
              <td className="px-4 py-3">
                <p className="font-medium">{post.title}</p>
                <p className="text-xs text-faint">/journal/{post.slug}</p>
              </td>
              <td className="px-4 py-3 text-xs text-muted">{post.category ?? '—'}</td>
              <td className="px-4 py-3">
                <Badge tone={post.is_published ? 'success' : 'neutral'}>
                  {post.is_published ? 'Published' : 'Draft'}
                </Badge>
              </td>
              <td className="px-4 py-3 text-xs text-faint">
                {post.published_at ? formatDate(post.published_at) : '—'}
              </td>
              <td className="px-4 py-3 text-xs tabular-nums">{post.view_count}</td>
              <td className="px-4 py-3 text-right">
                <button onClick={() => open(post.id)}
                        className="mr-3 text-xs text-muted hover:text-ink">Edit</button>
                <button onClick={() => { if (window.confirm('Delete this article? This cannot be undone.')) remove.mutate(post.id) }}
                        className="text-xs text-muted hover:text-[var(--wc-danger)]">
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Modal
        open={creating || editing !== null}
        onClose={close}
        title={editing ? 'Edit article' : 'New article'}
        size="lg"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={close}>Cancel</Button>
            <Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button>
          </div>
        }
      >
        <form className="space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate() }}>
          <Field label="Title" id="title" required>
            <Input id="title" required value={form.title} onChange={bind('title')} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="URL slug" id="slug" hint="Leave blank to generate from the title">
              <Input id="slug" value={form.slug ?? ''} onChange={bind('slug')} />
            </Field>
            <Field label="Category" id="category">
              <Select id="category" value={form.category ?? ''} onChange={bind('category')}>
                {['Craft', 'Care', 'Styling', 'Sustainability'].map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Excerpt" id="excerpt" hint="Shown on the journal index">
            <Textarea id="excerpt" rows={2} value={form.excerpt ?? ''} onChange={bind('excerpt')} />
          </Field>
          <Field label="Body" id="body" hint="HTML. Use <p>, <h2>, <ul>, <blockquote>.">
            <Textarea id="body" rows={12} className="font-mono text-xs"
                      value={form.body_html ?? ''} onChange={bind('body_html')} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Author" id="author">
              <Input id="author" value={form.author_name ?? ''} onChange={bind('author_name')} />
            </Field>
            <Field label="Reading minutes" id="reading">
              <Input id="reading" type="number" value={form.reading_minutes ?? 5}
                     onChange={(e) => setForm((c) => ({ ...c, reading_minutes: Number(e.target.value) }))} />
            </Field>
          </div>
          <Checkbox label="Published" checked={form.is_published}
                    onChange={(e) => setForm((c) => ({ ...c, is_published: e.target.checked }))} />
        </form>
      </Modal>
    </>
  )
}

/* ── Static pages ────────────────────────────────────────────────────────── */
const EMPTY_PAGE = {
  title: '', slug: '', body_html: '', is_published: true,
  show_in_footer: true, sort_order: 0, meta_title: '', meta_description: '',
}

export function AdminPages() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<any>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ ...EMPTY_PAGE })

  const { data: pages, isLoading } = useQuery({
    queryKey: ['admin-pages'],
    queryFn: () => get<any[]>('/admin/pages'),
  })

  const open = async (row: any) => {
    const page = await get<any>(`/admin/pages/${row.id}`)
    setForm({ ...EMPTY_PAGE, ...page })
    setEditing(page)
  }
  const close = () => { setEditing(null); setCreating(false); setForm({ ...EMPTY_PAGE }) }

  const save = useMutation({
    mutationFn: () =>
      editing
        ? put<ApiMessage>(`/admin/pages/${editing.id}`, form)
        : post<ApiMessage>('/admin/pages', form),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-pages'] })
      close()
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not save'),
  })

  const remove = useMutation({
    mutationFn: (id: string) => del<ApiMessage>(`/admin/pages/${id}`),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-pages'] })
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not delete'),
  })

  const bind = (key: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm((c) => ({ ...c, [key]: e.target.value }))

  return (
    <>
      <PageHeading
        title="Pages"
        action={
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus size={13} strokeWidth={2} /> New page
          </Button>
        }
      />

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <Table head={['Title', 'URL', 'Status', 'Footer', '']}>
          {pages?.map((page) => (
            <tr key={page.id} className={ROW}>
              <td className="px-4 py-3">
                <span className="font-medium">{page.title}</span>
                {page.is_system && (
                  <Badge tone="info" className="ml-2">Required</Badge>
                )}
              </td>
              <td className="px-4 py-3 font-mono text-xs text-faint">/page/{page.slug}</td>
              <td className="px-4 py-3">
                <Badge tone={page.is_published ? 'success' : 'neutral'}>
                  {page.is_published ? 'Published' : 'Hidden'}
                </Badge>
              </td>
              <td className="px-4 py-3 text-xs text-muted">
                {page.show_in_footer ? 'Yes' : 'No'}
              </td>
              <td className="px-4 py-3 text-right">
                <button onClick={() => open(page)}
                        className="mr-3 text-xs text-muted hover:text-ink">Edit</button>
                {!page.is_system && (
                  <button onClick={() => remove.mutate(page.id)}
                          className="text-xs text-muted hover:text-[var(--wc-danger)]">
                    Delete
                  </button>
                )}
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Modal
        open={creating || editing !== null}
        onClose={close}
        title={editing ? `Edit ${editing.title}` : 'New page'}
        size="lg"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={close}>Cancel</Button>
            <Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button>
          </div>
        }
      >
        <form className="space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate() }}>
          <Field label="Title" id="ptitle" required>
            <Input id="ptitle" required value={form.title} onChange={bind('title')} />
          </Field>
          <Field label="URL slug" id="pslug"
                 hint={editing?.is_system ? 'Required pages keep their URL' : 'Leave blank to generate'}>
            <Input id="pslug" value={form.slug ?? ''} onChange={bind('slug')}
                   disabled={editing?.is_system} />
          </Field>
          <Field label="Body" id="pbody" hint="HTML">
            <Textarea id="pbody" rows={14} className="font-mono text-xs"
                      value={form.body_html ?? ''} onChange={bind('body_html')} />
          </Field>
          <div className="flex gap-6">
            <Checkbox label="Published" checked={form.is_published}
                      onChange={(e) => setForm((c) => ({ ...c, is_published: e.target.checked }))} />
            <Checkbox label="Show in footer" checked={form.show_in_footer}
                      onChange={(e) => setForm((c) => ({ ...c, show_in_footer: e.target.checked }))} />
          </div>
        </form>
      </Modal>
    </>
  )
}

/* ── Coupons ─────────────────────────────────────────────────────────────── */
const EMPTY_COUPON = {
  code: '', description: '', kind: 'percentage', value_bp: 1000,
  value_paisa: null as number | null, max_discount_paisa: null as number | null,
  min_order_paisa: 0, usage_limit: null as number | null,
  usage_limit_per_user: null as number | null,
  first_order_only: false, is_active: true,
  starts_at: null as string | null, ends_at: null as string | null,
}

export function AdminCoupons() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<any>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState<any>({ ...EMPTY_COUPON })

  const { data: coupons, isLoading } = useQuery({
    queryKey: ['admin-coupons'],
    queryFn: () => get<any[]>('/admin/coupons'),
  })

  const close = () => { setEditing(null); setCreating(false); setForm({ ...EMPTY_COUPON }) }

  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...form,
        code: form.code.toUpperCase(),
        // The form works in rupees and percent; the API works in paisa and
        // basis points. Convert at this boundary and nowhere else.
        value_bp: form.kind === 'percentage' ? Number(form.value_bp) : null,
        value_paisa: form.kind === 'fixed_amount' ? Number(form.value_paisa) : null,
        min_order_paisa: Number(form.min_order_paisa) || 0,
        usage_limit: form.usage_limit ? Number(form.usage_limit) : null,
        max_discount_paisa: form.max_discount_paisa ? Number(form.max_discount_paisa) : null,
        starts_at: form.starts_at || null,
        ends_at: form.ends_at || null,
      }
      return editing
        ? put<ApiMessage>(`/admin/coupons/${editing.id}`, body)
        : post<ApiMessage>('/admin/coupons', body)
    },
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-coupons'] })
      close()
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not save'),
  })

  const remove = useMutation({
    mutationFn: (id: string) => del<ApiMessage>(`/admin/coupons/${id}`),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-coupons'] })
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not remove'),
  })

  const openEdit = (coupon: any) => {
    setForm({
      ...EMPTY_COUPON, ...coupon,
      starts_at: coupon.starts_at ? coupon.starts_at.slice(0, 16) : '',
      ends_at: coupon.ends_at ? coupon.ends_at.slice(0, 16) : '',
    })
    setEditing(coupon)
  }

  const tone = (state: string) =>
    state === 'live' ? 'success'
    : state === 'scheduled' ? 'info'
    : state === 'exhausted' ? 'warning'
    : 'neutral'

  return (
    <>
      <PageHeading
        title="Coupons"
        action={
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus size={13} strokeWidth={2} /> New coupon
          </Button>
        }
      />

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <Table head={['Code', 'Discount', 'Minimum', 'Used', 'Saved', 'Window', 'State', '']}>
          {coupons?.map((coupon) => (
            <tr key={coupon.id} className={ROW}>
              <td className="px-4 py-3">
                <p className="font-mono text-sm">{coupon.code}</p>
                {coupon.description && (
                  <p className="text-xs text-faint">{coupon.description}</p>
                )}
              </td>
              <td className="px-4 py-3 tabular-nums">{coupon.value_display}</td>
              <td className="px-4 py-3 text-xs tabular-nums text-muted">
                {coupon.min_order_paisa ? coupon.min_order_display : '—'}
              </td>
              <td className="px-4 py-3 text-xs tabular-nums">
                {coupon.used_count}{coupon.usage_limit ? ` / ${coupon.usage_limit}` : ''}
              </td>
              <td className="px-4 py-3 text-xs tabular-nums text-muted">{coupon.total_saved}</td>
              <td className="px-4 py-3 text-xs text-faint">
                {coupon.ends_at ? `until ${formatDate(coupon.ends_at)}` : 'no end date'}
              </td>
              <td className="px-4 py-3"><Badge tone={tone(coupon.state)}>{coupon.state}</Badge></td>
              <td className="px-4 py-3 text-right">
                <button onClick={() => openEdit(coupon)}
                        className="mr-3 text-xs text-muted hover:text-ink">Edit</button>
                <button onClick={() => { if (window.confirm('Remove this coupon?')) remove.mutate(coupon.id) }}
                        className="text-xs text-muted hover:text-[var(--wc-danger)]">
                  {coupon.used_count ? 'Disable' : 'Delete'}
                </button>
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Modal
        open={creating || editing !== null}
        onClose={close}
        title={editing ? `Edit ${editing.code}` : 'New coupon'}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={close}>Cancel</Button>
            <Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button>
          </div>
        }
      >
        <form className="space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate() }}>
          <Field label="Code" id="code" required hint="Customers type this at checkout">
            <Input id="code" required className="font-mono uppercase" value={form.code}
                   disabled={Boolean(editing)}
                   onChange={(e) => setForm((c: any) => ({ ...c, code: e.target.value.toUpperCase() }))} />
          </Field>
          <Field label="Description" id="cdesc">
            <Input id="cdesc" value={form.description ?? ''}
                   onChange={(e) => setForm((c: any) => ({ ...c, description: e.target.value }))} />
          </Field>
          <Field label="Type" id="kind">
            <Select id="kind" value={form.kind}
                    onChange={(e) => setForm((c: any) => ({ ...c, kind: e.target.value }))}>
              <option value="percentage">Percentage off</option>
              <option value="fixed_amount">Fixed amount off</option>
              <option value="free_shipping">Free delivery</option>
            </Select>
          </Field>

          {form.kind === 'percentage' && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Percent off" id="pct" hint="In basis points: 1000 is 10%">
                <Input id="pct" type="number" value={form.value_bp ?? ''}
                       onChange={(e) => setForm((c: any) => ({ ...c, value_bp: e.target.value }))} />
              </Field>
              <Field label="Cap (paisa)" id="cap" hint="Optional maximum discount">
                <Input id="cap" type="number" value={form.max_discount_paisa ?? ''}
                       onChange={(e) => setForm((c: any) => ({ ...c, max_discount_paisa: e.target.value }))} />
              </Field>
            </div>
          )}
          {form.kind === 'fixed_amount' && (
            <Field label="Amount off (paisa)" id="amt" hint="200000 is Rs 2,000">
              <Input id="amt" type="number" value={form.value_paisa ?? ''}
                     onChange={(e) => setForm((c: any) => ({ ...c, value_paisa: e.target.value }))} />
            </Field>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Minimum order (paisa)" id="min">
              <Input id="min" type="number" value={form.min_order_paisa ?? 0}
                     onChange={(e) => setForm((c: any) => ({ ...c, min_order_paisa: e.target.value }))} />
            </Field>
            <Field label="Usage limit" id="limit" hint="Blank for unlimited">
              <Input id="limit" type="number" value={form.usage_limit ?? ''}
                     onChange={(e) => setForm((c: any) => ({ ...c, usage_limit: e.target.value }))} />
            </Field>
            <Field label="Starts" id="starts">
              <Input id="starts" type="datetime-local" value={form.starts_at ?? ''}
                     onChange={(e) => setForm((c: any) => ({ ...c, starts_at: e.target.value }))} />
            </Field>
            <Field label="Ends" id="ends">
              <Input id="ends" type="datetime-local" value={form.ends_at ?? ''}
                     onChange={(e) => setForm((c: any) => ({ ...c, ends_at: e.target.value }))} />
            </Field>
          </div>

          <div className="flex gap-6">
            <Checkbox label="Active" checked={form.is_active}
                      onChange={(e) => setForm((c: any) => ({ ...c, is_active: e.target.checked }))} />
            <Checkbox label="First order only" checked={form.first_order_only}
                      onChange={(e) => setForm((c: any) => ({ ...c, first_order_only: e.target.checked }))} />
          </div>
        </form>
      </Modal>
    </>
  )
}

/* ── Gift cards ──────────────────────────────────────────────────────────── */
export function AdminGiftCards() {
  const queryClient = useQueryClient()
  const [issuing, setIssuing] = useState(false)
  const [form, setForm] = useState({
    amount_paisa: 500_000, quantity: 1,
    recipient_email: '', recipient_name: '', message: '',
  })

  const { data: cards, isLoading } = useQuery({
    queryKey: ['admin-gift-cards'],
    queryFn: () => get<any[]>('/admin/gift-cards'),
  })

  const issue = useMutation({
    mutationFn: () =>
      post<ApiMessage>('/admin/gift-cards', {
        ...form,
        amount_paisa: Number(form.amount_paisa),
        quantity: Number(form.quantity),
        recipient_email: form.recipient_email || null,
        recipient_name: form.recipient_name || null,
        message: form.message || null,
      }),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-gift-cards'] })
      setIssuing(false)
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not issue'),
  })

  const cancel = useMutation({
    mutationFn: (id: string) => post<ApiMessage>(`/admin/gift-cards/${id}/cancel`),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-gift-cards'] })
    },
  })

  return (
    <>
      <PageHeading
        title="Gift cards"
        action={
          <Button size="sm" onClick={() => setIssuing(true)}>
            <Plus size={13} strokeWidth={2} /> Issue cards
          </Button>
        }
      />

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <Table head={['Code', 'Issued', 'Spent', 'Balance', 'Recipient', 'Status', '']}>
          {cards?.map((card) => (
            <tr key={card.id} className={ROW}>
              <td className="px-4 py-3 font-mono text-xs">{card.code}</td>
              <td className="px-4 py-3 tabular-nums">{card.initial}</td>
              <td className="px-4 py-3 tabular-nums text-muted">{card.spent}</td>
              <td className="px-4 py-3 tabular-nums font-medium">{card.balance}</td>
              <td className="px-4 py-3 text-xs text-muted">
                {card.recipient_email ?? '—'}
              </td>
              <td className="px-4 py-3">
                <Badge tone={
                  card.status === 'active' ? 'success'
                  : card.status === 'cancelled' ? 'danger' : 'neutral'
                }>
                  {card.status}
                </Badge>
              </td>
              <td className="px-4 py-3 text-right">
                {card.status === 'active' && (
                  <button onClick={() => { if (window.confirm('Cancel this gift card? The remaining balance will be voided.')) cancel.mutate(card.id) }}
                          className="text-xs text-muted hover:text-[var(--wc-danger)]">
                    Cancel
                  </button>
                )}
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Modal
        open={issuing}
        onClose={() => setIssuing(false)}
        title="Issue gift cards"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setIssuing(false)}>Cancel</Button>
            <Button loading={issue.isPending} onClick={() => issue.mutate()}>Issue</Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Value (paisa)" id="amount" hint="500000 is Rs 5,000">
              <Input id="amount" type="number" value={form.amount_paisa}
                     onChange={(e) => setForm((c) => ({ ...c, amount_paisa: Number(e.target.value) }))} />
            </Field>
            <Field label="How many" id="qty">
              <Input id="qty" type="number" min={1} max={50} value={form.quantity}
                     onChange={(e) => setForm((c) => ({ ...c, quantity: Number(e.target.value) }))} />
            </Field>
          </div>
          <Field label="Recipient email" id="remail"
                 hint="Optional. If set, the code is emailed to them.">
            <Input id="remail" type="email" value={form.recipient_email}
                   onChange={(e) => setForm((c) => ({ ...c, recipient_email: e.target.value }))} />
          </Field>
          <Field label="Recipient name" id="rname">
            <Input id="rname" value={form.recipient_name}
                   onChange={(e) => setForm((c) => ({ ...c, recipient_name: e.target.value }))} />
          </Field>
          <Field label="Message" id="rmsg">
            <Textarea id="rmsg" rows={2} value={form.message}
                      onChange={(e) => setForm((c) => ({ ...c, message: e.target.value }))} />
          </Field>
        </div>
      </Modal>
    </>
  )
}

/* ── Returns ─────────────────────────────────────────────────────────────── */
export function AdminReturns() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState('')
  const [deciding, setDeciding] = useState<any>(null)
  const [decision, setDecision] = useState({
    status: 'approved', admin_note: '', restock: true, refund: false,
  })

  const { data: returns, isLoading } = useQuery({
    queryKey: ['admin-returns', status],
    queryFn: () => get<any[]>('/admin/returns', { status }),
  })

  const decide = useMutation({
    mutationFn: () => post<ApiMessage>(`/admin/returns/${deciding.id}/decide`, decision),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-returns'] })
      setDeciding(null)
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not update'),
  })

  return (
    <>
      <PageHeading
        title="Returns"
        action={
          <Select value={status} onChange={(e) => setStatus(e.target.value)}
                  className="w-auto py-1.5 text-xs">
            <option value="">All</option>
            {['requested', 'approved', 'in_transit', 'received', 'refunded', 'rejected']
              .map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
          </Select>
        }
      />

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : !returns?.length ? (
        <EmptyState title="No returns" description="Nothing to process right now." />
      ) : (
        <ul className="space-y-3">
          {returns.map((request) => (
            <li key={request.id} className="wc-panel p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs">{request.return_number}</span>
                    <span className="text-xs text-faint">for {request.order_number}</span>
                    <Badge tone={
                      request.status === 'refunded' ? 'success'
                      : request.status === 'rejected' ? 'danger'
                      : request.status === 'requested' ? 'warning' : 'neutral'
                    }>
                      {request.status.replace('_', ' ')}
                    </Badge>
                  </div>
                  <p className="text-sm">
                    {request.customer} · <span className="text-muted">{request.reason}</span>
                  </p>
                  {request.customer_note && (
                    <p className="mt-1 text-sm italic text-muted">“{request.customer_note}”</p>
                  )}
                  <ul className="mt-2 text-xs text-faint">
                    {request.items.map((item: any, i: number) => (
                      <li key={i}>{item.quantity}× {item.name}</li>
                    ))}
                  </ul>
                  <p className="mt-2 text-xs">
                    Refundable: <span className="tabular-nums">{request.refundable}</span>
                    <span className="text-faint"> · {relativeTime(request.created_at)}</span>
                  </p>
                </div>
                <Button size="sm" variant="outline" onClick={() => {
                  setDeciding(request)
                  setDecision({
                    status: request.status === 'requested' ? 'approved' : 'received',
                    admin_note: request.admin_note ?? '', restock: true, refund: false,
                  })
                }}>
                  Process
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal
        open={deciding !== null}
        onClose={() => setDeciding(null)}
        title={`Process ${deciding?.return_number ?? ''}`}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDeciding(null)}>Cancel</Button>
            <Button loading={decide.isPending} onClick={() => decide.mutate()}>Apply</Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Field label="Decision" id="rstatus">
            <Select id="rstatus" value={decision.status}
                    onChange={(e) => setDecision((c) => ({ ...c, status: e.target.value }))}>
              <option value="approved">Approve the return</option>
              <option value="rejected">Reject</option>
              <option value="in_transit">Marked as sent back</option>
              <option value="received">Received at the workshop</option>
              <option value="refunded">Refunded</option>
            </Select>
          </Field>

          {decision.status === 'received' && (
            <>
              <Checkbox
                label="Put the items back into stock"
                checked={decision.restock}
                onChange={(e) => setDecision((c) => ({ ...c, restock: e.target.checked }))}
              />
              <p className="text-xs text-faint">
                Stock only comes back once the goods physically arrive, and only
                if they are resellable. Damaged returns should be left unticked.
              </p>
            </>
          )}

          {decision.status === 'refunded' && (
            <>
              <Checkbox
                label={`Issue a refund of ${deciding?.refundable ?? ''} as store credit`}
                checked={decision.refund}
                onChange={(e) => setDecision((c) => ({ ...c, refund: e.target.checked }))}
              />
              <p className="text-xs text-faint">
                COD orders are refunded out of band, so store credit is the
                honest default here.
              </p>
            </>
          )}

          <Field label="Note to the customer" id="rnote">
            <Textarea id="rnote" rows={3} value={decision.admin_note}
                      onChange={(e) => setDecision((c) => ({ ...c, admin_note: e.target.value }))} />
          </Field>
        </div>
      </Modal>
    </>
  )
}

/* ── Support tickets ─────────────────────────────────────────────────────── */
export function AdminTickets() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)
  const [reply, setReply] = useState({ body: '', is_internal: false, status: '' })

  const { data: tickets, isLoading } = useQuery({
    queryKey: ['admin-tickets', status],
    queryFn: () => get<any[]>('/admin/tickets', { status }),
  })

  const { data: ticket } = useQuery({
    queryKey: ['admin-ticket', openId],
    queryFn: () => get<any>(`/admin/tickets/${openId}`),
    enabled: Boolean(openId),
  })

  const send = useMutation({
    mutationFn: () =>
      post<ApiMessage>(`/admin/tickets/${openId}/reply`, {
        ...reply,
        status: reply.status || undefined,
      }),
    onSuccess: (result) => {
      toast.success(result.message)
      queryClient.invalidateQueries({ queryKey: ['admin-ticket', openId] })
      queryClient.invalidateQueries({ queryKey: ['admin-tickets'] })
      setReply({ body: '', is_internal: false, status: '' })
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Could not send'),
  })

  return (
    <>
      <PageHeading
        title="Support"
        action={
          <Select value={status} onChange={(e) => setStatus(e.target.value)}
                  className="w-auto py-1.5 text-xs">
            <option value="">All</option>
            <option value="open">Open</option>
            <option value="pending_customer">Awaiting customer</option>
            <option value="resolved">Resolved</option>
            <option value="closed">Closed</option>
          </Select>
        }
      />

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : !tickets?.length ? (
        <EmptyState title="No tickets" />
      ) : (
        <Table head={['Ticket', 'Subject', 'Customer', 'Priority', 'Status', 'Opened', '']}>
          {tickets.map((row) => (
            <tr key={row.id} className={ROW}>
              <td className="px-4 py-3 font-mono text-xs">{row.ticket_number}</td>
              <td className="px-4 py-3">
                <p className="text-sm">{row.subject}</p>
                <p className="truncate text-xs text-faint">{row.last_message}</p>
              </td>
              <td className="px-4 py-3 text-xs">
                <p>{row.contact_name}</p>
                <p className="text-faint">{row.contact_email}</p>
              </td>
              <td className="px-4 py-3">
                <Badge tone={row.priority === 'high' || row.priority === 'urgent' ? 'warning' : 'neutral'}>
                  {row.priority}
                </Badge>
              </td>
              <td className="px-4 py-3">
                <Badge tone={
                  row.status === 'open' ? 'warning'
                  : row.status === 'resolved' ? 'success' : 'neutral'
                }>
                  {row.status.replace('_', ' ')}
                </Badge>
              </td>
              <td className="px-4 py-3 text-xs text-faint">{relativeTime(row.created_at)}</td>
              <td className="px-4 py-3 text-right">
                <button onClick={() => setOpenId(row.id)}
                        className="text-xs text-muted hover:text-ink">Open</button>
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Modal
        open={openId !== null}
        onClose={() => setOpenId(null)}
        title={ticket?.subject ?? 'Ticket'}
        size="lg"
      >
        {ticket && (
          <div className="space-y-5">
            <p className="text-xs text-faint">
              {ticket.ticket_number} · {ticket.contact_name} ({ticket.contact_email})
              {ticket.order_number && <> · order {ticket.order_number}</>}
            </p>

            <ul className="space-y-3">
              {ticket.messages.map((message: any) => (
                <li
                  key={message.id}
                  className={cn(
                    'border p-3 text-sm',
                    message.is_internal
                      ? 'border-dashed border-[var(--wc-warning)] bg-warning-bg'
                      : message.is_staff
                        ? 'border-line bg-sunken'
                        : 'border-line',
                  )}
                >
                  <div className="mb-1 flex items-center gap-2 text-xs text-faint">
                    <span>{message.is_staff ? 'Woodcroft' : ticket.contact_name}</span>
                    {message.is_internal && <Badge tone="warning">Internal note</Badge>}
                    <span className="ml-auto">{formatDateTime(message.at)}</span>
                  </div>
                  <p className="whitespace-pre-line">{message.body}</p>
                </li>
              ))}
            </ul>

            <div className="space-y-3 border-t border-line pt-4">
              <Field label="Reply" id="reply">
                <Textarea id="reply" rows={4} value={reply.body}
                          onChange={(e) => setReply((c) => ({ ...c, body: e.target.value }))} />
              </Field>
              <div className="flex flex-wrap items-center gap-4">
                <Checkbox
                  label="Internal note (not emailed)"
                  checked={reply.is_internal}
                  onChange={(e) => setReply((c) => ({ ...c, is_internal: e.target.checked }))}
                />
                <Select value={reply.status}
                        onChange={(e) => setReply((c) => ({ ...c, status: e.target.value }))}
                        className="w-auto py-1.5 text-xs">
                  <option value="">Keep status</option>
                  <option value="open">Mark open</option>
                  <option value="pending_customer">Awaiting customer</option>
                  <option value="resolved">Mark resolved</option>
                  <option value="closed">Close</option>
                </Select>
                <Button size="sm" className="ml-auto" loading={send.isPending}
                        disabled={reply.body.trim().length < 2}
                        onClick={() => send.mutate()}>
                  {reply.is_internal ? 'Add note' : 'Send reply'}
                </Button>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}

/* ── Bulk import ─────────────────────────────────────────────────────────── */
export function AdminImport() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [result, setResult] = useState<any>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)

  const run = useMutation({
    mutationFn: async ({ file, dryRun }: { file: File; dryRun: boolean }) => {
      const body = new FormData()
      body.append('file', file)
      return api<any>(`/admin/products/import?dry_run=${dryRun}`, {
        method: 'POST',
        body,
      })
    },
    onSuccess: (data) => {
      setResult(data)
      if (data.dry_run) toast.info(data.message)
      else toast.success(data.message)
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : 'Import failed'),
  })

  return (
    <>
      <PageHeading
        title="Bulk import"
        action={
          <Button
            variant="outline"
            size="sm"
            onClick={() => download('/admin/products/export', 'products.csv')}
          >
            Export current catalogue
          </Button>
        }
      />

      <div className="wc-panel max-w-2xl p-5">
        <p className="text-sm text-muted">
          Update prices, stock and status in bulk from a CSV, matched on SKU.
          Export the catalogue first to get the right columns.
        </p>
        <p className="mt-3 text-xs text-faint">
          It always runs as a dry run first. A bulk price change applied to the
          wrong file is expensive and hard to undo, so applying it is a separate
          deliberate step.
        </p>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              const file = e.target.files?.[0] ?? null
              setPendingFile(file)
              setResult(null)
              if (file) run.mutate({ file, dryRun: true })
            }}
            className="hidden"
          />
          <Button variant="outline" onClick={() => fileRef.current?.click()}>
            <FileUp size={13} strokeWidth={1.5} /> Choose a CSV
          </Button>
          {pendingFile && (
            <span className="text-xs text-muted">{pendingFile.name}</span>
          )}
        </div>

        {run.isPending && <Skeleton className="mt-5 h-24 w-full" />}

        {result && (
          <div className="mt-6 space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge tone={result.updated_count ? 'info' : 'neutral'}>
                {result.updated_count} to change
              </Badge>
              <Badge tone="neutral">{result.unchanged} unchanged</Badge>
              {result.error_count > 0 && (
                <Badge tone="danger">{result.error_count} problems</Badge>
              )}
            </div>

            {result.errors?.length > 0 && (
              <div className="border border-[var(--wc-danger)] bg-danger-bg p-3">
                <p className="mb-2 text-xs font-medium">Rows that will be skipped</p>
                <ul className="space-y-1 text-xs">
                  {result.errors.slice(0, 10).map((error: any, i: number) => (
                    <li key={i}>
                      Row {error.row} <span className="font-mono">{error.sku}</span>: {error.error}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {result.updated?.length > 0 && (
              <div className="wc-scroll-x border border-line">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="px-3 py-2 text-left wc-eyebrow">SKU</th>
                      <th className="px-3 py-2 text-left wc-eyebrow">Product</th>
                      <th className="px-3 py-2 text-left wc-eyebrow">Changes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.updated.slice(0, 25).map((row: any, i: number) => (
                      <tr key={i} className="border-b border-line last:border-0">
                        <td className="px-3 py-2 font-mono">{row.sku}</td>
                        <td className="px-3 py-2">{row.product}</td>
                        <td className="px-3 py-2">
                          {Object.entries(row.changes).map(([field, change]: any) => (
                            <span key={field} className="mr-3">
                              {field}: <span className="text-faint">{change.from}</span> →{' '}
                              <strong>{change.to}</strong>
                            </span>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {result.dry_run && result.updated_count > 0 && (
              <Button
                loading={run.isPending}
                onClick={() => pendingFile && run.mutate({ file: pendingFile, dryRun: false })}
              >
                Apply {result.updated_count} changes
              </Button>
            )}
          </div>
        )}
      </div>
    </>
  )
}
