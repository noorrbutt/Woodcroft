import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, Hammer, Leaf, Truck } from 'lucide-react'

import { get, post } from '@/lib/api'
import { useReveal } from '@/hooks/useReveal'
import { Button, SectionHeading } from '@/components/ui'
import { ProductGrid } from '@/features/catalog/ProductCard'
import type { Category, ProductList } from '@/lib/types'

/**
 * Homepage.
 *
 * One still hero, not a carousel. Rotating heroes are a conversion and taste
 * liability, and no premium furniture brand ships one. The life in it comes
 * from a slow ken burns on the image instead.
 */

function Hero() {
  return (
    <section
      className="relative overflow-hidden bg-inverse text-on-inverse"
      /* svh, not vh: 100vh jumps by about 60px on mobile Safari when the URL
         bar collapses, which reads as a broken page on the most important
         screen in the whole site. */
      style={{ minHeight: 'min(88svh, 860px)' }}
    >
      <div className="absolute inset-0 overflow-hidden">
        {/* A dedicated edge-to-edge wood field, not a product plate. A plate
            is a framed panel on paper, so it leaves a visible vertical seam
            down the hero wherever the panel stops. */}
        <img
          src="/media/hero/workshop_2400.webp"
          srcSet="/media/hero/workshop_800.webp 800w, /media/hero/workshop_1600.webp 1600w, /media/hero/workshop_2400.webp 2400w"
          sizes="100vw"
          alt=""
          aria-hidden
          fetchPriority="high"
          className="wc-kenburns size-full object-cover opacity-55"
        />
        <div
          className="absolute inset-0"
          style={{
            background:
              'linear-gradient(102deg, rgb(18 13 9 / 0.94) 0%, rgb(18 13 9 / 0.78) 38%, rgb(18 13 9 / 0.42) 72%, rgb(18 13 9 / 0.55) 100%)',
          }}
        />
      </div>

      <div className="wc-container relative flex flex-col justify-center" style={{ minHeight: 'min(88svh, 860px)' }}>
        <div className="max-w-2xl py-24">
          <div className="mb-6 flex items-center gap-3">
            <span className="wc-numeral !text-[var(--brass-300)]">EST 2002</span>
            <span className="h-px w-12 bg-[var(--brass-400)]" aria-hidden />
            <span className="wc-eyebrow !text-[var(--walnut-200)]">Karachi</span>
          </div>

          <h1 className="text-[var(--walnut-50)]">
            Made to be kept.
          </h1>

          <p className="mt-6 max-w-lg text-base leading-relaxed text-[var(--walnut-200)]">
            Solid sheesham, walnut and teak, cut and joined by hand. No veneer,
            no board, no shortcuts on the side nobody sees.
          </p>

          <div className="mt-10 flex flex-wrap gap-3">
            <Link to="/shop" className="wc-btn wc-btn-brass wc-btn-lg">
              Explore the collection
            </Link>
            <Link
              to="/collections/bespoke"
              className="wc-btn wc-btn-lg border border-[var(--walnut-400)] text-[var(--walnut-100)] hover:bg-white/5"
            >
              Commission a piece
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

function AssuranceStrip() {
  const items = [
    { icon: Hammer, title: 'Joined by hand', body: 'Mortise and tenon, cut dovetails, no flat pack.' },
    { icon: Truck, title: 'Delivered nationwide', body: 'Free over Rs 20,000. Cash on delivery available.' },
    { icon: Leaf, title: 'Traceable timber', body: 'Every board sourced from a named mill.' },
  ]
  return (
    <section className="border-b border-line bg-surface">
      <div className="wc-container grid gap-8 py-10 sm:grid-cols-3">
        {items.map(({ icon: Icon, title, body }) => (
          <div key={title} className="flex gap-3.5">
            <Icon size={20} strokeWidth={1.25} className="mt-0.5 shrink-0 text-[var(--wc-brass)]" />
            <div>
              <h3 className="font-sans text-sm font-semibold">{title}</h3>
              <p className="mt-0.5 text-xs leading-relaxed text-muted">{body}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function Collections() {
  const ref = useReveal<HTMLElement>()
  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: () => get<Category[]>('/categories'),
    staleTime: 10 * 60_000,
  })

  return (
    <section ref={ref} className="wc-section wc-reveal">
      <div className="wc-container">
        <SectionHeading
          numeral="01"
          title="The collections"
          description="Nine rooms' worth of work, from a six-seat dining table down to a chopping board."
        />

        {/* Deliberately dark walnut plaques in both themes. It reads as engraved
            wood, ties the section to the hero and story bands, and sidesteps the
            surface flip entirely so the text is always cream on wood and never
            washes out in dark mode. */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {categories.slice(0, 6).map((category, index) => (
            <Link
              key={category.id}
              to={`/collections/${category.slug}`}
              className="wc-lift group relative flex min-h-[13.5rem] flex-col justify-end overflow-hidden rounded-sm p-6 ring-1 ring-black/10"
              style={{
                background:
                  'linear-gradient(150deg, var(--walnut-800) 0%, var(--walnut-900) 100%)',
              }}
            >
              <div className="wc-grain absolute inset-0 opacity-60" aria-hidden />
              {/* Brass baseline that lights up on hover. */}
              <span
                className="absolute inset-x-0 bottom-0 h-px bg-[var(--brass-400)] opacity-40 transition-opacity duration-300 group-hover:opacity-90"
                aria-hidden
              />
              <span className="wc-numeral relative mb-2 !text-[var(--brass-300)]">
                {String(index + 1).padStart(2, '0')}
              </span>
              <h3 className="relative font-display text-2xl text-[var(--walnut-50)]">
                {category.name}
              </h3>
              <p className="relative mt-1 text-xs text-[var(--walnut-200)]">
                {category.product_count} pieces
              </p>
              <ArrowRight
                size={18}
                strokeWidth={1.5}
                className="absolute right-6 top-6 text-[var(--brass-300)] transition-transform duration-300 group-hover:translate-x-1"
                aria-hidden
              />
            </Link>
          ))}
        </div>
      </div>
    </section>
  )
}

function ProductRail({
  numeral,
  title,
  description,
  params,
  href,
}: {
  numeral: string
  title: string
  description: string
  params: Record<string, unknown>
  href: string
}) {
  const ref = useReveal<HTMLElement>()
  const { data, isLoading } = useQuery({
    queryKey: ['products', params],
    queryFn: () => get<ProductList>('/products', { per_page: 4, ...params }),
  })

  return (
    <section ref={ref} className="wc-section wc-reveal">
      <div className="wc-container">
        <SectionHeading
          numeral={numeral}
          title={title}
          description={description}
          action={
            <Link to={href} className="wc-link text-sm">
              View all
            </Link>
          }
        />
        <ProductGrid products={data?.items} loading={isLoading} skeletonCount={4} />
      </div>
    </section>
  )
}

function Story() {
  const ref = useReveal<HTMLElement>()
  return (
    <section ref={ref} className="wc-reveal bg-inverse text-on-inverse">
      <div className="wc-container wc-section">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <span className="wc-numeral !text-on-inverse opacity-70">04</span>
            <h2 className="mt-4 text-on-inverse">
              Every board is chosen by hand
            </h2>
            <div className="mt-6 space-y-4 text-sm leading-relaxed text-on-inverse opacity-80">
              <p>
                Timber arrives at the yard behind the workshop as rough sawn
                boards. It is stacked, stickered and left to settle for months
                before anyone touches it with a saw.
              </p>
              <p>
                Rushing that stage is the single most common reason furniture
                cracks a year later, and it is the part of the process nobody
                photographs.
              </p>
            </div>
            <Link
              to="/page/about"
              className="wc-btn wc-btn-brass mt-8"
            >
              Read our story
            </Link>
          </div>

          <figure className="relative">
            <blockquote className="border-l-2 border-on-inverse/40 pl-6">
              <p className="font-display text-2xl leading-relaxed text-on-inverse"
                 style={{ fontVariationSettings: '"SOFT" 40, "WONK" 1, "opsz" 72' }}>
                “They measured my alcove twice before cutting anything. That
                tells you everything.”
              </p>
              <figcaption className="mt-5 text-xs tracking-widest uppercase text-on-inverse opacity-70">
                Hira Malik — Islamabad
              </figcaption>
            </blockquote>
          </figure>
        </div>
      </div>
    </section>
  )
}

function Newsletter() {
  const [email, setEmail] = useState('')
  const subscribe = useMutation({
    mutationFn: () => post<{ message: string }>('/newsletter', { email, source: 'home' }),
  })

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (email.trim()) subscribe.mutate()
  }

  return (
    <section className="border-t border-line bg-sunken">
      <div className="wc-container py-16 text-center">
        <h2 className="font-display text-2xl">10% off your first order</h2>
        <p className="mx-auto mt-3 max-w-md text-sm text-muted">
          Care guides, new pieces and the occasional look inside the workshop.
          No more than twice a month.
        </p>
        {subscribe.isSuccess ? (
          <p className="mx-auto mt-7 max-w-md text-sm text-[var(--wc-success)]">
            {subscribe.data.message}
          </p>
        ) : (
          <form className="mx-auto mt-7 flex max-w-md gap-2" onSubmit={onSubmit}>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              aria-label="Email address"
              className="wc-input"
            />
            <Button type="submit" loading={subscribe.isPending} className="shrink-0">
              Subscribe
            </Button>
          </form>
        )}
        {subscribe.isError && (
          <p className="mx-auto mt-3 max-w-md text-sm text-[var(--wc-danger)]">
            Something went wrong. Please try again.
          </p>
        )}
      </div>
    </section>
  )
}

export function HomePage() {
  return (
    <>
      <Hero />
      <AssuranceStrip />
      <Collections />
      <ProductRail
        numeral="02"
        title="New arrivals"
        description="The most recent pieces to come out of the workshop."
        params={{ new_arrivals: true, sort: 'newest' }}
        href="/shop?new_arrivals=true"
      />
      <ProductRail
        numeral="03"
        title="On sale"
        description="Reduced while stocks last. Every piece is the same build as full price."
        params={{ on_sale: true }}
        href="/shop?on_sale=true"
      />
      <Story />
      <ProductRail
        numeral="05"
        title="Best selling"
        description="What our customers keep coming back for."
        params={{ sort: 'bestselling' }}
        href="/shop?sort=bestselling"
      />
      <Newsletter />
    </>
  )
}

export default HomePage
