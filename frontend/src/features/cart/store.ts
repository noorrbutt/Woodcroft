/**
 * Cart state.
 *
 * The cart is held locally and mirrored to the server. Local-first is the right
 * shape here: adding to a cart must feel instant and must work before anyone
 * has signed in, and the server copy exists so the cart survives a change of
 * device and so an abandoned cart can be recovered.
 *
 * Prices in this store are a CACHE for rendering only. Checkout re-prices the
 * whole basket server-side through the pricing engine, so a stale price here
 * can never become a stale price charged.
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import { auth, del, post } from '@/lib/api'
import { queryClient } from '@/lib/queryClient'

export interface PersonalizationValue {
  key: string
  label: string
  value: string
  surchargePaisa: number
}

export interface CartLine {
  /** Stable identity for the line: variant plus personalization. */
  lineId: string
  productId: string
  productSlug: string
  productName: string
  variantId: string
  variantName: string | null
  sku: string
  imageUrl: string | null
  unitPricePaisa: number
  comparePricePaisa: number | null
  quantity: number
  maxQuantity: number
  personalization: PersonalizationValue[]
}

interface CartState {
  lines: CartLine[]
  giftWrap: boolean
  giftMessage: string
  couponCode: string | null
  giftCardCode: string | null

  add: (line: Omit<CartLine, 'lineId'>) => void
  updateQuantity: (lineId: string, quantity: number) => void
  remove: (lineId: string) => void
  clear: () => void
  setGiftWrap: (value: boolean) => void
  setGiftMessage: (value: string) => void
  setCoupon: (code: string | null) => void
  setGiftCard: (code: string | null) => void

  itemCount: () => number
  subtotalPaisa: () => number
  personalizationPaisa: () => number
}

/**
 * Two units of the same variant engraved differently are not the same line.
 * Hashing the personalization into the id is what keeps them separate instead
 * of silently merging into quantity 2 with one engraving.
 */
function makeLineId(variantId: string, personalization: PersonalizationValue[]): string {
  if (personalization.length === 0) return variantId
  const signature = personalization
    .map((entry) => `${entry.key}=${entry.value}`)
    .sort()
    .join('|')
  return `${variantId}::${signature}`
}

export function linePersonalizationPaisa(line: CartLine): number {
  return line.personalization.reduce((sum, entry) => sum + entry.surchargePaisa, 0)
}

export function lineTotalPaisa(line: CartLine): number {
  return (line.unitPricePaisa + linePersonalizationPaisa(line)) * line.quantity
}

export const useCartStore = create<CartState>()(
  persist(
    (set, get) => ({
      lines: [],
      giftWrap: false,
      giftMessage: '',
      couponCode: null,
      giftCardCode: null,

      add: (incoming) => {
        const lineId = makeLineId(incoming.variantId, incoming.personalization)
        set((state) => {
          const existing = state.lines.find((line) => line.lineId === lineId)
          if (existing) {
            return {
              lines: state.lines.map((line) =>
                line.lineId === lineId
                  ? {
                      ...line,
                      quantity: Math.min(
                        line.maxQuantity || 99,
                        line.quantity + incoming.quantity,
                      ),
                    }
                  : line,
              ),
            }
          }
          return {
            lines: [
              ...state.lines,
              {
                ...incoming,
                lineId,
                // Clamp a brand-new line too, not just merges, so switching to a
                // low-stock variant cannot add more than is available.
                quantity: Math.min(incoming.maxQuantity || 99, incoming.quantity),
              },
            ],
          }
        })
      },

      updateQuantity: (lineId, quantity) =>
        set((state) => ({
          lines:
            quantity <= 0
              ? state.lines.filter((line) => line.lineId !== lineId)
              : state.lines.map((line) =>
                  line.lineId === lineId
                    ? { ...line, quantity: Math.min(line.maxQuantity || 99, quantity) }
                    : line,
                ),
        })),

      remove: (lineId) =>
        set((state) => ({ lines: state.lines.filter((line) => line.lineId !== lineId) })),

      clear: () => set({ lines: [], giftWrap: false, giftMessage: '', couponCode: null, giftCardCode: null }),

      setGiftWrap: (giftWrap) => set({ giftWrap }),
      setGiftMessage: (giftMessage) => set({ giftMessage }),
      setCoupon: (couponCode) => set({ couponCode }),
      setGiftCard: (giftCardCode) => set({ giftCardCode }),

      itemCount: () => get().lines.reduce((sum, line) => sum + line.quantity, 0),
      subtotalPaisa: () => get().lines.reduce((sum, line) => sum + lineTotalPaisa(line), 0),
      personalizationPaisa: () =>
        get().lines.reduce(
          (sum, line) => sum + linePersonalizationPaisa(line) * line.quantity,
          0,
        ),
    }),
    {
      name: 'wc-cart',
      version: 1,
      // Derived values are recomputed, never restored.
      partialize: (state) => ({
        lines: state.lines,
        giftWrap: state.giftWrap,
        giftMessage: state.giftMessage,
        couponCode: state.couponCode,
        giftCardCode: state.giftCardCode,
      }),
    },
  ),
)

/** Wishlist, same local-first shape. */
interface WishlistState {
  slugs: string[]
  /** Toggle a product. Pass the id so the change can reach the server. */
  toggle: (slug: string, productId?: string) => void
  has: (slug: string) => boolean
  remove: (slug: string, productId?: string) => void
  clear: () => void
  /** Replace the local set from the server list after sign-in. */
  hydrate: (slugs: string[]) => void
}

export const useWishlistStore = create<WishlistState>()(
  persist(
    (set, get) => ({
      slugs: [],
      toggle: (slug, productId) => {
        const adding = !get().slugs.includes(slug)
        set((state) => ({
          slugs: adding
            ? [...state.slugs, slug]
            : state.slugs.filter((entry) => entry !== slug),
        }))
        // Persist to the server for signed-in shoppers, then refresh the account
        // wishlist query. Guests keep a local-only list until they sign in.
        if (productId && auth.isAuthenticated) {
          const call = adding
            ? post(`/wishlist/${productId}`)
            : del(`/wishlist/${productId}`)
          call
            .then(() => queryClient.invalidateQueries({ queryKey: ['wishlist'] }))
            .catch(() => {
              // Roll the heart back if the server rejected the change.
              set((state) => ({
                slugs: adding
                  ? state.slugs.filter((entry) => entry !== slug)
                  : [...state.slugs, slug],
              }))
            })
        }
      },
      has: (slug) => get().slugs.includes(slug),
      remove: (slug, productId) => {
        set((state) => ({ slugs: state.slugs.filter((entry) => entry !== slug) }))
        if (productId && auth.isAuthenticated) {
          del(`/wishlist/${productId}`)
            .then(() => queryClient.invalidateQueries({ queryKey: ['wishlist'] }))
            .catch(() => undefined)
        }
      },
      clear: () => set({ slugs: [] }),
      hydrate: (slugs) => set({ slugs }),
    }),
    { name: 'wc-wishlist', version: 1 },
  ),
)

/** Recently compared products, capped so the bar cannot grow unbounded. */
interface CompareState {
  slugs: string[]
  toggle: (slug: string) => void
  clear: () => void
}

export const useCompareStore = create<CompareState>()(
  persist(
    (set) => ({
      slugs: [],
      toggle: (slug) =>
        set((state) => {
          if (state.slugs.includes(slug)) {
            return { slugs: state.slugs.filter((entry) => entry !== slug) }
          }
          // Four is the most a comparison table can show without scrolling
          // horizontally on a laptop, so the oldest drops off.
          return { slugs: [...state.slugs, slug].slice(-4) }
        }),
      clear: () => set({ slugs: [] }),
    }),
    { name: 'wc-compare', version: 1 },
  ),
)
