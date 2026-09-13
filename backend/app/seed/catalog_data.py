"""The catalogue itself: categories, and the products that fill them.

Written by hand rather than generated from word lists. A seed full of
"Premium Wooden Item 47" makes every screen look like scaffolding, and you
cannot judge a product grid, a search result or a PDP against filler. These are
real Pakistani furniture forms in real local timbers at prices a Lahore
showroom would actually put on them.
"""

from __future__ import annotations

from app.models.enums import WoodSpecies as W

#: (name, slug, [children]) where a child is (name, slug).
CATEGORY_TREE: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("Living", "living", [
        ("Sofas & Daybeds", "sofas-daybeds"),
        ("Coffee Tables", "coffee-tables"),
        ("TV Consoles", "tv-consoles"),
        ("Shelving", "shelving"),
        ("Side Tables", "side-tables"),
    ]),
    ("Dining", "dining", [
        ("Dining Tables", "dining-tables"),
        ("Dining Chairs", "dining-chairs"),
        ("Sideboards", "sideboards"),
        ("Bar Stools", "bar-stools"),
    ]),
    ("Bedroom", "bedroom", [
        ("Beds", "beds"),
        ("Wardrobes", "wardrobes"),
        ("Nightstands", "nightstands"),
        ("Dressers", "dressers"),
    ]),
    ("Office", "office", [
        ("Desks", "desks"),
        ("Bookcases", "bookcases"),
        ("Office Chairs", "office-chairs"),
    ]),
    ("Kitchen & Dining", "kitchen-dining", [
        ("Chopping Boards", "chopping-boards"),
        ("Serving Boards", "serving-boards"),
        ("Utensils", "utensils"),
        ("Spice Racks", "spice-racks"),
    ]),
    ("Decor & Small Goods", "decor", [
        ("Mirrors", "mirrors"),
        ("Frames", "frames"),
        ("Trays", "trays"),
        ("Candle Holders", "candle-holders"),
        ("Planters", "planters"),
    ]),
    ("Storage", "storage", [
        ("Chests & Trunks", "chests-trunks"),
        ("Cabinets", "cabinets"),
        ("Blanket Boxes", "blanket-boxes"),
    ]),
    ("Outdoor", "outdoor", [
        ("Garden Benches", "garden-benches"),
        ("Loungers", "loungers"),
    ]),
    ("Custom & Bespoke", "bespoke", []),
]


#: Finishes, with the surcharge in paisa that some of them carry.
FINISHES: list[tuple[str, str, int]] = [
    ("Natural Oil", "#B08A5E", 0),
    ("Matte Lacquer", "#8A6844", 0),
    ("Walnut Stain", "#5C4433", 150_000),
    ("Whitewash", "#D6C9B4", 150_000),
    ("Dark Wax", "#3E2C1E", 250_000),
]



class Item:
    """One catalogue entry, before it becomes rows.

    Prices are in paisa. Dimensions are millimetres.
    """

    __slots__ = (
        "name", "category", "wood", "price", "subtitle", "description", "story",
        "care", "dims", "weight_g", "sizes", "tags", "personalize", "specs",
    )

    def __init__(
        self,
        name: str,
        category: str,
        wood: W,
        price: int,
        subtitle: str,
        description: str,
        *,
        story: str | None = None,
        care: str | None = None,
        dims: tuple[int, int, int] | None = None,
        weight_g: int | None = None,
        sizes: list[tuple[str, int]] | None = None,
        tags: list[str] | None = None,
        personalize: list[str] | None = None,
        specs: dict | None = None,
    ) -> None:
        self.name = name
        self.category = category
        self.wood = wood
        self.price = price
        self.subtitle = subtitle
        self.description = description
        self.story = story
        self.care = care
        self.dims = dims
        self.weight_g = weight_g
        self.sizes = sizes or []
        self.tags = tags or []
        self.personalize = personalize or []
        self.specs = specs or {}


RS = 100  # paisa per rupee

CARE_HARDWOOD = (
    "Dust with a dry, soft cloth. Wipe spills straight away rather than letting "
    "them sit. Re-oil once or twice a year to keep the grain from drying out. "
    "Keep it out of direct sunlight and away from a heater, both of which will "
    "open up joints over time."
)
CARE_BOARD = (
    "Hand wash in warm water and dry standing on edge. Never put it in a "
    "dishwasher and never leave it soaking. Rub in food-safe mineral oil every "
    "few weeks; when the surface stops looking thirsty, you have done enough."
)
CARE_OUTDOOR = (
    "Teak will silver to a soft grey outdoors, which is the wood protecting "
    "itself and not a fault. If you prefer the original honey colour, clean and "
    "re-oil each spring. Cover it or bring it in during monsoon."
)

ITEMS: list[Item] = [
    # ── Dining ───────────────────────────────────────────────────────────────
    Item(
        "Lahore Six-Seat Dining Table", "dining-tables", W.SHEESHAM, 189_000 * RS,
        "Seats six in solid sheesham",
        "A full-size dining table cut from solid sheesham, with a 40mm top and "
        "hand-cut mortise and tenon joinery at every leg. The grain runs "
        "unbroken across the length because the top is made from four matched "
        "boards, not a veneer over board.",
        story="Sheesham is the timber Punjabi furniture has been made from for "
              "generations. It is dense, it darkens beautifully with age, and it "
              "takes a hand-planed finish better than anything else grown here.",
        care=CARE_HARDWOOD, dims=(1800, 950, 760), weight_g=68_000,
        sizes=[("Six seat, 180cm", 0), ("Eight seat, 220cm", 45_000 * RS),
               ("Ten seat, 260cm", 92_000 * RS)],
        tags=["handmade", "heirloom"],
        personalize=["engraving"],
        specs={"Joinery": "Mortise and tenon", "Top thickness": "40 mm",
               "Assembly": "Legs bolt on, 20 minutes"},
    ),
    Item(
        "Anarkali Dining Chair", "dining-chairs", W.SHEESHAM, 24_500 * RS,
        "Woven cane back, solid frame",
        "A dining chair with a hand-woven cane back and a shaped solid seat. "
        "The back rake was adjusted over several prototypes until it was "
        "comfortable through a long meal rather than just for a photograph.",
        care=CARE_HARDWOOD, dims=(450, 520, 890), weight_g=6_400,
        tags=["handmade"], specs={"Seat height": "460 mm", "Back": "Hand-woven cane"},
    ),
    Item(
        "Gulberg Sideboard", "sideboards", W.WALNUT, 142_000 * RS,
        "Four doors, brass pulls",
        "A long, low sideboard in walnut with four doors, adjustable shelves "
        "behind each pair, and solid brass pulls that will patinate rather than "
        "flake.",
        care=CARE_HARDWOOD, dims=(1650, 450, 800), weight_g=52_000,
        tags=["heirloom"], personalize=["engraving"],
        specs={"Doors": "4", "Hardware": "Solid brass"},
    ),
    Item(
        "Rawal Counter Stool", "bar-stools", W.MANGO, 16_900 * RS,
        "Counter height, footrest",
        "A counter stool in mango wood with a turned footrest and a lightly "
        "dished seat. Stable enough to lean back on without it walking away "
        "from the counter.",
        care=CARE_HARDWOOD, dims=(380, 380, 660), weight_g=4_800,
        sizes=[("Counter, 66cm", 0), ("Bar, 76cm", 2_000 * RS)],
    ),
    Item(
        "Murree Round Dining Table", "dining-tables", W.DEODAR, 96_000 * RS,
        "Four-seat pedestal round",
        "A round four-seat table on a single turned pedestal, so nobody ends up "
        "straddling a leg. Deodar keeps it light enough for one person to move.",
        care=CARE_HARDWOOD, dims=(1100, 1100, 750), weight_g=31_000,
        tags=["eco-friendly"],
    ),

    # ── Living ───────────────────────────────────────────────────────────────
    Item(
        "Ravi Coffee Table", "coffee-tables", W.SHEESHAM, 58_000 * RS,
        "Live-edge top, tapered legs",
        "A coffee table that keeps the natural edge of the board along one "
        "side. Every piece is different because every board is, so the one that "
        "arrives will not be identical to the photograph.",
        story="We buy these boards as whole slabs and cut around the character "
              "rather than cutting it out.",
        care=CARE_HARDWOOD, dims=(1200, 600, 420), weight_g=24_000,
        tags=["live-edge", "handmade", "limited"],
        personalize=["engraving"],
    ),
    Item(
        "Clifton Media Console", "tv-consoles", W.WALNUT, 118_000 * RS,
        "Cable management, two drawers",
        "A media console sized for a 65 inch screen, with two soft-close "
        "drawers, an open bay for a console or receiver, and cable ports cut "
        "through the back panel rather than left to you and a drill.",
        care=CARE_HARDWOOD, dims=(1500, 400, 500), weight_g=38_000,
        sizes=[("140 cm", -8_000 * RS), ("150 cm", 0), ("180 cm", 22_000 * RS)],
        specs={"Fits screens up to": "65 inch", "Drawers": "2, soft close"},
    ),
    Item(
        "Islamabad Bookshelf", "shelving", W.OAK, 74_000 * RS,
        "Five adjustable shelves",
        "A tall open bookshelf with five shelves, each adjustable on a 32mm "
        "pitch. The back is braced diagonally so it stays square rather than "
        "racking into a parallelogram once it is loaded.",
        care=CARE_HARDWOOD, dims=(900, 320, 1900), weight_g=41_000,
        specs={"Shelves": "5, adjustable", "Load per shelf": "35 kg"},
    ),
    Item(
        "Hunza Side Table", "side-tables", W.ACACIA, 18_500 * RS,
        "Three legs, small footprint",
        "A small three-legged side table. Three legs rather than four because "
        "three never rock on an uneven floor.",
        care=CARE_HARDWOOD, dims=(420, 420, 550), weight_g=5_200,
        tags=["handmade"],
    ),
    Item(
        "Chenab Daybed", "sofas-daybeds", W.TEAK, 168_000 * RS,
        "Teak frame, removable cushions",
        "A daybed on a solid teak frame with slatted support and removable "
        "cushions in a heavy cotton canvas. Works indoors or on a covered "
        "veranda.",
        care=CARE_OUTDOOR, dims=(1900, 850, 700), weight_g=54_000,
        tags=["heirloom"],
    ),

    # ── Bedroom ──────────────────────────────────────────────────────────────
    Item(
        "Margalla King Bed", "beds", W.SHEESHAM, 215_000 * RS,
        "Slatted base, no box needed",
        "A king bed with a panelled headboard and a slatted base strong enough "
        "that no box spring is required. The rails bolt to the posts with "
        "captive nuts, so it can be taken apart and moved without losing "
        "strength each time.",
        care=CARE_HARDWOOD, dims=(1980, 1930, 1150), weight_g=86_000,
        sizes=[("Queen", -35_000 * RS), ("King", 0)],
        tags=["heirloom", "handmade"], personalize=["engraving"],
        specs={"Base": "Slatted, 14 slats", "Mattress": "Not included"},
    ),
    Item(
        "Kaghan Nightstand", "nightstands", W.WALNUT, 32_000 * RS,
        "One drawer, open shelf",
        "A nightstand with one dovetailed drawer and an open shelf beneath, "
        "sized so a book and a glass of water both fit on top without "
        "negotiation.",
        care=CARE_HARDWOOD, dims=(450, 400, 550), weight_g=9_800,
        tags=["handmade"], personalize=["engraving"],
    ),
    Item(
        "Swat Three-Door Wardrobe", "wardrobes", W.SHEESHAM, 268_000 * RS,
        "Hanging rail and shelves",
        "A three-door wardrobe with a full-width hanging rail on one side and "
        "five shelves on the other. Doors are solid panel, not board, so they "
        "will not sag off their hinges in a few years.",
        care=CARE_HARDWOOD, dims=(1800, 600, 2100), weight_g=124_000,
        tags=["heirloom"],
    ),
    Item(
        "Neelum Six-Drawer Dresser", "dressers", W.MANGO, 128_000 * RS,
        "Dovetailed drawers",
        "Six drawers, all hand-cut dovetails, running on wooden runners waxed "
        "rather than fitted with metal slides. They will still open smoothly "
        "long after a drawer slide would have given up.",
        care=CARE_HARDWOOD, dims=(1400, 480, 820), weight_g=58_000,
        specs={"Drawers": "6", "Joinery": "Hand-cut dovetail"},
    ),

    # ── Office ───────────────────────────────────────────────────────────────
    Item(
        "Jinnah Writing Desk", "desks", W.WALNUT, 96_000 * RS,
        "Two drawers, cable port",
        "A writing desk with a generous top, two drawers, and a discreet cable "
        "port at the back. Deep enough for a monitor and still leave room to "
        "write.",
        care=CARE_HARDWOOD, dims=(1400, 700, 750), weight_g=34_000,
        tags=["handmade"], personalize=["engraving", "monogram"],
        specs={"Drawers": "2", "Knee clearance": "640 mm"},
    ),
    Item(
        "Karakoram Bookcase", "bookcases", W.OAK, 88_000 * RS,
        "Six shelves, closed back",
        "A tall closed-back bookcase in oak. The closed back adds real rigidity "
        "and stops the wall showing through behind the books.",
        care=CARE_HARDWOOD, dims=(1000, 350, 2100), weight_g=52_000,
    ),

    # ── Kitchen ──────────────────────────────────────────────────────────────
    Item(
        "Grain End-Grain Chopping Board", "chopping-boards", W.ACACIA, 8_900 * RS,
        "End grain, kind to knives",
        "An end-grain board, which means the knife edge parts the fibres rather "
        "than cutting across them. Your knives stay sharper and the board heals "
        "its own cuts.",
        care=CARE_BOARD, dims=(400, 300, 40), weight_g=2_900,
        sizes=[("Small, 30cm", -2_500 * RS), ("Medium, 40cm", 0),
               ("Large, 50cm", 3_500 * RS)],
        tags=["food-safe", "handmade"],
        personalize=["engraving", "monogram"],
        specs={"Construction": "End grain", "Thickness": "40 mm"},
    ),
    Item(
        "Feast Serving Board", "serving-boards", W.MANGO, 6_500 * RS,
        "Long board with a handle",
        "A long serving board with a shaped handle, for bread, cheese or a row "
        "of kebabs straight off the grill.",
        care=CARE_BOARD, dims=(550, 200, 20), weight_g=1_200,
        tags=["food-safe"], personalize=["engraving"],
    ),
    Item(
        "Handled Spice Rack", "spice-racks", W.DEODAR, 5_400 * RS,
        "Two tiers, twelve jars",
        "A two-tier spice rack sized for standard masala jars, with a handle so "
        "the whole thing comes to the stove and goes back again.",
        care=CARE_BOARD, dims=(360, 140, 260), weight_g=1_400,
        tags=["eco-friendly"],
    ),
    Item(
        "Olive Wood Utensil Set", "utensils", W.ACACIA, 4_200 * RS,
        "Spoon, spatula, slotted spoon",
        "Three kitchen utensils turned and shaped by hand. Wood will not scratch "
        "a non-stick pan and will not melt against the side of a hot one.",
        care=CARE_BOARD, weight_g=420, tags=["food-safe", "handmade"],
    ),

    # ── Decor ────────────────────────────────────────────────────────────────
    Item(
        "Arched Hall Mirror", "mirrors", W.TEAK, 34_000 * RS,
        "Arched teak frame",
        "An arched mirror in a solid teak frame, with a 5mm mirror rather than "
        "the thin sheet that distorts once it is hung.",
        care=CARE_HARDWOOD, dims=(600, 30, 1100), weight_g=11_000,
        tags=["handmade"],
    ),
    Item(
        "Gallery Picture Frame", "frames", W.WALNUT, 3_900 * RS,
        "Museum-style deep rebate",
        "A deep-rebate frame that lets a mounted print sit properly back from "
        "the glass, the way a gallery would hang it.",
        care=CARE_BOARD, weight_g=600,
        sizes=[("A4", 0), ("A3", 1_600 * RS), ("A2", 3_400 * RS)],
        personalize=["engraving"],
    ),
    Item(
        "Chai Serving Tray", "trays", W.SHEESHAM, 7_800 * RS,
        "Raised lip, cut handles",
        "A tray with a raised lip and cut-through handles, sized for a full chai "
        "service. The lip is there so a full cup does not walk off the edge on "
        "the way from the kitchen.",
        care=CARE_BOARD, dims=(450, 320, 50), weight_g=1_800,
        tags=["handmade"], personalize=["engraving", "monogram"],
    ),
    Item(
        "Turned Candle Holders", "candle-holders", W.WALNUT, 4_600 * RS,
        "Set of three, graduated heights",
        "Three turned holders at graduated heights, sized for standard dinner "
        "candles, with brass inserts so wax does not soak into the wood.",
        care=CARE_BOARD, weight_g=900, tags=["handmade"],
    ),
    Item(
        "Cedar Planter Box", "planters", W.DEODAR, 9_200 * RS,
        "Lined and drained",
        "A planter box in deodar, which resists rot naturally. Lined, and "
        "drilled for drainage, so it can be planted into directly.",
        care=CARE_OUTDOOR, dims=(600, 250, 300), weight_g=4_100,
        tags=["eco-friendly"],
    ),

    # ── Storage ──────────────────────────────────────────────────────────────
    Item(
        "Dowry Chest", "chests-trunks", W.SHEESHAM, 145_000 * RS,
        "Hand-carved panels",
        "A chest in the tradition of a dowry trunk, with hand-carved front "
        "panels and forged iron hardware. Carving is done by one workshop in "
        "Chiniot and takes about a week per chest.",
        story="Chiniot has been a woodcarving town for four hundred years. The "
              "patterns on this chest are ones the workshop has used for "
              "generations.",
        care=CARE_HARDWOOD, dims=(1100, 550, 600), weight_g=62_000,
        tags=["heirloom", "handmade", "limited"],
        personalize=["engraving"],
    ),
    Item(
        "Attock Blanket Box", "blanket-boxes", W.MANGO, 42_000 * RS,
        "Soft-close lid",
        "A blanket box with a lid on soft-close stays, so it cannot drop on "
        "fingers. Cedar strip inside to keep moths off wool.",
        care=CARE_HARDWOOD, dims=(1000, 450, 480), weight_g=22_000,
    ),
    Item(
        "Two-Door Storage Cabinet", "cabinets", W.OAK, 78_000 * RS,
        "Adjustable interior",
        "A two-door cabinet with three adjustable shelves, deep enough for "
        "files, folded linen or board games.",
        care=CARE_HARDWOOD, dims=(900, 420, 1200), weight_g=36_000,
    ),

    # ── Outdoor ──────────────────────────────────────────────────────────────
    Item(
        "Shalimar Garden Bench", "garden-benches", W.TEAK, 82_000 * RS,
        "Weathers to silver grey",
        "A garden bench in solid teak, assembled with stainless fixings so "
        "nothing rusts and stains the wood. Left outside it will silver to a "
        "soft grey, which is the timber protecting itself.",
        care=CARE_OUTDOOR, dims=(1500, 620, 880), weight_g=34_000,
        sizes=[("Two seat, 120cm", -14_000 * RS), ("Three seat, 150cm", 0)],
        tags=["outdoor", "heirloom"],
    ),
    Item(
        "Veranda Lounger", "loungers", W.TEAK, 94_000 * RS,
        "Five reclining positions",
        "A reclining lounger in teak with five positions and wheels at one end, "
        "so it can be moved without lifting the whole thing.",
        care=CARE_OUTDOOR, dims=(1950, 700, 900), weight_g=28_000,
        tags=["outdoor"],
    ),

    # ── Bespoke ──────────────────────────────────────────────────────────────
    Item(
        "Bespoke Dining Table", "bespoke", W.SHEESHAM, 240_000 * RS,
        "Built to your dimensions",
        "A dining table made to the size you need, in the timber you choose. "
        "Tell us the length, width and height and we will build to it. Lead "
        "time is eight to ten weeks because the timber has to be selected and "
        "then left to settle before it is cut.",
        care=CARE_HARDWOOD, weight_g=70_000,
        tags=["bespoke", "handmade"],
        personalize=["dimensions", "engraving"],
        specs={"Lead time": "8 to 10 weeks", "Deposit": "50 percent"},
    ),
    Item(
        "Bespoke Bookcase", "bespoke", W.WALNUT, 160_000 * RS,
        "Fitted to your wall",
        "A bookcase built to fit a specific alcove or wall, to the millimetre. "
        "Send us the measurements and we will come and check them before "
        "anything is cut.",
        care=CARE_HARDWOOD, weight_g=55_000,
        tags=["bespoke"], personalize=["dimensions"],
        specs={"Lead time": "6 to 8 weeks"},
    ),
]
