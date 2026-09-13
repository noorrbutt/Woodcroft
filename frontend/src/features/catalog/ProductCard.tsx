import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Heart } from 'lucide-react'

import { cn } from '@/lib/cn'
import { Badge, Price, Rating, Skeleton } from '@/components/ui'
import { useWishlistStore } from '@/features/cart/store'
import type { ProductCard as Product } from '@/lib/types'

/**
 * Product card.
 *
 * Deliberately has no border and no background at rest: the surface and its
 * warm shadow fade in on hover only. A bordered box around every card in a
 * grid is the single most recognisable "generic template" tell, and removing
 * it is the cheapest upgrade in the whole design.
 *
 * The title is Inter, not Fraunces. A display serif at 15px repeated two dozen
 * times down a grid turns into visual noise, and it is exactly how a serif
 * brand ends up looking cheap.
 */
export function ProductCard({
  product,
  eager = false,
}: {
  product: Product
  eager?: boolean
}) {
  const [loaded, setLoaded] = useState(false)
  const wishlisted = useWishlistStore((state) => state.slugs.includes(product.slug))
  const toggleWishlist = useWishlistStore((state) => state.toggle)

  const image = product.primary_image

  return (
    <article className="group relative">
      <Link to={`/product/${product.slug}`} className="block">
        <div
          className="relative overflow-hidden bg-sunken transition-shadow duration-300
                     group-hover:shadow-lg"
          style={{ aspectRatio: '4 / 5' }}
        >
          {/* The blurred placeholder means a card never flashes empty while
              its image arrives. */}
          {image?.blur_data_url && !loaded && (
            <img
              src={image.blur_data_url}
              alt=""
              aria-hidden
              className="absolute inset-0 size-full scale-110 object-cover blur-xl"
            />
          )}

          {image ? (
            <img
              src={image.url}
              srcSet={image.srcset}
              sizes="(min-width: 1280px) 22vw, (min-width: 768px) 30vw, 45vw"
              alt={image.alt_text || product.name}
              loading={eager ? 'eager' : 'lazy'}
              fetchPriority={eager ? 'high' : 'auto'}
              onLoad={() => setLoaded(true)}
              className={cn(
                'size-full object-cover transition-[opacity,transform] duration-700 ease-[var(--ease-wc-out)]',
                'group-hover:scale-[1.035]',
                loaded ? 'opacity-100' : 'opacity-0',
              )}
            />
          ) : (
            <div className="size-full bg-sunken" />
          )}

          <div className="absolute left-2.5 top-2.5 flex flex-col items-start gap-1.5">
            {product.discount_percent != null && (
              <Badge tone="sale">−{product.discount_percent}%</Badge>
            )}
            {product.is_new_arrival && !product.discount_percent && (
              <Badge tone="new">New</Badge>
            )}
            {!product.is_in_stock && <Badge tone="out">Sold out</Badge>}
          </div>

          <button
            onClick={(event) => {
              event.preventDefault()
              toggleWishlist(product.slug)
            }}
            aria-label={wishlisted ? 'Remove from wishlist' : 'Save to wishlist'}
            aria-pressed={wishlisted}
            className="absolute right-2.5 top-2.5 flex size-8 items-center justify-center
                       rounded-full bg-[var(--wc-surface)]/85 text-muted backdrop-blur-sm
                       opacity-0 transition-all duration-200 hover:text-[var(--wc-danger)]
                       group-hover:opacity-100 focus-visible:opacity-100"
          >
            <Heart
              size={15}
              strokeWidth={1.5}
              className={wishlisted ? 'fill-[var(--wc-danger)] text-[var(--wc-danger)]' : ''}
            />
          </button>
        </div>

        <div className="pt-3.5">
          {product.wood_species_label && (
            <p className="wc-eyebrow mb-1.5 text-[0.65rem]">
              {product.wood_species_label.split(' (')[0]}
            </p>
          )}
          <h3 className="font-sans text-[0.9375rem] font-medium leading-snug">
            {product.name}
          </h3>
          {product.subtitle && (
            <p className="mt-0.5 line-clamp-1 text-xs text-muted">{product.subtitle}</p>
          )}

          <div className="mt-2 flex items-center justify-between gap-2">
            <Price value={product.price} compareAt={product.compare_at_price} size="sm" />
            {product.rating_count > 0 && (
              <Rating value={product.rating_average} count={product.rating_count} size={11} />
            )}
          </div>
        </div>
      </Link>
    </article>
  )
}

export function ProductCardSkeleton() {
  return (
    <div>
      <Skeleton className="w-full" style={{ aspectRatio: '4 / 5' }} />
      <div className="space-y-2 pt-3.5">
        <Skeleton className="h-2.5 w-16" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="h-4 w-24" />
      </div>
    </div>
  )
}

export function ProductGrid({
  products,
  loading,
  skeletonCount = 8,
}: {
  products?: Product[]
  loading?: boolean
  skeletonCount?: number
}) {
  return (
    <div className="grid grid-cols-2 gap-x-5 gap-y-10 md:grid-cols-3 xl:grid-cols-4">
      {loading
        ? Array.from({ length: skeletonCount }, (_, index) => (
            <ProductCardSkeleton key={index} />
          ))
        : products?.map((product, index) => (
            <ProductCard key={product.id} product={product} eager={index < 4} />
          ))}
    </div>
  )
}
