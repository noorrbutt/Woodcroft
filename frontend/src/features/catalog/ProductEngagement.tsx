/**
 * Reviews and Q&A for the product page.
 *
 * The PDP previously showed only the rating histogram, with no way to read a
 * review or write one, and no Q&A at all. This adds both.
 */

import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Check, ThumbsUp } from 'lucide-react'

import { ApiError, get, post } from '@/lib/api'
import { relativeTime } from '@/lib/format'
import {
  Badge,
  Button,
  Field,
  Rating,
  Select,
  Tab,
  TabList,
  TabPanel,
  Tabs,
  Textarea,
} from '@/components/ui'
import { useAuthStore } from '@/features/auth/store'
import type { ApiMessage } from '@/lib/types'

interface Review {
  id: string
  author_name: string
  rating: number
  title: string | null
  body: string
  created_at: string
  is_verified_purchase: boolean
  helpful_count: number
  not_helpful_count: number
  reply: { display_name: string; body: string; created_at: string } | null
}

interface Question {
  id: string
  body: string
  asker_name: string
  created_at: string
  helpful_count: number
  answers: { body: string; is_official: boolean; created_at: string }[]
}

function StarInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex gap-1" role="radiogroup" aria-label="Your rating">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          role="radio"
          aria-checked={value === star}
          aria-label={`${star} star${star > 1 ? 's' : ''}`}
          onClick={() => onChange(star)}
          className="p-0.5"
        >
          <svg
            width={26}
            height={26}
            viewBox="0 0 24 24"
            className={star <= value ? 'fill-[var(--wc-brass)] text-[var(--wc-brass)]' : 'fill-none text-[var(--walnut-300)]'}
            stroke="currentColor"
            strokeWidth={1.5}
          >
            <path d="M12 2l2.9 6.3 6.6.6-5 4.4 1.5 6.5L12 17l-6 3.3 1.5-6.5-5-4.4 6.6-.6z" />
          </svg>
        </button>
      ))}
    </div>
  )
}

function WriteReview({ slug }: { slug: string }) {
  const user = useAuthStore((state) => state.user)
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ rating: 5, title: '', body: '' })

  const { data: eligibility } = useQuery({
    queryKey: ['can-review', slug],
    queryFn: () => get<{ can_review: boolean; verified: boolean; reason: string | null }>(
      `/products/${slug}/can-review`,
    ),
    enabled: Boolean(user),
  })

  const submit = useMutation({
    mutationFn: () => post<ApiMessage>(`/products/${slug}/reviews`, form),
    onSuccess: (result) => {
      toast.success(result.message)
      setOpen(false)
      setForm({ rating: 5, title: '', body: '' })
      queryClient.invalidateQueries({ queryKey: ['can-review', slug] })
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'email_not_verified') return
      toast.error(e instanceof ApiError ? e.message : 'Could not submit')
    },
  })

  if (!user) {
    return (
      <p className="text-sm text-muted">
        <Link to={`/login?next=/product/${slug}`} className="wc-link">Sign in</Link> to
        write a review.
      </p>
    )
  }
  if (eligibility && !eligibility.can_review) {
    return (
      <p className="text-sm text-muted">
        {eligibility.reason === 'already_reviewed'
          ? 'You have already reviewed this piece. Thank you.'
          : 'You can review this once you have bought it.'}
      </p>
    )
  }

  if (!open) {
    return <Button variant="outline" size="sm" onClick={() => setOpen(true)}>Write a review</Button>
  }

  return (
    <form
      onSubmit={(e: FormEvent) => { e.preventDefault(); submit.mutate() }}
      className="wc-panel space-y-4 p-5"
    >
      {eligibility?.verified && (
        <Badge tone="success">Verified purchase</Badge>
      )}
      <Field label="Your rating">
        <StarInput value={form.rating} onChange={(rating) => setForm((c) => ({ ...c, rating }))} />
      </Field>
      <Field label="Title (optional)" id="rtitle">
        <input
          id="rtitle"
          className="wc-input"
          maxLength={200}
          value={form.title}
          onChange={(e) => setForm((c) => ({ ...c, title: e.target.value }))}
        />
      </Field>
      <Field label="Your review" id="rbody" hint="At least 10 characters">
        <Textarea id="rbody" rows={4} required minLength={10} value={form.body}
                  onChange={(e) => setForm((c) => ({ ...c, body: e.target.value }))} />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" size="sm" loading={submit.isPending}
                disabled={form.body.trim().length < 10}>
          Submit review
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function ReviewList({ slug }: { slug: string }) {
  const [sort, setSort] = useState('recent')
  const user = useAuthStore((state) => state.user)
  const queryClient = useQueryClient()

  const { data: reviews = [], isLoading } = useQuery({
    queryKey: ['reviews', slug, sort],
    queryFn: () => get<Review[]>(`/products/${slug}/reviews`, { sort }),
  })

  const vote = useMutation({
    mutationFn: (id: string) => post(`/reviews/${id}/helpful?helpful=true`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['reviews', slug] }),
    onError: () => toast.error('Please sign in to vote'),
  })

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <WriteReview slug={slug} />
        {reviews.length > 0 && (
          <label className="flex items-center gap-2 text-xs text-muted">
            Sort
            <Select value={sort} onChange={(e) => setSort(e.target.value)}
                    className="w-auto py-1.5 text-xs">
              <option value="recent">Most recent</option>
              <option value="helpful">Most helpful</option>
              <option value="rating_high">Highest rated</option>
              <option value="rating_low">Lowest rated</option>
            </Select>
          </label>
        )}
      </div>

      {isLoading ? (
        <p className="text-sm text-faint">Loading reviews…</p>
      ) : reviews.length === 0 ? (
        <p className="text-sm text-muted">
          No reviews yet. If you have bought this, yours would be the first.
        </p>
      ) : (
        <ul className="space-y-6">
          {reviews.map((review) => (
            <li key={review.id} className="border-b border-line pb-6 last:border-0">
              <div className="mb-1.5 flex flex-wrap items-center gap-2">
                <Rating value={review.rating} showCount={false} size={13} />
                {review.is_verified_purchase && (
                  <span className="inline-flex items-center gap-1 text-[0.7rem] text-[var(--wc-success)]">
                    <Check size={11} strokeWidth={2.5} /> Verified purchase
                  </span>
                )}
              </div>
              {review.title && <p className="font-medium">{review.title}</p>}
              <p className="mt-1 text-sm text-muted">{review.body}</p>
              <div className="mt-2 flex items-center gap-4 text-xs text-faint">
                <span>{review.author_name} · {relativeTime(review.created_at)}</span>
                <button
                  onClick={() => (user ? vote.mutate(review.id) : toast.error('Please sign in to vote'))}
                  className="inline-flex items-center gap-1 hover:text-ink"
                >
                  <ThumbsUp size={12} strokeWidth={1.5} /> Helpful ({review.helpful_count})
                </button>
              </div>
              {review.reply && (
                <div className="mt-3 border-l-2 border-[var(--wc-brass)] bg-sunken p-3">
                  <p className="text-xs font-medium">{review.reply.display_name}</p>
                  <p className="mt-1 text-sm text-muted">{review.reply.body}</p>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function QuestionList({ slug }: { slug: string }) {
  const [body, setBody] = useState('')
  const [open, setOpen] = useState(false)

  const { data: questions = [], isLoading } = useQuery({
    queryKey: ['questions', slug],
    queryFn: () => get<Question[]>(`/products/${slug}/questions`),
  })

  const ask = useMutation({
    mutationFn: () => post<ApiMessage>(`/products/${slug}/questions`, { body }),
    onSuccess: (result) => {
      toast.success(result.message)
      setBody('')
      setOpen(false)
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'email_not_verified') return
      toast.error(e instanceof ApiError ? e.message : 'Could not send')
    },
  })

  return (
    <div>
      <div className="mb-6">
        {open ? (
          <form onSubmit={(e: FormEvent) => { e.preventDefault(); ask.mutate() }}
                className="wc-panel space-y-3 p-5">
            <Field label="Your question" id="qbody">
              <Textarea id="qbody" rows={3} required minLength={5} value={body}
                        onChange={(e) => setBody(e.target.value)}
                        placeholder="Ask anything about this piece." />
            </Field>
            <div className="flex gap-2">
              <Button type="submit" size="sm" loading={ask.isPending}
                      disabled={body.trim().length < 5}>Send question</Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <Button variant="outline" size="sm" onClick={() => setOpen(true)}>Ask a question</Button>
        )}
      </div>

      {isLoading ? (
        <p className="text-sm text-faint">Loading…</p>
      ) : questions.length === 0 ? (
        <p className="text-sm text-muted">
          No questions yet. Ask the first, and we will answer it here.
        </p>
      ) : (
        <ul className="space-y-5">
          {questions.map((q) => (
            <li key={q.id} className="border-b border-line pb-5 last:border-0">
              <p className="text-sm font-medium">Q. {q.body}</p>
              <p className="mt-0.5 text-xs text-faint">
                {q.asker_name} · {relativeTime(q.created_at)}
              </p>
              {q.answers.map((a, i) => (
                <div key={i} className="mt-2 pl-4">
                  <p className="text-sm text-muted">
                    A. {a.body}
                    {a.is_official && (
                      <Badge tone="success" className="ml-2">Woodcroft</Badge>
                    )}
                  </p>
                </div>
              ))}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function ProductEngagement({
  slug,
  reviewCount,
}: {
  slug: string
  reviewCount: number
}) {
  return (
    <Tabs defaultValue="reviews">
      <TabList>
        <Tab value="reviews">Reviews{reviewCount > 0 ? ` (${reviewCount})` : ''}</Tab>
        <Tab value="questions">Questions</Tab>
      </TabList>
      <TabPanel value="reviews">
        <ReviewList slug={slug} />
      </TabPanel>
      <TabPanel value="questions">
        <QuestionList slug={slug} />
      </TabPanel>
    </Tabs>
  )
}
