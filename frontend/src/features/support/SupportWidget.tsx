/**
 * Support widget.
 *
 * Deliberately not a third-party chat bubble. Those need an external account,
 * they load a script that can see the whole page, and there is nobody sitting
 * on the other end of one in this deployment. This opens a real support ticket
 * against the same system the admin panel works from, so a message sent here
 * genuinely arrives somewhere a person will see it.
 */

import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { MessageCircle, X } from 'lucide-react'

import { ApiError, get, post } from '@/lib/api'
import { Button, Field, Input, Select, Textarea } from '@/components/ui'
import { useAuthStore } from '@/features/auth/store'
import type { ApiMessage } from '@/lib/types'

interface Faq {
  id: string
  question: string
  answer_html: string
  category: string
}

export function SupportWidget() {
  const [open, setOpen] = useState(false)
  const [sent, setSent] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const user = useAuthStore((state) => state.user)

  const [form, setForm] = useState({
    name: '',
    email: '',
    subject: '',
    message: '',
  })

  // A handful of FAQs answer most of what arrives here, so offering them
  // first is better for the customer than making them wait for a reply.
  const { data: faqs = [] } = useQuery({
    queryKey: ['faq'],
    queryFn: () => get<Faq[]>('/faq'),
    enabled: open,
    staleTime: 10 * 60_000,
  })

  const bind = (key: keyof typeof form) =>
    (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const result = await post<ApiMessage>('/contact', {
        name: user?.full_name || form.name,
        email: user?.email || form.email,
        subject: form.subject,
        message: form.message,
      })
      setSent(result.message)
      toast.success('Message sent')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send your message')
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setOpen(false)
    setSent(null)
    setError(null)
    setForm({ name: '', email: '', subject: '', message: '' })
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label="Get help"
        className="fixed bottom-5 right-5 z-40 flex size-12 items-center justify-center
                   rounded-full bg-accent text-on-accent shadow-lg transition-transform
                   hover:scale-105 wc-no-print"
      >
        <MessageCircle size={20} strokeWidth={1.5} />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-end p-4 sm:p-5 wc-no-print">
          <button
            className="absolute inset-0 bg-[var(--wc-scrim)] sm:bg-transparent"
            onClick={reset}
            aria-label="Close"
            tabIndex={-1}
          />

          <div
            role="dialog"
            aria-modal="true"
            aria-label="Get help"
            className="relative flex max-h-[80vh] w-full max-w-sm flex-col
                       border border-line bg-raised shadow-xl"
            style={{ animation: 'wcPop 220ms var(--wc-ease-out)' }}
          >
            <header className="flex items-start justify-between border-b border-line px-5 py-4">
              <div>
                <h2 className="font-display text-lg">How can we help?</h2>
                <p className="text-xs text-faint">We usually reply within a working day.</p>
              </div>
              <button onClick={reset} aria-label="Close" className="p-1 text-muted hover:text-ink">
                <X size={17} strokeWidth={1.5} />
              </button>
            </header>

            <div className="flex-1 overflow-y-auto px-5 py-4">
              {sent ? (
                <div className="py-6 text-center">
                  <p className="font-display text-lg">Thank you</p>
                  <p className="mt-2 text-sm text-muted">{sent}</p>
                  <Button variant="outline" size="sm" className="mt-5" onClick={reset}>
                    Close
                  </Button>
                </div>
              ) : (
                <>
                  {faqs.length > 0 && (
                    <div className="mb-5">
                      <p className="wc-eyebrow mb-2">Quick answers</p>
                      <ul className="space-y-1.5">
                        {faqs.slice(0, 4).map((faq) => (
                          <li key={faq.id}>
                            <Link
                              to="/faq"
                              onClick={reset}
                              className="text-sm text-muted hover:text-ink"
                            >
                              {faq.question}
                            </Link>
                          </li>
                        ))}
                      </ul>
                      <div className="my-4 h-px bg-[var(--wc-border-subtle)]" />
                    </div>
                  )}

                  <form onSubmit={submit} className="space-y-3">
                    {error && (
                      <p role="alert" className="text-sm text-[var(--wc-danger)]">{error}</p>
                    )}

                    {!user && (
                      <>
                        <Field label="Your name" id="sname">
                          <Input id="sname" required value={form.name} onChange={bind('name')}
                                 className="py-2 text-sm" />
                        </Field>
                        <Field label="Email" id="semail">
                          <Input id="semail" type="email" required value={form.email}
                                 onChange={bind('email')} className="py-2 text-sm" />
                        </Field>
                      </>
                    )}

                    <Field label="Subject" id="ssubject">
                      <Select id="ssubject" required value={form.subject} onChange={bind('subject')}
                              className="py-2 text-sm">
                        <option value="">Choose a topic</option>
                        <option value="Question about an order">Question about an order</option>
                        <option value="Question about a product">Question about a product</option>
                        <option value="Delivery">Delivery</option>
                        <option value="Returns">Returns</option>
                        <option value="A bespoke commission">A bespoke commission</option>
                        <option value="Something else">Something else</option>
                      </Select>
                    </Field>

                    <Field label="Message" id="smessage">
                      <Textarea id="smessage" required rows={4} value={form.message}
                                onChange={bind('message')} className="py-2 text-sm"
                                placeholder="Tell us what you need." />
                    </Field>

                    <Button type="submit" fullWidth size="sm" loading={loading}>
                      Send message
                    </Button>

                    <p className="text-center text-xs text-faint">
                      Or email <a href="mailto:hello@woodcroft.pk" className="wc-link">hello@woodcroft.pk</a>
                    </p>
                  </form>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
