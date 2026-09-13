/** Shared API types. These mirror the Pydantic response models. */

export interface Money {
  paisa: number
  display: string
}

export interface Image {
  id: string
  url: string
  thumb_url: string
  srcset: string
  alt_text: string
  width: number
  height: number
  aspect: number
  blur_data_url: string | null
  is_primary: boolean
}

export interface Tag {
  name: string
  slug: string
  accent: string | null
}

export interface Category {
  id: string
  name: string
  slug: string
  path: string
  depth: number
  description: string | null
  image_url: string | null
  product_count: number
  children: Category[]
}

export interface Stock {
  available: number
  is_in_stock: boolean
  is_low: boolean
  remaining_label: string | null
  is_preorder: boolean
  preorder_available_at: string | null
}

export interface OptionValue {
  id: string
  value: string
  swatch: string | null
  available: boolean
}

export interface OptionType {
  id: string
  name: string
  values: OptionValue[]
}

export interface Variant {
  id: string
  sku: string
  name: string | null
  price: Money
  compare_at_price: Money | null
  option_value_ids: string[]
  stock: Stock
  is_active: boolean
}

export interface PersonalizationOption {
  id: string
  key: string
  label: string
  help_text: string | null
  input_type: 'text' | 'monogram' | 'select' | 'dimensions'
  is_required: boolean
  surcharge: Money
  surcharge_per_char: Money
  max_length: number | null
  constraints: Record<string, unknown>
}

export interface ProductCard {
  id: string
  name: string
  slug: string
  subtitle: string | null
  category_name: string | null
  price: Money
  compare_at_price: Money | null
  discount_percent: number | null
  primary_image: Image | null
  rating_average: string
  rating_count: number
  wood_species: string | null
  wood_species_label: string | null
  tags: Tag[]
  is_in_stock: boolean
  is_new_arrival: boolean
  is_bestseller: boolean
}

export interface ProductDetail extends ProductCard {
  description: string
  story: string | null
  care_instructions: string | null
  specifications: Record<string, string>
  dimensions: Record<string, number | null> | null
  weight_g: number | null
  images: Image[]
  option_types: OptionType[]
  variants: Variant[]
  personalization_options: PersonalizationOption[]
  assets: { id: string; title: string; kind: string; url: string; file_size_bytes: number | null }[]
  meta_title: string | null
  meta_description: string | null
  category_path: string
}

export interface FacetValue {
  value: string
  label: string
  count: number
}

export interface Facets {
  categories: FacetValue[]
  wood_species: FacetValue[]
  tags: FacetValue[]
  price_min_paisa: number
  price_max_paisa: number
}

export interface ProductList {
  items: ProductCard[]
  total: number
  page: number
  per_page: number
  pages: number
  facets: Facets
  did_you_mean: string | null
}

export interface SearchSuggestion {
  kind: 'product' | 'category' | 'term'
  label: string
  slug: string | null
  image_url: string | null
}

export interface RatingBreakdown {
  average: string
  total: number
  counts: Record<string, number>
}

export type Role = 'customer' | 'staff' | 'admin'

export interface User {
  id: string
  email: string
  full_name: string
  phone: string | null
  avatar_path: string | null
  role: Role
  is_email_verified: boolean
  referral_code: string | null
  store_credit_paisa: number
  created_at: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface AuthResponse {
  user: User
  tokens: TokenPair
}

export interface Session {
  session_id: string
  user_agent: string | null
  ip_address: string | null
  created_at: string
  expires_at: string
  is_current: boolean
}

export interface NotificationPreferences {
  email_order_updates: boolean
  email_marketing: boolean
  email_back_in_stock: boolean
  email_price_drop: boolean
  email_review_reminder: boolean
  sms_order_updates: boolean
  sms_marketing: boolean
}

export interface ApiMessage {
  message: string
  ok: boolean
}

export type Province =
  | 'punjab'
  | 'sindh'
  | 'khyber_pakhtunkhwa'
  | 'balochistan'
  | 'gilgit_baltistan'
  | 'azad_jammu_kashmir'
  | 'islamabad'

export const PROVINCES: { value: Province; label: string }[] = [
  { value: 'punjab', label: 'Punjab' },
  { value: 'sindh', label: 'Sindh' },
  { value: 'khyber_pakhtunkhwa', label: 'Khyber Pakhtunkhwa' },
  { value: 'balochistan', label: 'Balochistan' },
  { value: 'gilgit_baltistan', label: 'Gilgit-Baltistan' },
  { value: 'azad_jammu_kashmir', label: 'Azad Jammu & Kashmir' },
  { value: 'islamabad', label: 'Islamabad Capital Territory' },
]

export const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest' },
  { value: 'relevance', label: 'Most relevant' },
  { value: 'price_asc', label: 'Price, low to high' },
  { value: 'price_desc', label: 'Price, high to low' },
  { value: 'rating', label: 'Top rated' },
  { value: 'bestselling', label: 'Best selling' },
] as const

export type SortKey = (typeof SORT_OPTIONS)[number]['value']
