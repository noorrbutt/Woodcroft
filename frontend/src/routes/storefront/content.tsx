/** Journal, static pages, FAQ and contact. */

import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { ApiError, get, post } from '@/lib/api'
import { formatDate } from '@/lib/format'
import {
  Accordion,
  Breadcrumbs,
  Button,
  EmptyState,
  Field,
  Input,
  Skeleton,
  Textarea,
} from '@/components/ui'
import type { ApiMessage } from '@/lib/types'

interface Post {
  id: string
  title: string
  slug: string
  excerpt: string | null
  category: string | null
  author_name: string
  cover_image_url: string | null
  published_at: string | null
  reading_minutes: number | null
  body_html?: string
}

interface Page {
  title: string
  slug: string
  body_html: string
  meta_description: string | null
}

interface Faq {
  id: string
  question: string
  answer_html: string
  category: string
}

export function JournalPage() {
  const { data: posts, isLoading } = useQuery({
    queryKey: ['blog'],
    queryFn: () => get<Post[]>('/blog'),
  })

  const categories = [...new Set((posts ?? []).map((p) => p.category).filter(Boolean))]

  return (
    <div className="wc-container py-10">
      <Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: 'Journal' }]} />

      <header className="mt-6 mb-12 max-w-2xl">
        <span className="wc-numeral">THE JOURNAL</span>
        <h1 className="mt-3 text-4xl">Notes from the workshop</h1>
        <p className="mt-4 text-sm text-muted">
          Care guides, styling notes and the occasional argument about why we
          still cut joints by hand.
        </p>
      </header>

      {categories.length > 0 && (
        <div className="mb-10 flex flex-wrap gap-2">
          {categories.map((category) => (
            <span key={category} className="wc-badge bg-sunken text-muted">
              {category}
            </span>
          ))}
        </div>
      )}

      {isLoading ? (
        <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="space-y-3">
              <Skeleton className="aspect-3/2 w-full" />
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-3 w-full" />
            </div>
          ))}
        </div>
      ) : (
        <div className="grid gap-x-8 gap-y-12 md:grid-cols-2 lg:grid-cols-3">
          {posts?.map((post, index) => (
            <article key={post.id} className="group">
              <Link to={`/journal/${post.slug}`}>
                <div className="mb-4 overflow-hidden bg-sunken" style={{ aspectRatio: '3 / 2' }}>
                  {post.cover_image_url ? (
                    <img
                      src={post.cover_image_url}
                      alt=""
                      loading="lazy"
                      className="size-full object-cover transition-transform duration-700 group-hover:scale-[1.04]"
                    />
                  ) : (
                    <div className="wc-grain relative size-full" />
                  )}
                </div>
                <div className="mb-2 flex items-center gap-3">
                  <span className="wc-numeral text-[0.7rem]">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  {post.category && <span className="wc-eyebrow">{post.category}</span>}
                </div>
                <h2 className="font-display text-xl leading-snug">{post.title}</h2>
                {post.excerpt && (
                  <p className="mt-2 line-clamp-2 text-sm text-muted">{post.excerpt}</p>
                )}
                <p className="mt-3 text-xs text-faint">
                  {formatDate(post.published_at)}
                  {post.reading_minutes && <> · {post.reading_minutes} min read</>}
                </p>
              </Link>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

export function JournalPostPage() {
  const { slug } = useParams()
  const { data: post, isLoading } = useQuery({
    queryKey: ['blog', slug],
    queryFn: () => get<Post>(`/blog/${slug}`),
    enabled: Boolean(slug),
  })

  if (isLoading) {
    return (
      <div className="wc-container py-16">
        <Skeleton className="mx-auto h-96 w-full max-w-3xl" />
      </div>
    )
  }
  if (!post) {
    return (
      <div className="wc-container py-16">
        <EmptyState
          title="Article not found"
          action={<Link to="/journal" className="wc-btn wc-btn-primary">Back to the journal</Link>}
        />
      </div>
    )
  }

  return (
    <article className="wc-container py-10">
      <Breadcrumbs
        items={[
          { label: 'Home', to: '/' },
          { label: 'Journal', to: '/journal' },
          { label: post.title },
        ]}
      />

      <header className="mx-auto mt-8 max-w-3xl text-center">
        {post.category && <span className="wc-eyebrow">{post.category}</span>}
        <h1 className="mt-3">{post.title}</h1>
        <p className="mt-5 text-xs text-faint">
          {post.author_name} · {formatDate(post.published_at)}
          {post.reading_minutes && <> · {post.reading_minutes} min read</>}
        </p>
      </header>

      {post.cover_image_url && (
        <img
          src={post.cover_image_url}
          alt=""
          className="mx-auto mt-10 max-w-4xl"
        />
      )}

      <div
        className="wc-prose mx-auto mt-12 text-base leading-relaxed [&_h2]:mt-10 [&_h2]:mb-3 [&_h2]:font-display [&_h2]:text-2xl [&_p]:mt-4"
        dangerouslySetInnerHTML={{ __html: post.body_html ?? '' }}
      />

      <div className="mx-auto mt-16 max-w-3xl border-t border-line pt-8 text-center">
        <Link to="/journal" className="wc-btn wc-btn-outline">More from the journal</Link>
      </div>
    </article>
  )
}

export function StaticPageView() {
  const { slug } = useParams()
  const { data: page, isLoading } = useQuery({
    queryKey: ['page', slug],
    queryFn: () => get<Page>(`/pages/${slug}`),
    enabled: Boolean(slug),
  })

  if (isLoading) {
    return (
      <div className="wc-container py-16">
        <Skeleton className="mx-auto h-96 w-full max-w-3xl" />
      </div>
    )
  }
  if (!page) {
    return (
      <div className="wc-container py-16">
        <EmptyState
          title="Page not found"
          action={<Link to="/" className="wc-btn wc-btn-primary">Back to home</Link>}
        />
      </div>
    )
  }

  return (
    <div className="wc-container py-10">
      <Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: page.title }]} />
      <div
        className="wc-prose mx-auto mt-10 text-base leading-relaxed [&_h1]:mb-6 [&_h2]:mt-10 [&_h2]:mb-3 [&_h2]:font-display [&_h2]:text-2xl [&_p]:mt-4"
        dangerouslySetInnerHTML={{ __html: page.body_html }}
      />
    </div>
  )
}

export function FaqPage() {
  const { data: faqs = [], isLoading } = useQuery({
    queryKey: ['faq'],
    queryFn: () => get<Faq[]>('/faq'),
  })

  const grouped = faqs.reduce<Record<string, Faq[]>>((acc, faq) => {
    ;(acc[faq.category] ??= []).push(faq)
    return acc
  }, {})

  return (
    <div className="wc-container py-10">
      <Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: 'FAQ' }]} />
      <header className="mt-6 mb-12 max-w-2xl">
        <h1 className="text-4xl">Frequently asked</h1>
        <p className="mt-3 text-sm text-muted">
          If your question is not here,{' '}
          <Link to="/contact" className="wc-link">write to us</Link> and a person
          will reply.
        </p>
      </header>

      {isLoading ? (
        <Skeleton className="h-64 w-full max-w-2xl" />
      ) : (
        <div className="max-w-2xl space-y-10">
          {Object.entries(grouped).map(([category, items]) => (
            <section key={category}>
              <h2 className="wc-eyebrow mb-4">{category}</h2>
              {items.map((faq) => (
                <Accordion key={faq.id} title={faq.question}>
                  <div dangerouslySetInnerHTML={{ __html: faq.answer_html }} />
                </Accordion>
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

export function ContactPage() {
  const [form, setForm] = useState({ name: '', email: '', subject: '', message: '' })
  const [sent, setSent] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const bind = (key: keyof typeof form) =>
    (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const result = await post<ApiMessage>('/contact', form)
      setSent(result.message)
      toast.success('Message sent')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send your message')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="wc-container py-10">
      <Breadcrumbs items={[{ label: 'Home', to: '/' }, { label: 'Contact' }]} />

      <div className="mt-8 grid max-w-4xl gap-12 md:grid-cols-2">
        <div>
          <h1 className="text-4xl">Get in touch</h1>
          <p className="mt-4 text-sm text-muted">
            Questions about a piece, a commission, or an order already placed.
            We usually reply within one working day.
          </p>

          <dl className="mt-8 space-y-4 text-sm">
            <div>
              <dt className="wc-eyebrow mb-1">Workshop</dt>
              <dd className="text-muted">14-C Commercial Area, Gulberg III, Lahore</dd>
            </div>
            <div>
              <dt className="wc-eyebrow mb-1">Email</dt>
              <dd><a href="mailto:hello@woodcroft.pk" className="wc-link">hello@woodcroft.pk</a></dd>
            </div>
            <div>
              <dt className="wc-eyebrow mb-1">Phone</dt>
              <dd className="text-muted">0300 1234567</dd>
            </div>
            <div>
              <dt className="wc-eyebrow mb-1">Hours</dt>
              <dd className="text-muted">Monday to Saturday, 10am to 7pm</dd>
            </div>
          </dl>
        </div>

        <div>
          {sent ? (
            <div className="wc-panel p-6">
              <h2 className="font-display text-xl">Message sent</h2>
              <p className="mt-3 text-sm text-muted">{sent}</p>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              {error && (
                <div role="alert" className="border border-[var(--wc-danger)] bg-danger-bg px-3 py-2 text-sm text-[var(--wc-danger)]">
                  {error}
                </div>
              )}
              <Field label="Your name" id="name" required>
                <Input id="name" required value={form.name} onChange={bind('name')} />
              </Field>
              <Field label="Email" id="email" required>
                <Input id="email" type="email" required value={form.email} onChange={bind('email')} />
              </Field>
              <Field label="Subject" id="subject" required>
                <Input id="subject" required value={form.subject} onChange={bind('subject')} />
              </Field>
              <Field label="Message" id="message" required>
                <Textarea id="message" required rows={6} value={form.message} onChange={bind('message')} />
              </Field>
              <Button type="submit" loading={loading} fullWidth>Send message</Button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
