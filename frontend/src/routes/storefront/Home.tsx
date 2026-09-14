import { useState, type CSSProperties, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, Hammer, Leaf, Truck } from 'lucide-react'

import { get, post } from '@/lib/api'
import { cn } from '@/lib/cn'
import { useReveal } from '@/hooks/useReveal'
import { Button, SectionHeading, Skeleton } from '@/components/ui'
import { ProductCard, ProductGrid } from '@/features/catalog/ProductCard'
import type { Category, ProductList } from '@/lib/types'

/**
 * Homepage.
 *
 * Arranged like an edited furniture magazine rather than a stack of identical
 * bands: warm bone paper broken by a few committed dark moments, real timber
 * shown wherever the eye lands, and one confident typographic voice used at
 * scale. Every band varies its figure-ground and no module repeats verbatim.
 */

/** Inline custom property for the staggered-reveal index. */
const step = (i: number): CSSProperties => ({ '--wc-i': i } as CSSProperties)

function Hero() {
  const ref = useReveal<HTMLDivElement>()
  return (
    <section
      className="relative overflow-hidden bg-inverse text-on-inverse"
      /* svh, not vh: 100vh jumps by about 60px on mobile Safari when the URL
         bar collapses, which reads as a broken page on the most important
         screen in the whole site. */
      style={{ minHeight: 'min(90svh, 900px)' }}
    >
      <div className="absolute inset-0 overflow-hidden">
        <img
          src="/media/hero/workshop_2400.webp"
          srcSet="/media/hero/workshop_800.webp 800w, /media/hero/workshop_1600.webp 1600w, /media/hero/workshop_2400.webp 2400w"
          sizes="100vw"
          alt=""
          aria-hidden
          fetchPriority="high"
          className="wc-kenburns size-full object-cover opacity-75"
        />
        {/* Warm walnut scrim, darkest on the left where the text sits and
            opening to the right so the grain and tools read. Never neutral
            black — walnut-900 is rgb(31 22 16). */}
        <div
          className="absolute inset-0"
          style={{
            background:
              'linear-gradient(102deg, rgb(31 22 16 / 0.86) 0%, rgb(31 22 16 / 0.66) 40%, rgb(31 22 16 / 0.28) 74%, rgb(31 22 16 / 0.45) 100%)',
          }}
        />
        {/* Settle the hero into the page below instead of a hard cut. */}
        <div
          className="absolute inset-x-0 bottom-0 h-24"
          style={{ background: 'linear-gradient(to bottom, transparent, var(--wc-canvas))' }}
          aria-hidden
        />
      </div>

      <div
        ref={ref}
        className="wc-container wc-reveal relative flex flex-col justify-center"
        style={{ minHeight: 'min(90svh, 900px)' }}
      >
        <div className="wc-reveal-stagger max-w-2xl py-24">
          <div className="mb-6 flex items-center gap-3" style={step(0)}>
            <span className="wc-numeral !text-[var(--brass-300)]">EST 2002</span>
            <span className="h-px w-12 bg-[var(--brass-400)]" aria-hidden />
            <span className="wc-eyebrow !text-[var(--walnut-200)]">Karachi</span>
          </div>

          <h1 className="text-balance text-[var(--walnut-50)]" style={step(1)}>
            Made to be kept.
          </h1>

          <p
            className="mt-6 max-w-lg text-base leading-relaxed text-[var(--walnut-200)]"
            style={step(2)}
          >
            Solid sheesham, walnut and teak, cut and joined by hand. No veneer,
            no board, no shortcuts on the side nobody sees.
          </p>

          <div className="mt-10 flex flex-wrap gap-3" style={step(3)}>
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
      <div className="wc-container grid sm:grid-cols-3 sm:divide-x sm:divide-line">
        {items.map(({ icon: Icon, title, body }, i) => (
          <div key={title} className="py-9 sm:px-8 sm:first:pl-0 sm:last:pr-0">
            <div className="mb-3 flex items-center gap-3">
              <span className="wc-numeral">{`0${i + 1}`}</span>
              <span className="h-px w-8 bg-[var(--wc-brass)]" aria-hidden />
            </div>
            <div className="flex gap-3">
              <Icon size={20} strokeWidth={1.25} className="mt-0.5 shrink-0 text-[var(--wc-brass)]" />
              <div>
                <h3 className="font-sans text-sm font-semibold">{title}</h3>
                <p className="mt-0.5 text-xs leading-relaxed text-muted">{body}</p>
              </div>
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

  const walnutBg = 'linear-gradient(150deg, var(--walnut-800) 0%, var(--walnut-900) 100%)'
  const forestBg = 'linear-gradient(150deg, var(--forest-700) 0%, var(--forest-800) 100%)'

  return (
    <section ref={ref} className="wc-section wc-reveal overflow-hidden">
      <div className="wc-container relative">
        <SectionHeading
          numeral="01"
          ghost
          title="The collections"
          description="Nine rooms' worth of work, from a six-seat dining table down to a chopping board."
        />

        {/* A bento wall: one 2x2 flagship, then a run of image tiles. Real
            timber shows through; a walnut/forest scrim keeps the label legible
            in both themes without hiding the photo. */}
        <div className="wc-reveal-stagger grid gap-4 sm:grid-cols-2 lg:auto-rows-[15rem] lg:grid-cols-3">
          {categories.slice(0, 6).map((category, index) => {
            const feature = index === 0
            const hasImage = Boolean(category.image_url)
            const fallback = index % 3 === 2 ? forestBg : walnutBg
            return (
              <Link
                key={category.id}
                to={`/collections/${category.slug}`}
                style={{ ...step(Math.min(index, 7)), background: fallback }}
                className={cn(
                  'wc-lift group relative flex min-h-[19rem] flex-col justify-end overflow-hidden rounded-sm p-6 ring-1 ring-black/10',
                  feature ? 'lg:col-span-2 lg:row-span-2' : 'lg:min-h-0',
                )}
              >
                {hasImage && (
                  <>
                    <img
                      src={category.image_url!}
                      alt=""
                      aria-hidden
                      loading="lazy"
                      className="absolute inset-0 size-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
                    />
                    <div
                      className="absolute inset-0"
                      aria-hidden
                      style={{
                        background:
                          'linear-gradient(to top, var(--walnut-900) 4%, rgb(31 22 16 / 0.62) 42%, rgb(31 22 16 / 0.12) 100%)',
                      }}
                    />
                  </>
                )}
                <div className="wc-grain absolute inset-0 opacity-40" aria-hidden />
                <span
                  className="absolute inset-x-0 bottom-0 h-px bg-[var(--brass-400)] opacity-40 transition-opacity duration-300 group-hover:opacity-90"
                  aria-hidden
                />
                <span className="wc-numeral relative mb-2 !text-[var(--brass-300)]">
                  {String(index + 1).padStart(2, '0')}
                </span>
                {feature ? (
                  <h3
                    className="relative font-display text-[clamp(2.5rem,4vw,3.25rem)] leading-[1.05] text-[var(--walnut-50)]"
                    style={{ fontVariationSettings: '"SOFT" 40, "WONK" 1, "opsz" 96' }}
                  >
                    {category.name}
                  </h3>
                ) : (
                  <h3 className="relative font-display text-2xl text-[var(--walnut-50)]">
                    {category.name}
                  </h3>
                )}
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
            )
          })}
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
  tone = 'plain',
  layout = 'grid',
  ghost = false,
}: {
  numeral: string
  title: string
  description: string
  params: Record<string, unknown>
  href: string
  tone?: 'plain' | 'sunken'
  layout?: 'grid' | 'rail'
  ghost?: boolean
}) {
  const ref = useReveal<HTMLElement>()
  const { data, isLoading } = useQuery({
    queryKey: ['products', params],
    queryFn: () => get<ProductList>('/products', { per_page: layout === 'rail' ? 8 : 4, ...params }),
  })

  type Item = ProductList['items'][number]
  const railItems: (Item | undefined)[] = isLoading
    ? Array.from({ length: 5 }, () => undefined)
    : data?.items ?? []

  return (
    <section
      ref={ref}
      className={cn('wc-section wc-reveal', tone === 'sunken' && 'border-y border-line bg-sunken')}
    >
      <div className="wc-container relative overflow-hidden">
        <SectionHeading
          numeral={numeral}
          title={title}
          description={description}
          ghost={ghost}
          action={
            <Link to={href} className="wc-link text-sm">
              View all
            </Link>
          }
        />
        {layout === 'rail' ? (
          // A horizontal peek-scroller: the half-visible next card signals a
          // curated selection with more behind it, and no module repeats the
          // same four-up grid verbatim.
          <div className="wc-scroll-x wc-no-scrollbar -mx-[var(--wc-gutter)] flex gap-5 px-[var(--wc-gutter)] [scroll-snap-type:x_mandatory]">
            {railItems.map((product, i) => (
              <div
                key={product?.id ?? i}
                className="shrink-0 basis-[72%] [scroll-snap-align:start] sm:basis-[42%] lg:basis-[23%]"
              >
                {product ? (
                  <ProductCard product={product} />
                ) : (
                  <Skeleton className="aspect-[4/5] w-full" />
                )}
              </div>
            ))}
          </div>
        ) : (
          <ProductGrid products={data?.items} loading={isLoading} skeletonCount={4} stagger />
        )}
      </div>
    </section>
  )
}

function Story() {
  const ref = useReveal<HTMLElement>()
  return (
    <section
      ref={ref}
      className="wc-reveal relative overflow-hidden"
      /* The one deep-forest band on the page — the brand's third pillar, used
         exactly once. Fixed in both themes, so its copy uses fixed forest
         tokens, never text-on-inverse (which would go dark in dark mode). */
      style={{ background: 'linear-gradient(160deg, var(--forest-700), var(--forest-800))' }}
    >
      <div className="wc-container wc-section relative">
        <div className="grid items-center gap-x-16 gap-y-12 lg:grid-cols-[0.9fr_1.1fr]">
          <div>
            <span className="wc-numeral !text-[var(--brass-300)]">04</span>
            <h2 className="mt-4 text-[var(--forest-50)]">Every board is chosen by hand</h2>
            <div className="mt-6 max-w-[34rem] space-y-4 text-[1.0625rem] leading-[1.75] text-[var(--forest-100)]">
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
            <Link to="/page/about" className="wc-btn wc-btn-brass mt-8">
              Read our story
            </Link>
          </div>

          <figure className="relative">
            <div className="relative">
              <img
                src="/media/hero/story_1600.webp"
                srcSet="/media/hero/story_800.webp 800w, /media/hero/story_1600.webp 1600w"
                sizes="(min-width: 1024px) 55vw, 100vw"
                alt="A craftsman planing a solid board in the Woodcroft workshop"
                loading="lazy"
                className="w-full rounded-sm object-cover shadow-xl"
                style={{ aspectRatio: '5 / 4' }}
              />
              <blockquote className="absolute bottom-4 left-4 max-w-[17rem] border-l-2 border-[var(--brass-400)]/50 bg-[var(--walnut-900)]/85 p-5 backdrop-blur-sm sm:-left-6 sm:bottom-8">
                <p
                  className="font-display text-[clamp(1.6rem,3.2vw,2.15rem)] leading-[1.2] text-[var(--walnut-50)]"
                  style={{ fontVariationSettings: '"SOFT" 40, "WONK" 1, "opsz" 96' }}
                >
                  “They measured my alcove twice before cutting anything.”
                </p>
                <figcaption className="mt-4 text-xs uppercase tracking-widest text-[var(--brass-200)]">
                  Hira Malik — Islamabad
                </figcaption>
              </blockquote>
            </div>
            <figcaption className="wc-eyebrow mt-8 !text-[var(--forest-200)]">
              The drying yard — Surjani Town, Karachi
            </figcaption>
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
    <section className="relative overflow-hidden border-t border-line bg-inverse text-on-inverse">
      <span className="absolute inset-x-0 top-0 h-px bg-[var(--brass-400)] opacity-50" aria-hidden />
      <div className="wc-grain absolute inset-0 opacity-50" aria-hidden />
      <div className="wc-container relative grid gap-8 py-20 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
        <div>
          <span className="wc-numeral !text-[var(--brass-300)]">06</span>
          <h2 className="mt-4 text-on-inverse">10% off your first order</h2>
          <p className="mt-3 max-w-md text-sm text-on-inverse opacity-80">
            Care guides, new pieces and the occasional look inside the workshop.
            No more than twice a month.
          </p>
        </div>
        <div>
          {subscribe.isSuccess ? (
            <p className="text-sm text-[var(--wc-success)]">{subscribe.data.message}</p>
          ) : (
            <form className="flex max-w-md gap-2" onSubmit={onSubmit}>
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
            <p className="mt-3 text-sm text-[var(--wc-danger)]">
              Something went wrong. Please try again.
            </p>
          )}
        </div>
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
        title="Best selling"
        description="What our customers keep coming back for."
        params={{ sort: 'bestselling' }}
        href="/shop?sort=bestselling"
        layout="rail"
      />
      <ProductRail
        numeral="03"
        title="New arrivals"
        description="The most recent pieces to come out of the workshop."
        params={{ new_arrivals: true, sort: 'newest' }}
        href="/shop?new_arrivals=true"
        tone="sunken"
      />
      <Story />
      <ProductRail
        numeral="05"
        title="On sale"
        description="Reduced while stocks last. Every piece is the same build as full price."
        params={{ on_sale: true }}
        href="/shop?on_sale=true"
        ghost
      />
      <Newsletter />
    </>
  )
}

export default HomePage
