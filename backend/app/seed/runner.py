"""The seeder.

Design rules this follows, and why:

Deterministic. One fixed Faker/random seed, so the same data appears on every
run. Screenshots stay valid, and a bug you saw yesterday is still there today.

Idempotent. Re-running does not duplicate. Every creator looks for its natural
key first, so ``--append`` is safe.

Priced by the real engine. Order totals are produced by ``services.pricing``,
not invented. If the seeder made up its own numbers, the admin revenue reports
would disagree with the invoices and every analytics screen would be quietly
lying.
"""

from __future__ import annotations

import random
import time
import uuid
from datetime import UTC, datetime, timedelta

from faker import Faker
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.money import apply_bp
from app.core.permissions import DEFAULT_STAFF_PERMISSIONS, Role
from app.core.security import hash_password
from app.models.cart import Cart, CartItem, WishlistItem
from app.models.catalog import (
    BackInStockSubscription,
    Category,
    PersonalizationOption,
    Product,
    ProductAnswer,
    ProductImage,
    ProductOptionType,
    ProductOptionValue,
    ProductQuestion,
    ProductTag,
    ProductVariant,
    Tag,
    VariantOptionValue,
)
from app.models.content import (
    Banner,
    BlogPost,
    Faq,
    NewsletterSubscriber,
    StaticPage,
    SupportMessage,
    SupportTicket,
    Testimonial,
)
from app.models.enums import (
    Courier,
    DiscountKind,
    DiscountTarget,
    MovementReason,
    NotificationChannel,
    OrderStatus,
    PakistanProvince,
    PaymentMethodCode,
    PaymentStatus,
    PersonalizationInputType,
    ProductStatus,
    ReturnReason,
    ReturnStatus,
    ReviewStatus,
    ShipmentStatus,
    TaxMode,
    WoodSpecies,
)
from app.models.identity import Address, NotificationPreference, User
from app.models.inventory import StockLevel, StockMovement
from app.models.order import (
    Order,
    OrderEvent,
    OrderItem,
    Payment,
    PaymentMethod,
    Refund,
    ReturnItem,
    ReturnRequest,
    Shipment,
    ShipmentItem,
)
from app.models.ops import (
    AuditLog,
    SearchQueryLog,
    ShippingRate,
    ShippingZone,
    StoreSetting,
    TaxClass,
)
from app.models.promotion import (
    Coupon,
    DiscountRule,
    FlashSale,
    FlashSaleItem,
    GiftCard,
    GiftCardTransaction,
    LoyaltyAccount,
    LoyaltyTransaction,
)
from app.models.review import Review, ReviewReply, ReviewVote
from app.seed.catalog_data import CATEGORY_TREE, FINISHES, ITEMS, Item
from app.services.pricing import (
    CouponInput,
    LineInput,
    PersonalizationChoice,
    QuoteRequest,
    quote,
)

SEED = 20260914
RS = 100

fake = Faker("en_US")

#: Pakistani cities, roughly weighted by where furniture actually ships.
CITIES: list[tuple[str, PakistanProvince, str]] = [
    ("Lahore", PakistanProvince.PUNJAB, "54000"),
    ("Karachi", PakistanProvince.SINDH, "74000"),
    ("Islamabad", PakistanProvince.ISLAMABAD, "44000"),
    ("Rawalpindi", PakistanProvince.PUNJAB, "46000"),
    ("Faisalabad", PakistanProvince.PUNJAB, "38000"),
    ("Multan", PakistanProvince.PUNJAB, "60000"),
    ("Peshawar", PakistanProvince.KHYBER_PAKHTUNKHWA, "25000"),
    ("Quetta", PakistanProvince.BALOCHISTAN, "87300"),
    ("Sialkot", PakistanProvince.PUNJAB, "51310"),
    ("Gujranwala", PakistanProvince.PUNJAB, "52250"),
    ("Hyderabad", PakistanProvince.SINDH, "71000"),
    ("Abbottabad", PakistanProvince.KHYBER_PAKHTUNKHWA, "22010"),
    ("Gilgit", PakistanProvince.GILGIT_BALTISTAN, "15100"),
    ("Muzaffarabad", PakistanProvince.AZAD_JAMMU_KASHMIR, "13100"),
]

FIRST_NAMES = [
    "Ayesha", "Fatima", "Zainab", "Maryam", "Hira", "Sana", "Amna", "Nimra",
    "Rabia", "Sadia", "Iqra", "Mahnoor", "Areeba", "Laiba", "Noor",
    "Ahmed", "Ali", "Hassan", "Usman", "Bilal", "Hamza", "Omar", "Zain",
    "Faisal", "Imran", "Kamran", "Adnan", "Tariq", "Shahzad", "Waqas",
    "Danish", "Salman", "Junaid", "Rizwan", "Asad",
]
LAST_NAMES = [
    "Khan", "Ahmed", "Malik", "Butt", "Chaudhry", "Sheikh", "Qureshi", "Raza",
    "Siddiqui", "Hussain", "Iqbal", "Javed", "Mahmood", "Nawaz", "Rashid",
    "Saeed", "Tariq", "Zafar", "Abbasi", "Bhatti", "Gill", "Mirza", "Sial",
]

AREAS = [
    "DHA Phase 5", "Gulberg III", "Model Town", "Bahria Town", "Johar Town",
    "Clifton Block 4", "F-7", "G-11", "Askari 10", "Cantt", "Garden Town",
    "PECHS", "North Nazimabad", "Satellite Town", "University Town",
]
LANDMARKS = [
    "Near Jamia Masjid", "Opposite Total petrol pump", "Behind Imtiaz Store",
    "Next to the park", "Near the community centre", "Opposite the school",
    "Beside Allied Bank", "Near the roundabout",
]


def log(message: str) -> None:
    print(f"  {message}")


class Seeder:
    def __init__(self, db: Session, *, with_images: bool = True) -> None:
        self.db = db
        self.with_images = with_images
        self.rng = random.Random(SEED)
        Faker.seed(SEED)

        self.categories: dict[str, Category] = {}
        self.tags: dict[str, Tag] = {}
        self.products: list[Product] = []
        self.variants: list[ProductVariant] = []
        self.users: list[User] = []
        self.admin: User | None = None
        self.staff: User | None = None
        self.coupons: list[Coupon] = []
        # Global SKU sequence. Deriving the SKU from a truncated slug
        # collides as soon as two products share a prefix.
        self._sku_seq = 0

    log = staticmethod(log)

    # ── helpers ──────────────────────────────────────────────────────────────
    def get_or_create(self, model, defaults: dict | None = None, **lookup):
        instance = self.db.scalar(
            select(model).filter_by(**lookup)
        )
        if instance is not None:
            return instance, False
        instance = model(**lookup, **(defaults or {}))
        self.db.add(instance)
        self.db.flush()
        return instance, True

    def phone(self) -> str:
        return f"03{self.rng.randint(0, 4)}{self.rng.randint(10_000_000, 99_999_999)}"[:11]

    def person(self) -> str:
        return f"{self.rng.choice(FIRST_NAMES)} {self.rng.choice(LAST_NAMES)}"

    # ── 1. store settings, tax, shipping, payment ────────────────────────────
    def seed_settings(self) -> None:
        rows = [
            ("store_name", "general", "Store name", "text", settings.APP_NAME),
            ("store_tagline", "general", "Tagline", "text",
             "Handcrafted wood, made to keep"),
            ("contact_email", "general", "Contact email", "text", "hello@woodcroft.pk"),
            ("contact_phone", "general", "Contact phone", "text", "03001234567"),
            ("store_address", "general", "Address", "text",
             "14-C Commercial Area, Gulberg III, Lahore"),
            ("currency", "general", "Currency", "text", "PKR"),
            ("timezone", "general", "Timezone", "text", "Asia/Karachi"),
            ("tax_mode", "tax", "Tax mode", "text", "inclusive"),
            ("maintenance_mode", "general", "Maintenance mode", "bool", False),
            ("announcement", "general", "Site announcement", "text",
             "Free delivery on orders over Rs 20,000"),
        ]
        for key, group, label, vtype, value in rows:
            existing = self.db.scalar(select(StoreSetting).where(StoreSetting.key == key))
            if existing:
                continue
            setting = StoreSetting(key=key, group=group, label=label, value_type=vtype)
            if vtype == "bool":
                setting.value_bool = value
            elif vtype == "int":
                setting.value_int = value
            else:
                setting.value_text = value
            self.db.add(setting)

        numeric = [
            ("default_tax_rate_bp", "tax", "Default GST rate (basis points)", 1800),
            ("cod_surcharge_paisa", "payments", "COD surcharge", 20_000),
            ("free_shipping_threshold_paisa", "shipping", "Free shipping over", 2_000_000),
            ("loyalty_points_per_rupee", "loyalty", "Points per Rs 100", 1),
            ("loyalty_point_value_paisa", "loyalty", "Value of one point", 100),
            ("referral_reward_paisa", "loyalty", "Referral reward", 50_000),
            ("return_window_days", "orders", "Return window (days)", 14),
            ("cancel_window_hours", "orders", "Self-cancel window (hours)", 24),
        ]
        for key, group, label, value in numeric:
            if self.db.scalar(select(StoreSetting).where(StoreSetting.key == key)):
                continue
            self.db.add(
                StoreSetting(
                    key=key, group=group, label=label, value_type="int", value_int=value
                )
            )

        self.get_or_create(
            TaxClass, {"rate_bp": 1800, "is_default": True,
                       "description": "Pakistan standard GST"},
            name="Standard 18%",
        )
        self.get_or_create(
            TaxClass, {"rate_bp": 0, "description": "Exempt goods"}, name="Zero-rated"
        )

        # Shipping zones. Punjab is cheapest because the workshop is in Lahore.
        zones = [
            ("Punjab & Islamabad", ["punjab", "islamabad"], 45_000, True, 20_000),
            ("Sindh", ["sindh"], 75_000, True, 25_000),
            ("Khyber Pakhtunkhwa", ["khyber_pakhtunkhwa"], 85_000, True, 25_000),
            ("Balochistan & North", ["balochistan", "gilgit_baltistan",
                                     "azad_jammu_kashmir"], 120_000, False, 0),
        ]
        for name, provinces, price, cod, cod_fee in zones:
            zone, created = self.get_or_create(
                ShippingZone,
                {"provinces": provinces, "cod_available": cod,
                 "cod_surcharge_paisa": cod_fee,
                 "cod_max_order_paisa": 30_000_000 if cod else None},
                name=name,
            )
            if not created:
                continue
            self.db.add(ShippingRate(
                zone_id=zone.id, name="Standard", courier=Courier.TCS,
                price_paisa=price, free_above_paisa=2_000_000,
                min_days=3, max_days=6, sort_order=0,
            ))
            self.db.add(ShippingRate(
                zone_id=zone.id, name="Express", courier=Courier.LEOPARDS,
                price_paisa=price * 2, min_days=1, max_days=3, sort_order=1,
            ))

        methods = [
            (PaymentMethodCode.COD, "Cash on Delivery",
             "Pay the courier in cash when your order arrives.", True, None, 0),
            (PaymentMethodCode.JAZZCASH, "JazzCash",
             "Pay from your JazzCash mobile account.", False, "Coming soon", 1),
            (PaymentMethodCode.EASYPAISA, "Easypaisa",
             "Pay from your Easypaisa account.", False, "Coming soon", 2),
        ]
        for code, name, desc, enabled, label, order in methods:
            self.get_or_create(
                PaymentMethod,
                {"display_name": name, "description": desc, "is_enabled": enabled,
                 "unavailable_label": label, "sort_order": order,
                 "surcharge_paisa": 20_000 if code is PaymentMethodCode.COD else 0},
                code=code,
            )
        log("settings, tax, shipping zones and payment methods")

    # ── 2. categories and tags ───────────────────────────────────────────────
    def seed_categories(self) -> None:
        for order, (name, slug, children) in enumerate(CATEGORY_TREE):
            parent, _ = self.get_or_create(
                Category,
                {"name": name, "path": slug, "depth": 0, "sort_order": order,
                 "description": f"{name} pieces, made by hand in solid timber."},
                slug=slug,
            )
            self.categories[slug] = parent

            for child_order, (child_name, child_slug) in enumerate(children):
                child, _ = self.get_or_create(
                    Category,
                    {"name": child_name, "parent_id": parent.id,
                     "path": f"{slug}/{child_slug}", "depth": 1,
                     "sort_order": child_order},
                    slug=child_slug,
                )
                self.categories[child_slug] = child

        for name, slug, accent in [
            ("Handmade", "handmade", "brass"),
            ("Heirloom", "heirloom", "walnut"),
            ("Eco-friendly", "eco-friendly", "forest"),
            ("Limited edition", "limited", "brass"),
            ("Live edge", "live-edge", "walnut"),
            ("Food safe", "food-safe", "forest"),
            ("Outdoor", "outdoor", "forest"),
            ("Bespoke", "bespoke", "brass"),
        ]:
            tag, _ = self.get_or_create(Tag, {"name": name, "accent": accent}, slug=slug)
            self.tags[slug] = tag

        log(f"{len(self.categories)} categories, {len(self.tags)} tags")

    # ── 3. products ──────────────────────────────────────────────────────────
    def seed_products(self) -> None:
        from app.services.media.plates import write_plate, write_swatch

        media_root = settings.media_path
        if self.with_images:
            for species in WoodSpecies:
                write_swatch(media_root, species)

        created = 0
        # Each hand-written item is produced in two or three timbers, which is
        # how a real workshop offers them and gets us to a realistic catalogue
        # size without inventing filler products.
        for base in ITEMS:
            woods = self._woods_for(base)
            for index, wood in enumerate(woods):
                product = self._make_product(base, wood, index, media_root, write_plate)
                if product is not None:
                    created += 1

        self.db.flush()
        log(f"{created} products, {len(self.variants)} variants")

    def _woods_for(self, base: Item) -> list[WoodSpecies]:
        alternates = {
            WoodSpecies.SHEESHAM: [WoodSpecies.WALNUT, WoodSpecies.MANGO],
            WoodSpecies.WALNUT: [WoodSpecies.SHEESHAM, WoodSpecies.OAK],
            WoodSpecies.TEAK: [WoodSpecies.ACACIA],
            WoodSpecies.MANGO: [WoodSpecies.ACACIA, WoodSpecies.SHEESHAM],
            WoodSpecies.ACACIA: [WoodSpecies.MANGO],
            WoodSpecies.OAK: [WoodSpecies.WALNUT, WoodSpecies.DEODAR],
            WoodSpecies.DEODAR: [WoodSpecies.PINE],
            WoodSpecies.PINE: [WoodSpecies.DEODAR],
        }
        # Three or four timbers per form, which is how a workshop actually
        # offers them, and gets us a realistic catalogue size without
        # inventing filler products.
        extra = alternates.get(base.wood, [])
        pool = [w for w in WoodSpecies if w != base.wood and w not in extra]
        self.rng.shuffle(pool)
        chosen = [*extra, *pool][: self.rng.randint(2, 3)]
        return [base.wood, *chosen]

    def _make_product(self, base: Item, wood: WoodSpecies, index: int,
                      media_root, write_plate) -> Product | None:
        name = base.name if index == 0 else f"{base.name} in {wood.label.split(' (')[0]}"
        slug = name.lower().replace(",", "").replace("&", "and")
        slug = "-".join(slug.split()).replace("--", "-")

        if self.db.scalar(select(Product).where(Product.slug == slug)):
            return None

        category = self.categories[base.category]
        # Denser timber costs more. Multipliers are roughly market-real.
        multiplier = {
            WoodSpecies.SHEESHAM: 1.0, WoodSpecies.WALNUT: 1.15,
            WoodSpecies.TEAK: 1.30, WoodSpecies.MANGO: 0.82,
            WoodSpecies.ACACIA: 0.88, WoodSpecies.OAK: 1.05,
            WoodSpecies.DEODAR: 0.78, WoodSpecies.PINE: 0.65,
        }[wood]
        price = int(base.price * multiplier / 100) * 100

        on_sale = self.rng.random() < 0.22
        compare_at = int(price * self.rng.uniform(1.15, 1.4) / 100) * 100 if on_sale else None

        product = Product(
            category_id=category.id,
            name=name,
            slug=slug,
            subtitle=base.subtitle,
            description=base.description,
            story=base.story,
            care_instructions=base.care,
            base_price_paisa=price,
            compare_at_price_paisa=compare_at,
            cost_price_paisa=int(price * 0.55),
            wood_species=wood,
            length_mm=base.dims[0] if base.dims else None,
            width_mm=base.dims[1] if base.dims else None,
            height_mm=base.dims[2] if base.dims else None,
            weight_g=base.weight_g,
            specifications={**base.specs, "Timber": wood.label},
            status=ProductStatus.ACTIVE,
            published_at=datetime.now(UTC) - timedelta(days=self.rng.randint(1, 500)),
            is_featured=self.rng.random() < 0.15,
            is_new_arrival=self.rng.random() < 0.18,
            is_bestseller=self.rng.random() < 0.12,
            meta_title=f"{name} | Woodcroft",
            meta_description=base.subtitle,
        )
        self.db.add(product)
        self.db.flush()

        for slug_tag in base.tags:
            if slug_tag in self.tags:
                self.db.add(ProductTag(product_id=product.id, tag_id=self.tags[slug_tag].id))

        self._make_variants(product, base, wood)
        self._make_personalization(product, base)
        self._make_images(product, wood, media_root, write_plate, base.category)

        self.products.append(product)
        return product

    def _make_variants(self, product: Product, base: Item, wood: WoodSpecies) -> None:
        size_type = None
        if base.sizes:
            size_type = ProductOptionType(product_id=product.id, name="Size", sort_order=0)
            self.db.add(size_type)
            self.db.flush()

        finish_type = ProductOptionType(product_id=product.id, name="Finish", sort_order=1)
        self.db.add(finish_type)
        self.db.flush()

        finishes = self.rng.sample(FINISHES, self.rng.randint(2, 3))
        finish_values = []
        for order, (fname, swatch, surcharge) in enumerate(finishes):
            value = ProductOptionValue(
                option_type_id=finish_type.id, value=fname, swatch=swatch,
                sort_order=order,
            )
            self.db.add(value)
            finish_values.append((value, surcharge))
        self.db.flush()

        size_values = []
        if size_type is not None:
            for order, (label, delta) in enumerate(base.sizes):
                value = ProductOptionValue(
                    option_type_id=size_type.id, value=label, sort_order=order
                )
                self.db.add(value)
                size_values.append((value, delta))
            self.db.flush()
        else:
            size_values = [(None, 0)]

        prefix = f"WC-{wood.value[:3].upper()}"
        counter = 1
        for size_value, size_delta in size_values:
            for finish_value, finish_delta in finish_values:
                delta = size_delta + finish_delta
                self._sku_seq += 1
                variant = ProductVariant(
                    product_id=product.id,
                    sku=f"{prefix}-{self._sku_seq:05d}",
                    name=" / ".join(
                        p for p in [
                            size_value.value if size_value else None,
                            finish_value.value,
                        ] if p
                    ),
                    price_paisa=product.base_price_paisa + delta if delta else None,
                    compare_at_price_paisa=(
                        product.compare_at_price_paisa + delta
                        if product.compare_at_price_paisa and delta else None
                    ),
                    cost_price_paisa=int((product.base_price_paisa + delta) * 0.55),
                    weight_g=product.weight_g,
                    sort_order=counter,
                )
                self.db.add(variant)
                self.db.flush()
                counter += 1

                if size_value is not None:
                    self.db.add(VariantOptionValue(
                        variant_id=variant.id, option_value_id=size_value.id
                    ))
                self.db.add(VariantOptionValue(
                    variant_id=variant.id, option_value_id=finish_value.id
                ))

                self._make_stock(variant)
                self.variants.append(variant)

    def _make_stock(self, variant: ProductVariant) -> None:
        """Deliberately include out of stock, low stock and healthy cases.

        Every stock state needs to exist in the seed, or the PDP badges, the
        low stock report and the back in stock flow have nothing to render.
        """
        roll = self.rng.random()
        if roll < 0.08:
            on_hand = 0
        elif roll < 0.22:
            on_hand = self.rng.randint(1, 4)
        else:
            on_hand = self.rng.randint(8, 60)

        self.db.add(StockLevel(
            variant_id=variant.id, on_hand=on_hand, reserved=0,
            low_stock_threshold=5,
            restocked_at=datetime.now(UTC) - timedelta(days=self.rng.randint(1, 120)),
        ))
        if on_hand:
            self.db.add(StockMovement(
                variant_id=variant.id, delta=on_hand, balance_after=on_hand,
                reason=MovementReason.INITIAL, note="Opening stock",
                unit_cost_paisa=variant.cost_price_paisa,
            ))

    def _make_personalization(self, product: Product, base: Item) -> None:
        specs = {
            "engraving": dict(
                key="engraving", label="Engraving",
                help_text="Up to 30 characters, cut by hand into the underside.",
                input_type=PersonalizationInputType.TEXT,
                surcharge_paisa=150_000, surcharge_per_char_paisa=2_500,
                max_length=30, constraints={"pattern": "^[A-Za-z0-9 .,'-]+$"},
            ),
            "monogram": dict(
                key="monogram", label="Monogram",
                help_text="Two or three initials.",
                input_type=PersonalizationInputType.MONOGRAM,
                surcharge_paisa=90_000, max_length=3,
                constraints={"uppercase": True},
            ),
            "dimensions": dict(
                key="dimensions", label="Custom dimensions",
                help_text="Give length, width and height in centimetres.",
                input_type=PersonalizationInputType.DIMENSIONS,
                surcharge_paisa=1_200_000, is_required=True,
                constraints={"min_cm": 40, "max_cm": 320},
            ),
        }
        for order, key in enumerate(base.personalize):
            if key in specs:
                self.db.add(PersonalizationOption(
                    product_id=product.id, sort_order=order, **specs[key]
                ))

    def _make_images(self, product: Product, wood: WoodSpecies,
                     media_root, write_plate, subcategory: str) -> None:
        count = 3
        use_photos = self.with_images and settings.SEED_IMAGE_MODE == "curated"
        photo_ids: list[str] = []
        if use_photos:
            from app.services.media.photos import photo_ids_for
            photo_ids = photo_ids_for(subcategory, product.slug, count)

        for angle in range(count):
            rel = f"products/{product.slug}/{angle}"
            meta = None
            # Prefer a real curated photo; fall back to a generated plate if the
            # download fails, so an offline seed still produces images.
            if use_photos and angle < len(photo_ids):
                from app.services.media.photos import write_photo
                meta = write_photo(media_root, rel, photo_ids[angle])
            if meta is None and self.with_images:
                meta = write_plate(media_root, rel, wood, key=product.slug, angle=angle)
            if meta is None:
                meta = {
                    "base_path": rel, "sizes": [400, 800, 1600],
                    "width": 1000, "height": 1250, "aspect": 0.8,
                    "blur_data_url": None, "source": "generated", "checksum": None,
                }
            self.db.add(ProductImage(
                product_id=product.id,
                alt_text=f"{product.name}, view {angle + 1}",
                sort_order=angle,
                is_primary=(angle == 0),
                **meta,
            ))
