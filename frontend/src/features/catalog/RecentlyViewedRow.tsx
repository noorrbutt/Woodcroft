import { ProductCard } from '@/features/catalog/ProductCard'
import { SectionHeading } from '@/components/ui'
import type { ProductCard as Product } from '@/lib/types'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface RecentlyViewedState {
  products: Product[]
  record: (product: Product) => void
}

export const useRecentlyViewedStore = create<RecentlyViewedState>()(
  persist(
    (set) => ({
      products: [],
      record: (product) =>
        set((state) => ({
          products: [
            {
              id: product.id,
              name: product.name,
              slug: product.slug,
              subtitle: product.subtitle,
              category_name: product.category_name,
              price: product.price,
              compare_at_price: product.compare_at_price,
              discount_percent: product.discount_percent,
              primary_image: product.primary_image,
              rating_average: product.rating_average,
              rating_count: product.rating_count,
              wood_species: product.wood_species,
              wood_species_label: product.wood_species_label,
              tags: product.tags,
              is_in_stock: product.is_in_stock,
              is_new_arrival: product.is_new_arrival,
              is_bestseller: product.is_bestseller,
            },
            ...state.products.filter((item) => item.id !== product.id),
          ].slice(0, 8),
        })),
    }),
    { name: 'wc-recent', version: 1 },
  ),
)

export function RecentlyViewedRow({ excludeId }: { excludeId?: string }) {
  const products = useRecentlyViewedStore((state) =>
    excludeId
      ? state.products.filter((product) => product.id !== excludeId)
      : state.products,
  )

  if (products.length < 2) return null

  return (
    <section className="wc-section border-t border-line">
      <div className="wc-container">
        <SectionHeading title="Recently viewed" />
        <div className="wc-scroll-x wc-no-scrollbar -mx-[var(--wc-gutter)] flex gap-5 px-[var(--wc-gutter)] [scroll-snap-type:x_mandatory]">
          {products.map((product) => (
            <div
              key={product.id}
              className="shrink-0 basis-[72%] [scroll-snap-align:start] sm:basis-[42%] lg:basis-[23%]"
            >
              <ProductCard product={product} />
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
