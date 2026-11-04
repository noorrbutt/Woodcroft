import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Check, FileDown, Heart, Truck } from 'lucide-react'

import { get } from '@/lib/api'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { cn } from '@/lib/cn'
import { formatDimensions, formatPkr, formatWeight } from '@/lib/format'
import {
  Accordion,
  Badge,
  Breadcrumbs,
  Button,
  Field,
  Input,
  Price,
  QuantityStepper,
  EmptyState,
  Rating,
  SectionHeading,
  Skeleton,
} from '@/components/ui'
import { ProductGrid } from '@/features/catalog/ProductCard'
import { ProductEngagement } from '@/features/catalog/ProductEngagement'
import {
  useCartStore,
  useWishlistStore,
  type PersonalizationValue,
} from '@/features/cart/store'
import type {
  ProductCard as Card,
  ProductDetail,
  RatingBreakdown,
  Variant,
} from '@/lib/types'

function Gallery({ product }: { product: ProductDetail }) {
  const [index, setIndex] = useState(0)
  const [zoom, setZoom] = useState(false)
  const [origin, setOrigin] = useState({ x: 50, y: 50 })
  const image = product.images[index]

  return (
    <div className="flex gap-3">
      {product.images.length > 1 && (
        <div className="flex w-16 shrink-0 flex-col gap-2">
          {product.images.map((thumb, i) => (
            <button
              key={thumb.id}
              onClick={() => setIndex(i)}
              aria-label={`View image ${i + 1}`}
              aria-current={i === index}
              className={cn(
                'overflow-hidden border transition-colors',
                i === index ? 'border-[var(--wc-brass)]' : 'border-transparent hover:border-control',
              )}
            >
              <img
                src={thumb.thumb_url}
                alt=""
                className="aspect-4/5 w-full object-cover"
                loading="lazy"
                decoding="async"
              />
            </button>
          ))}
        </div>
      )}

      <div
        className="relative min-w-0 flex-1 overflow-hidden bg-sunken"
        style={{ aspectRatio: '4 / 5' }}
        onMouseEnter={() => setZoom(true)}
        onMouseLeave={() => setZoom(false)}
        onMouseMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect()
          setOrigin({
            x: ((event.clientX - rect.left) / rect.width) * 100,
            y: ((event.clientY - rect.top) / rect.height) * 100,
          })
        }}
      >
        {image && (
          <img
            src={image.url}
            srcSet={image.srcset}
            sizes="(min-width: 1024px) 48vw, 92vw"
            alt={image.alt_text || product.name}
            fetchPriority="high"
            decoding="async"
            className="size-full object-cover transition-transform duration-300 ease-out"
            style={{
              transform: zoom ? 'scale(1.7)' : 'scale(1)',
              transformOrigin: `${origin.x}% ${origin.y}%`,
            }}
          />
        )}
        <div className="absolute left-3 top-3 flex flex-col gap-1.5">
          {product.discount_percent != null && (
            <Badge tone="sale">−{product.discount_percent}%</Badge>
          )}
          {product.tags.map((tag) => (
            <Badge key={tag.slug} tone="neutral">{tag.name}</Badge>
          ))}
        </div>
      </div>
    </div>
  )
}

/* Common size presets plus a custom option for made-to-order dimensions.
   "Standard" carries no surcharge (the piece as shown); the others are treated
   as personalised and priced by the option's surcharge. */
const DIMENSION_PRESETS = [
  { key: 'standard', label: 'Standard', value: '' },
  { key: 'compact', label: 'Compact', value: 'Compact - about 10% smaller than standard' },
  { key: 'large', label: 'Large', value: 'Large - about 10% larger than standard' },
  { key: 'custom', label: 'Custom size', value: null },
] as const

function DimensionPicker({
  value,
  defaultDims,
  onChange,
}: {
  value: string
  defaultDims: string | null
  onChange: (next: string) => void
}) {
  const knownPreset = DIMENSION_PRESETS.find(
    (p) => p.value !== null && p.value === value,
  )
  const [mode, setMode] = useState<string>(
    value === '' ? 'standard' : knownPreset ? knownPreset.key : 'custom',
  )

  const pick = (preset: (typeof DIMENSION_PRESETS)[number]) => {
    setMode(preset.key)
    onChange(preset.value === null ? '' : preset.value)
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {DIMENSION_PRESETS.map((preset) => (
          <button
            key={preset.key}
            type="button"
            onClick={() => pick(preset)}
            aria-pressed={mode === preset.key}
            className={cn(
              'border px-3 py-1.5 text-xs transition-colors',
              mode === preset.key
                ? 'border-[var(--wc-border-strong)] bg-sunken text-ink'
                : 'border-control text-muted hover:border-[var(--wc-border-strong)]',
            )}
          >
            {preset.label}
          </button>
        ))}
      </div>
      {mode === 'custom' && (
        <Input
          className="mt-2"
          placeholder={defaultDims ? `As shown: ${defaultDims}` : 'e.g. 200 × 95 × 76 cm'}
          value={value}
          maxLength={60}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
      {mode === 'standard' && defaultDims && (
        <p className="mt-2 text-xs text-faint">As shown: {defaultDims}</p>
      )}
    </div>
  )
}

function PersonalizationFields({
  product,
  values,
  onChange,
}: {
  product: ProductDetail
  values: Record<string, string>
  onChange: (key: string, value: string) => void
}) {
  if (product.personalization_options.length === 0) return null

  return (
    <div className="space-y-4 border border-line bg-sunken p-4">
      <div className="flex items-center gap-2">
        <span className="wc-eyebrow">Make it yours</span>
        <span className="h-px flex-1 bg-[var(--wc-border-subtle)]" aria-hidden />
      </div>

      {product.personalization_options.map((option) => {
        const value = values[option.key] ?? ''
        const perChar = option.surcharge_per_char.paisa
        const cost =
          value.trim().length > 0
            ? option.surcharge.paisa + perChar * value.trim().length
            : 0

        return (
          <Field
            key={option.id}
            label={option.label}
            required={option.is_required}
            hint={
              option.help_text
                ? `${option.help_text}${
                    perChar > 0 ? ` ${formatPkr(option.surcharge.paisa)} plus ${formatPkr(perChar)} per character.` : ''
                  }`
                : undefined
            }
          >
            {option.input_type === 'dimensions' ? (
              <DimensionPicker
                value={value}
                defaultDims={
                  product.dimensions ? formatDimensions(product.dimensions) : null
                }
                onChange={(next) => onChange(option.key, next)}
              />
            ) : (
              <Input
                placeholder={
                  option.input_type === 'monogram' ? 'AK' : 'For Ayesha, 2026'
                }
                value={value}
                maxLength={option.max_length ?? 60}
                onChange={(event) =>
                  onChange(
                    option.key,
                    option.input_type === 'monogram'
                      ? event.target.value.toUpperCase()
                      : event.target.value,
                  )
                }
              />
            )}
            {cost > 0 && (
              <p className="mt-1 text-xs text-[var(--wc-brass-text)] tabular-nums">
                Adds {formatPkr(cost)}
              </p>
            )}
          </Field>
        )
      })}
    </div>
  )
}

export function ProductPage() {
  const { slug } = useParams()
  if (!slug) return <Navigate to="/shop" replace />
  // Key the body on the slug so navigating between products (for example from
  // "you may also like") remounts it and resets the option, quantity and
  // personalization state, instead of carrying the previous product's over.
  return <ProductBody key={slug} slug={slug} />
}

function ProductBody({ slug }: { slug: string }) {
  const [selected, setSelected] = useState<Record<string, string>>({})
  const [quantity, setQuantity] = useState(1)
  const [personalization, setPersonalization] = useState<Record<string, string>>({})

  const addToCart = useCartStore((state) => state.add)
  const wishlisted = useWishlistStore((state) => state.slugs.includes(slug))
  const toggleWishlist = useWishlistStore((state) => state.toggle)

  const { data: product, isLoading, isError } = useQuery({
    queryKey: ['product', slug],
    queryFn: () => get<ProductDetail>(`/products/${slug}`),
    enabled: Boolean(slug),
  })

  useDocumentTitle(product ? `Woodcroft ${product.name}` : 'Woodcroft')

  const { data: related } = useQuery({
    queryKey: ['related', slug],
    queryFn: () => get<Card[]>(`/products/${slug}/related`),
    enabled: Boolean(slug),
  })

  const { data: ratings } = useQuery({
    queryKey: ['rating', slug],
    queryFn: () => get<RatingBreakdown>(`/products/${slug}/rating`),
    enabled: Boolean(slug),
  })

  /* One value must be chosen for every option type before a concrete variant is
     resolved. A product with no option types has a single variant, which is
     always complete. */
  const optionTypes = product?.option_types ?? []
  const complete =
    optionTypes.length === 0 || optionTypes.every((t) => selected[t.id])

  /* Resolve the chosen values to a single variant, only once the selection is
     complete, so the picker never silently prices an option the customer did
     not choose. */
  const variant: Variant | undefined = useMemo(() => {
    if (!product) return undefined
    if (optionTypes.length === 0) return product.variants[0]
    if (!optionTypes.every((t) => selected[t.id])) return undefined
    const chosen = Object.values(selected)
    return product.variants.find((v) =>
      chosen.every((valueId) => v.option_value_ids.includes(valueId)),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [product, selected])

  // Clamp the quantity down when the chosen variant has less stock than the
  // number currently in the stepper, so a new line never exceeds availability.
  useEffect(() => {
    const max = Math.max(1, variant?.stock.available || 99)
    setQuantity((q) => Math.min(q, max))
  }, [variant])

  const personalizationLines: PersonalizationValue[] = useMemo(() => {
    if (!product) return []
    return product.personalization_options
      .filter((option) => (personalization[option.key] ?? '').trim().length > 0)
      .map((option) => {
        const value = personalization[option.key]!.trim()
        return {
          key: option.key,
          label: option.label,
          value,
          surchargePaisa:
            option.surcharge.paisa + option.surcharge_per_char.paisa * value.length,
        }
      })
  }, [product, personalization])

  const personalizationTotal = personalizationLines.reduce(
    (sum, entry) => sum + entry.surchargePaisa,
    0,
  )

  const missingRequired =
    product?.personalization_options.filter(
      (option) => option.is_required && !(personalization[option.key] ?? '').trim(),
    ) ?? []

  // A 404 or API error must not sit on the skeleton forever. Retries are off for
  // 4xx, so the query settles with no product; show a real empty state instead.
  if (isError || (!isLoading && !product)) {
    return (
      <div className="wc-container py-16">
        <EmptyState
          title="We could not find that piece"
          description="It may have been sold or moved. Browse the full collection instead."
          action={
            <Link to="/shop" className="wc-btn wc-btn-primary">
              Back to shop
            </Link>
          }
        />
      </div>
    )
  }

  if (isLoading || !product) {
    return (
      <div className="wc-container grid gap-12 py-10 lg:grid-cols-2">
        <Skeleton className="aspect-4/5 w-full" />
        <div className="space-y-4">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-10 w-3/4" />
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-24 w-full" />
        </div>
      </div>
    )
  }

  const unitPrice = variant?.price.paisa ?? product.price.paisa
  const totalPrice = (unitPrice + personalizationTotal) * quantity

  const handleAdd = () => {
    if (!variant) {
      toast.error('Please choose an option first')
      return
    }
    if (missingRequired.length > 0) {
      toast.error(`${missingRequired[0]!.label} is required`)
      return
    }
    addToCart({
      productId: product.id,
      productSlug: product.slug,
      productName: product.name,
      variantId: variant.id,
      variantName: variant.name,
      sku: variant.sku,
      imageUrl: product.primary_image?.thumb_url ?? null,
      unitPricePaisa: variant.price.paisa,
      comparePricePaisa: variant.compare_at_price?.paisa ?? null,
      quantity,
      maxQuantity: Math.max(1, variant.stock.available || 99),
      personalization: personalizationLines,
    })
    toast.success(`${product.name} added to your cart`)
  }

  const categoryCrumbs = product.category_path
    .split('/')
    .filter(Boolean)
    .map((segment, index, all) => ({
      label: segment.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
      to: index === all.length - 1 ? undefined : `/collections/${segment}`,
    }))

  return (
    <div className="wc-container py-10">
      <Breadcrumbs
        items={[{ label: 'Home', to: '/' }, ...categoryCrumbs, { label: product.name }]}
      />

      <div className="mt-8 grid gap-12 lg:grid-cols-2 lg:gap-16">
        <div className="lg:sticky lg:top-28 lg:self-start">
          <Gallery product={product} />
        </div>

        <div>
          {product.wood_species_label && (
            <p className="wc-eyebrow mb-3">{product.wood_species_label}</p>
          )}

          <h1 className="text-4xl leading-tight">{product.name}</h1>
          {product.subtitle && (
            <p className="mt-2 text-base text-muted">{product.subtitle}</p>
          )}

          {product.rating_count > 0 && (
            <div className="mt-4">
              <Rating value={product.rating_average} count={product.rating_count} />
            </div>
          )}

          <div className="mt-6">
            <Price
              value={unitPrice}
              compareAt={variant?.compare_at_price ?? product.compare_at_price}
              size="lg"
            />
            <p className="mt-1 text-xs text-faint">Price includes GST</p>
          </div>

          {product.option_types.map((optionType) => (
            <div key={optionType.id} className="mt-7">
              <div className="mb-2.5 flex items-baseline justify-between">
                <span className="wc-eyebrow">{optionType.name}</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {optionType.values.map((value) => {
                  const isActive = selected[optionType.id] === value.id
                  return (
                    <button
                      key={value.id}
                      onClick={() =>
                        setSelected((current) => ({ ...current, [optionType.id]: value.id }))
                      }
                      disabled={!value.available}
                      aria-pressed={isActive}
                      className={cn(
                        'flex items-center gap-2 border px-3.5 py-2 text-sm transition-colors',
                        isActive
                          ? 'border-[var(--wc-border-strong)] bg-sunken'
                          : 'border-control hover:border-[var(--wc-border-strong)]',
                        !value.available && 'cursor-not-allowed opacity-40 line-through',
                      )}
                    >
                      {value.swatch && (
                        <span
                          className="size-3.5 rounded-full border border-[var(--wc-border-subtle)]"
                          style={{ background: value.swatch }}
                          aria-hidden
                        />
                      )}
                      {value.value}
                      {isActive && <Check size={12} strokeWidth={2.5} />}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}

          {variant && (
            <div className="mt-5 flex items-center gap-2 text-sm">
              {variant.stock.is_preorder ? (
                <Badge tone="info">Pre-order</Badge>
              ) : variant.stock.is_in_stock ? (
                variant.stock.is_low ? (
                  <Badge tone="low">{variant.stock.remaining_label}</Badge>
                ) : (
                  <span className="flex items-center gap-1.5 text-[var(--wc-success)]">
                    <Check size={14} strokeWidth={2} /> In stock
                  </span>
                )
              ) : (
                <Badge tone="out">Out of stock</Badge>
              )}
              <span className="font-mono text-xs text-faint">{variant.sku}</span>
            </div>
          )}

          {product.personalization_options.length > 0 && (
            <div className="mt-7">
              <PersonalizationFields
                product={product}
                values={personalization}
                onChange={(key, value) =>
                  setPersonalization((current) => ({ ...current, [key]: value }))
                }
              />
            </div>
          )}

          <div className="mt-7 flex flex-wrap items-center gap-3">
            <QuantityStepper
              value={quantity}
              onChange={setQuantity}
              max={Math.max(1, variant?.stock.available || 99)}
            />
            <Button
              size="lg"
              onClick={handleAdd}
              disabled={!complete || !variant?.stock.is_in_stock}
              className="flex-1 min-w-[12rem]"
            >
              {!complete
                ? `Choose ${optionTypes.find((t) => !selected[t.id])?.name ?? 'an option'}`
                : variant?.stock.is_in_stock
                  ? 'Add to cart'
                  : 'Out of stock'}
            </Button>
            <button
              onClick={() => toggleWishlist(product.slug, product.id)}
              aria-label={wishlisted ? 'Remove from wishlist' : 'Save to wishlist'}
              aria-pressed={wishlisted}
              className="flex size-11 items-center justify-center border border-control transition-colors hover:border-[var(--wc-border-strong)]"
            >
              <Heart
                size={17}
                strokeWidth={1.5}
                className={wishlisted ? 'fill-[var(--wc-danger)] text-[var(--wc-danger)]' : ''}
              />
            </button>
          </div>

          {personalizationTotal > 0 && (
            <p className="mt-3 text-sm tabular-nums">
              <span className="text-muted">Total: </span>
              <strong>{formatPkr(totalPrice)}</strong>
              <span className="text-faint"> including personalisation</span>
            </p>
          )}

          <div className="mt-6 flex items-start gap-2.5 border-t border-line pt-6 text-xs text-muted">
            <Truck size={16} strokeWidth={1.25} className="mt-0.5 shrink-0 text-[var(--wc-brass)]" />
            <p>
              Free delivery on orders over Rs 20,000. Cash on delivery available
              across most of Pakistan. Usually dispatched within 3 working days.
            </p>
          </div>

          <div className="mt-8">
            {product.description && (
              <Accordion title="Description" defaultOpen>
                <p className="whitespace-pre-line">{product.description}</p>
                {product.story && (
                  <p className="mt-4 border-l-2 border-[var(--wc-brass)] pl-4 italic">
                    {product.story}
                  </p>
                )}
              </Accordion>
            )}

            {(product.dimensions || product.weight_g ||
              Object.keys(product.specifications).length > 0) && (
              <Accordion title="Specifications">
                <dl className="space-y-2">
                  {product.dimensions && (
                    <div className="flex justify-between gap-4 border-b border-line pb-2">
                      <dt className="text-faint">Dimensions</dt>
                      <dd className="text-right">{formatDimensions(product.dimensions)}</dd>
                    </div>
                  )}
                  {product.weight_g && (
                    <div className="flex justify-between gap-4 border-b border-line pb-2">
                      <dt className="text-faint">Weight</dt>
                      <dd className="text-right">{formatWeight(product.weight_g)}</dd>
                    </div>
                  )}
                  {Object.entries(product.specifications).map(([key, value]) => (
                    <div key={key} className="flex justify-between gap-4 border-b border-line pb-2">
                      <dt className="text-faint">{key}</dt>
                      <dd className="text-right">{String(value)}</dd>
                    </div>
                  ))}
                </dl>
              </Accordion>
            )}

            {product.care_instructions && (
              <Accordion title="Care">
                <p className="whitespace-pre-line">{product.care_instructions}</p>
              </Accordion>
            )}

            {product.assets.length > 0 && (
              <Accordion title="Downloads">
                <ul className="space-y-2">
                  {product.assets.map((asset) => (
                    <li key={asset.id}>
                      <a href={asset.url} className="flex items-center gap-2 hover:text-ink">
                        <FileDown size={14} strokeWidth={1.5} />
                        {asset.title}
                      </a>
                    </li>
                  ))}
                </ul>
              </Accordion>
            )}

            <Accordion title="Delivery and returns">
              <p>
                Delivered across Pakistan. Sindh usually takes three to five
                working days, Punjab and Islamabad five to seven, and the far
                north up to ten.
              </p>
              <p className="mt-2">
                Returns accepted within 14 days of delivery, provided the piece
                is unused and in its original condition. Bespoke pieces cannot
                be returned.
              </p>
            </Accordion>
          </div>
        </div>
      </div>

      {ratings && ratings.total > 0 && (
        <section className="wc-section border-t border-line">
          <SectionHeading numeral="06" title="What customers say" />
          <div className="grid gap-10 md:grid-cols-[16rem_1fr]">
            <div>
              <div className="font-display text-5xl">{Number(ratings.average).toFixed(1)}</div>
              <Rating value={ratings.average} count={ratings.total} size={16} />
              <div className="mt-5 space-y-1.5">
                {[5, 4, 3, 2, 1].map((star) => {
                  const count = ratings.counts[String(star)] ?? 0
                  const percent = ratings.total ? (count / ratings.total) * 100 : 0
                  return (
                    <div key={star} className="flex items-center gap-2 text-xs">
                      <span className="w-3 tabular-nums text-faint">{star}</span>
                      <div className="h-1.5 flex-1 overflow-hidden bg-sunken">
                        <div
                          className="h-full bg-[var(--wc-brass)]"
                          style={{ width: `${percent}%` }}
                        />
                      </div>
                      <span className="w-6 text-right tabular-nums text-faint">{count}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </section>
      )}

      <section className="wc-section border-t border-line">
        <SectionHeading numeral="07" title="Reviews and questions" />
        <ProductEngagement slug={product.slug} reviewCount={product.rating_count} />
      </section>

      {related && related.length > 0 && (
        <section className="wc-section border-t border-line">
          <SectionHeading numeral="08" title="You may also like" />
          <ProductGrid products={related.slice(0, 4)} />
        </section>
      )}
    </div>
  )
}

export default ProductPage
