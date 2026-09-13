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

  add: (line: Omit<CartLine, 'lineId'>) => void
  updateQuantity: (lineId: string, quantity: number) => void
  remove: (lineId: string) => void
  clear: () => void
  setGiftWrap: (value: boolean) => void
  setGiftMessage: (value: string) => void
  setCoupon: (code: string | null) => void

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
          return { lines: [...state.lines, { ...incoming, lineId }] }
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

      clear: () => set({ lines: [], giftWrap: false, giftMessage: '', couponCode: null }),

      setGiftWrap: (giftWrap) => set({ giftWrap }),
      setGiftMessage: (giftMessage) => set({ giftMessage }),
      setCoupon: (couponCode) => set({ couponCode }),

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
      }),
    },
  ),
)

/** Wishlist, same local-first shape. */
interface WishlistState {
  slugs: string[]
  toggle: (slug: string) => void
  has: (slug: string) => boolean
  remove: (slug: string) => void
  clear: () => void
}

export const useWishlistStore = create<WishlistState>()(
  persist(
    (set, get) => ({
      slugs: [],
      toggle: (slug) =>
        set((state) => ({
          slugs: state.slugs.includes(slug)
            ? state.slugs.filter((entry) => entry !== slug)
            : [...state.slugs, slug],
        })),
      has: (slug) => get().slugs.includes(slug),
      remove: (slug) =>
        set((state) => ({ slugs: state.slugs.filter((entry) => entry !== slug) })),
      clear: () => set({ slugs: [] }),
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
