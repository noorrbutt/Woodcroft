import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { SlidersHorizontal, X } from 'lucide-react'

import { get } from '@/lib/api'
import { cn } from '@/lib/cn'
import { formatPkr } from '@/lib/format'
import {
  Badge,
  Breadcrumbs,
  Button,
  Checkbox,
  EmptyState,
  Pagination,
  Select,
} from '@/components/ui'
import { ProductGrid } from '@/features/catalog/ProductCard'
import { SORT_OPTIONS, type Category, type ProductList } from '@/lib/types'

/**
 * Product listing, also used for search and for a single collection.
 *
 * Every filter lives in the URL. That means a filtered view is shareable and
 * bookmarkable, the back button behaves, and the server can render the same
 * state later if this ever needs SSR.
 */

const PRICE_BANDS: { label: string; min?: number; max?: number }[] = [
  { label: 'Under Rs 10,000', max: 1_000_000 },
  { label: 'Rs 10,000 – 50,000', min: 1_000_000, max: 5_000_000 },
  { label: 'Rs 50,000 – 150,000', min: 5_000_000, max: 15_000_000 },
  { label: 'Over Rs 150,000', min: 15_000_000 },
]

function FilterPanel({
  facets,
  params,
  setParams,
}: {
  facets: ProductList['facets'] | undefined
  params: URLSearchParams
  setParams: (next: URLSearchParams) => void
}) {
  const update = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params)
    mutate(next)
    next.delete('page') // a new filter always returns to page one
    setParams(next)
  }

  const toggleMulti = (key: string, value: string) => {
    update((next) => {
      const current = next.getAll(key)
      next.delete(key)
      const remaining = current.includes(value)
        ? current.filter((entry) => entry !== value)
        : [...current, value]
      remaining.forEach((entry) => next.append(key, entry))
    })
  }

  const activeWoods = params.getAll('wood')
  const activeTags = params.getAll('tag')

  return (
    <div className="space-y-8">
      <div>
        <h3 className="wc-eyebrow mb-3">Availability</h3>
        <div className="space-y-2">
          <Checkbox
            label="In stock only"
            checked={params.get('in_stock') === 'true'}
            onChange={(event) =>
              update((next) =>
                event.target.checked ? next.set('in_stock', 'true') : next.delete('in_stock'),
              )
            }
          />
          <Checkbox
            label="On sale"
            checked={params.get('on_sale') === 'true'}
            onChange={(event) =>
              update((next) =>
                event.target.checked ? next.set('on_sale', 'true') : next.delete('on_sale'),
              )
            }
          />
        </div>
      </div>

      <div>
        <h3 className="wc-eyebrow mb-3">Price</h3>
        <div className="space-y-2">
          {PRICE_BANDS.map((band) => {
            const active =
              params.get('min_price') === String(band.min ?? '') &&
              params.get('max_price') === String(band.max ?? '')
            return (
              <Checkbox
                key={band.label}
                label={band.label}
                checked={active}
                onChange={(event) =>
                  update((next) => {
                    next.delete('min_price')
                    next.delete('max_price')
                    if (event.target.checked) {
                      if (band.min) next.set('min_price', String(band.min))
                      if (band.max) next.set('max_price', String(band.max))
                    }
                  })
                }
              />
            )
          })}
        </div>
      </div>

      {facets && facets.wood_species.length > 0 && (
        <div>
          <h3 className="wc-eyebrow mb-3">Timber</h3>
          <div className="space-y-2">
            {facets.wood_species.map((facet) => (
              <Checkbox
                key={facet.value}
                checked={activeWoods.includes(facet.value)}
                onChange={() => toggleMulti('wood', facet.value)}
                label={
                  <span className="flex w-full items-center justify-between gap-2">
                    <span>{facet.label.split(' (')[0]}</span>
                    <span className="text-xs text-faint tabular-nums">{facet.count}</span>
                  </span>
                }
              />
            ))}
          </div>
        </div>
      )}

      {facets && facets.tags.length > 0 && (
        <div>
          <h3 className="wc-eyebrow mb-3">Character</h3>
          <div className="space-y-2">
            {facets.tags.map((facet) => (
              <Checkbox
                key={facet.value}
                checked={activeTags.includes(facet.value)}
                onChange={() => toggleMulti('tag', facet.value)}
                label={
                  <span className="flex w-full items-center justify-between gap-2">
                    <span>{facet.label}</span>
                    <span className="text-xs text-faint tabular-nums">{facet.count}</span>
                  </span>
                }
              />
            ))}
          </div>
        </div>
      )}

      <div>
        <h3 className="wc-eyebrow mb-3">Rating</h3>
        <div className="space-y-2">
          {[4, 3].map((rating) => (
            <Checkbox
              key={rating}
              label={`${rating} stars and up`}
              checked={params.get('min_rating') === String(rating)}
              onChange={(event) =>
                update((next) =>
                  event.target.checked
                    ? next.set('min_rating', String(rating))
                    : next.delete('min_rating'),
                )
              }
            />
          ))}
        </div>
      </div>
    </div>
  )
}

export function ShopPage() {
  const { slug } = useParams()
  const [params, setParams] = useSearchParams()
  const [filtersOpen, setFiltersOpen] = useState(false)

  const query = params.get('q') ?? undefined
  const page = Number(params.get('page') ?? 1)
  const sort = params.get('sort') ?? (query ? 'relevance' : 'newest')

  const { data: category } = useQuery({
    queryKey: ['category', slug],
    queryFn: () => get<Category>(`/categories/${slug}`),
    enabled: Boolean(slug),
  })

  const requestParams = {
    q: query,
    category: slug,
    wood: params.getAll('wood'),
    tag: params.getAll('tag'),
    min_price: params.get('min_price') ?? undefined,
    max_price: params.get('max_price') ?? undefined,
    min_rating: params.get('min_rating') ?? undefined,
    in_stock: params.get('in_stock') === 'true',
    on_sale: params.get('on_sale') === 'true',
    new_arrivals: params.get('new_arrivals') === 'true',
    sort,
    page,
    per_page: 24,
  }

  const { data, isLoading } = useQuery({
    queryKey: ['products', requestParams],
    queryFn: () => get<ProductList>('/products', requestParams),
  })

  const activeFilterCount =
    params.getAll('wood').length +
    params.getAll('tag').length +
    (params.get('in_stock') ? 1 : 0) +
    (params.get('on_sale') ? 1 : 0) +
    (params.get('min_rating') ? 1 : 0) +
    (params.get('min_price') || params.get('max_price') ? 1 : 0)

  const heading = query
    ? `Results for “${query}”`
    : (category?.name ?? 'The collection')

  const makeHref = (target: number) => {
    const next = new URLSearchParams(params)
    next.set('page', String(target))
    return `?${next}`
  }

  return (
    <div className="wc-container py-10">
      <Breadcrumbs
        items={[
          { label: 'Home', to: '/' },
          ...(category ? [{ label: category.name }] : [{ label: query ? 'Search' : 'Shop' }]),
        ]}
      />

      <header className="mt-6 mb-10">
        <h1 className="text-4xl">{heading}</h1>
        {category?.description && (
          <p className="mt-3 max-w-xl text-sm text-muted">{category.description}</p>
        )}
        {data && (
          <p className="mt-3 text-xs text-faint tabular-nums">
            {data.total} {data.total === 1 ? 'piece' : 'pieces'}
            {data.facets.price_max_paisa > 0 && (
              <> · {formatPkr(data.facets.price_min_paisa)} to {formatPkr(data.facets.price_max_paisa)}</>
            )}
          </p>
        )}
      </header>

      <div className="flex gap-10">
        <aside className="hidden w-56 shrink-0 lg:block">
          <div className="sticky top-28">
            <FilterPanel facets={data?.facets} params={params} setParams={setParams} />
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <div className="mb-6 flex items-center justify-between gap-3 border-b border-line pb-4">
            <button
              onClick={() => setFiltersOpen(true)}
              className="wc-btn wc-btn-outline wc-btn-sm lg:hidden"
            >
              <SlidersHorizontal size={13} strokeWidth={1.5} />
              Filters
              {activeFilterCount > 0 && (
                <span className="ml-1 rounded-full bg-[var(--wc-brass)] px-1.5 text-[0.6rem] text-[var(--walnut-900)]">
                  {activeFilterCount}
                </span>
              )}
            </button>

            <div className="hidden flex-wrap items-center gap-2 lg:flex">
              {activeFilterCount > 0 && (
                <>
                  {params.getAll('wood').map((wood) => (
                    <button
                      key={wood}
                      onClick={() => {
                        const next = new URLSearchParams(params)
                        const remaining = next.getAll('wood').filter((w) => w !== wood)
                        next.delete('wood')
                        remaining.forEach((w) => next.append('wood', w))
                        setParams(next)
                      }}
                      className="wc-badge bg-sunken text-muted hover:text-ink"
                    >
                      {wood} <X size={10} />
                    </button>
                  ))}
                  <Link to={slug ? `/collections/${slug}` : '/shop'} className="text-xs text-muted hover:text-ink">
                    Clear all
                  </Link>
                </>
              )}
            </div>

            <label className="ml-auto flex items-center gap-2 text-xs text-muted">
              Sort
              <Select
                value={sort}
                onChange={(event) => {
                  const next = new URLSearchParams(params)
                  next.set('sort', event.target.value)
                  next.delete('page')
                  setParams(next)
                }}
                className="w-auto py-1.5 text-xs"
              >
                {SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </label>
          </div>

          {!isLoading && data?.total === 0 ? (
            <EmptyState
              title="Nothing matched"
              description={
                data.did_you_mean
                  ? undefined
                  : 'Try removing a filter, or search for something broader.'
              }
              action={
                data.did_you_mean ? (
                  <div className="text-sm">
                    <span className="text-muted">Did you mean </span>
                    <Link
                      to={`/search?q=${encodeURIComponent(data.did_you_mean)}`}
                      className="wc-link font-medium"
                    >
                      {data.did_you_mean}
                    </Link>
                    ?
                  </div>
                ) : (
                  <Link to="/shop" className="wc-btn wc-btn-outline">
                    Browse everything
                  </Link>
                )
              }
            />
          ) : (
            <>
              <ProductGrid products={data?.items} loading={isLoading} skeletonCount={12} />
              {data && <Pagination page={data.page} pages={data.pages} makeHref={makeHref} />}
            </>
          )}
        </div>
      </div>

      {filtersOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            className="absolute inset-0 bg-[var(--wc-scrim)]"
            onClick={() => setFiltersOpen(false)}
            aria-label="Close filters"
            tabIndex={-1}
          />
          <div className="absolute bottom-0 left-0 right-0 max-h-[80vh] overflow-y-auto bg-surface p-5">
            <div className="mb-5 flex items-center justify-between">
              <h2 className="font-display text-lg">Filters</h2>
              <button onClick={() => setFiltersOpen(false)} aria-label="Close">
                <X size={18} strokeWidth={1.5} />
              </button>
            </div>
            <FilterPanel facets={data?.facets} params={params} setParams={setParams} />
            <Button fullWidth className="mt-6" onClick={() => setFiltersOpen(false)}>
              Show {data?.total ?? 0} results
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

export default ShopPage
