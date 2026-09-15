"""Real, Pakistan-tailored content for the statutory CMS pages.

IMPORTANT: These are practical, plain-English templates, not legal advice. A
qualified lawyer in Pakistan MUST review and adapt them before launch, and every
[PLACEHOLDER] must be replaced with the business's real facts. They are written
for a Karachi-based, cash-on-delivery furniture retailer and reference the Sindh
Consumer Protection Act 2014, the Prevention of Electronic Crimes Act 2016
(PECA) and the E-Commerce Policy of Pakistan 2019.

Slugs here match the seeded StaticPage slugs so the same pages that gate checkout
carry real content. The owner/lawyer can then edit them in Admin -> Content.
"""

from __future__ import annotations

# Facts the owner must confirm; surfaced verbatim so they are easy to find/replace.
LEGAL_NAME = "[PLACEHOLDER: registered business / legal name]"
ADDRESS = "[PLACEHOLDER: full registered address], Karachi, Sindh, Pakistan"
NTN = "[PLACEHOLDER: NTN - and STRN if sales-tax registered]"
PHONE = "[PLACEHOLDER: one real, working phone / WhatsApp number]"
EMAIL = "hello@woodcroft.pk"
RETURN_WINDOW = "[PLACEHOLDER: e.g. 7 days]"
REFUND_METHOD = "[PLACEHOLDER: bank transfer / JazzCash / Easypaisa / cash]"
REFUND_DAYS = "[PLACEHOLDER: e.g. 7–10 working days]"
COURIERS = "[PLACEHOLDER: courier(s) used, e.g. TCS / Leopards / own fleet]"
FOUNDED = "[PLACEHOLDER: founding year - publish only if accurate]"

_DISCLAIMER = (
    '<p style="background:#f6efe2;border:1px solid #c9963f;padding:12px 14px;'
    'border-radius:6px"><strong>Draft for review.</strong> This page is a working '
    "template and not legal advice. It must be reviewed by a qualified lawyer in "
    "Pakistan, and every bracketed placeholder replaced with our real details, "
    "before we rely on it.</p>"
)

_CONTACT_BLOCK = (
    "<h2>Contact us</h2>"
    f"<p>{LEGAL_NAME}<br>{ADDRESS}<br>"
    f'Email: <a href="mailto:{EMAIL}">{EMAIL}</a><br>Phone/WhatsApp: {PHONE}<br>'
    f"NTN: {NTN}</p>"
)


PRIVACY = f"""
{_DISCLAIMER}
<h1>Privacy Policy</h1>
<p><em>Last updated: [PLACEHOLDER: date].</em></p>
<p>This policy explains what personal data Woodcroft ({LEGAL_NAME}) collects, why,
how long we keep it, and your choices. We process personal data in line with the
Prevention of Electronic Crimes Act 2016 and applicable Pakistani law.</p>

<h2>What we collect</h2>
<ul>
  <li><strong>Order &amp; delivery details</strong> - your name, phone number,
      delivery address and any landmark, and the items you ordered. These are
      required to fulfil a cash-on-delivery order.</li>
  <li><strong>Account details</strong> - email, name, phone and a securely hashed
      password (we never store your password in plain text).</li>
  <li><strong>Messages you send us</strong> - the contents of contact-form
      messages, support tickets, reviews and product questions.</li>
  <li><strong>Newsletter</strong> - your email address, only if you subscribe.</li>
  <li><strong>Technical data</strong> - for security we log the IP address,
      device/browser (user-agent) and timestamps of sign-ins and sessions, and we
      record search terms you enter to improve results.</li>
  <li><strong>On your device</strong> - see our
      <a href="/page/cookies">Cookie &amp; Storage Notice</a>. We do not use
      advertising or analytics cookies or any third-party trackers.</li>
</ul>

<h2>Why we use it</h2>
<ul>
  <li>To take, deliver and support your orders, and to contact you about them.</li>
  <li>To run your account and keep it secure.</li>
  <li>To answer your questions and handle returns, refunds and complaints.</li>
  <li>To send marketing email <strong>only if you have opted in</strong>; you can
      unsubscribe at any time from any marketing email or in your account.</li>
  <li>To meet legal, tax and record-keeping obligations.</li>
</ul>

<h2>Who we share it with</h2>
<p>We do not sell your personal data. We share it only as needed to run the
store: our delivery courier(s) ({COURIERS}) receive your name, address and phone
to deliver cash-on-delivery orders; and service providers who host or email on
our behalf under confidentiality terms. We may disclose data where required by
law or a lawful order.</p>

<h2>How long we keep it</h2>
<p>We keep order and tax records for the period required by law
[PLACEHOLDER: retention period]. Account data is kept while your account is
active. Security logs, search history and sent notifications are kept for
[PLACEHOLDER: retention window] and then deleted or anonymised.</p>

<h2>Your choices and rights</h2>
<p>You can ask us to access, correct or delete your personal data, or to close
your account, by writing to <a href="mailto:{EMAIL}">{EMAIL}</a> or from your
account settings. We will respond within a reasonable time. Some data may be
retained where the law requires (for example tax records).</p>

<h2>Security</h2>
<p>We protect data with industry-standard measures including password hashing,
encrypted transport (HTTPS) and access controls. No system is perfectly secure,
so we cannot guarantee absolute security.</p>

<h2>Children</h2>
<p>The store is intended for customers aged 18 and over. We do not knowingly
collect data from children.</p>

<h2>Changes</h2>
<p>We may update this policy; the date above shows the latest version.</p>
{_CONTACT_BLOCK}
"""


TERMS = f"""
{_DISCLAIMER}
<h1>Terms of Service</h1>
<p><em>Last updated: [PLACEHOLDER: date].</em></p>
<p>These terms govern your use of this website and your purchases from Woodcroft
({LEGAL_NAME}). By using the site or placing an order you agree to them. If you
do not agree, please do not use the site.</p>

<h2>Who we are</h2>
<p>{LEGAL_NAME}, {ADDRESS}. NTN: {NTN}. Contact:
<a href="mailto:{EMAIL}">{EMAIL}</a>, {PHONE}.</p>

<h2>Eligibility</h2>
<p>You must be at least 18 years old and able to enter a binding contract to buy
from us.</p>

<h2>Your account</h2>
<p>Keep your login details confidential; you are responsible for activity under
your account. Tell us at once if you suspect unauthorised use.</p>

<h2>Orders and how a contract is formed</h2>
<p>Product listings are an invitation to order, not an offer. When you place an
order you make an offer to buy. A binding contract forms only when we confirm the
order is accepted and being prepared for dispatch. We may decline or cancel an
order (for example if an item is out of stock, a price is clearly wrong, or an
address cannot be served) and will not charge you for a cancelled order.</p>

<h2>Prices, tax and payment</h2>
<p>Prices are in Pakistani Rupees. [PLACEHOLDER: confirm whether prices include
GST and whether the business is sales-tax registered; if registered, show STRN on
invoices; if not, do not label the tax line "GST".] Payment is by
<strong>cash on delivery</strong> only. Please have the exact amount ready.</p>

<h2>Delivery, returns and refunds</h2>
<p>Delivery is covered by our <a href="/page/shipping">Shipping Policy</a> and
your cancellation, return and refund rights by our
<a href="/page/returns">Return &amp; Refund Policy</a>, which form part of these
terms.</p>

<h2>Custom and bespoke items</h2>
<p>Made-to-order and bespoke pieces are produced to your specification and may not
be returnable except where faulty. See the Return &amp; Refund Policy.</p>

<h2>Intellectual property</h2>
<p>The Woodcroft name, logo, site content and images are owned by us or used
under licence and may not be copied without permission.</p>

<h2>Acceptable use</h2>
<p>Do not misuse the site, attempt to breach its security, post unlawful content,
or submit fake reviews.</p>

<h2>Product descriptions</h2>
<p>Solid timber is a natural material; grain, colour and small variations are
normal and are not defects. We describe pieces as accurately as we can.</p>

<h2>Warranty and liability</h2>
<p>Nothing in these terms excludes rights you have under the Sindh Consumer
Protection Act 2014 or other applicable law. Subject to that, and to the extent
the law allows, our liability for any order is limited to the price you paid for
the affected item. [PLACEHOLDER: any product warranty you offer, and its terms.]</p>

<h2>Governing law and disputes</h2>
<p>These terms are governed by the laws of Pakistan, and the courts at Karachi,
Sindh have jurisdiction. We aim to resolve complaints directly first - please
contact us.</p>

<h2>Changes</h2>
<p>We may update these terms; the date above shows the latest version.</p>
{_CONTACT_BLOCK}
"""


RETURNS = f"""
{_DISCLAIMER}
<h1>Return &amp; Refund Policy</h1>
<p><em>Last updated: [PLACEHOLDER: date].</em></p>
<p>We want you to be happy with your furniture. This policy explains when you can
cancel, return or get a refund. It is in addition to your rights under the Sindh
Consumer Protection Act 2014.</p>

<h2>Cancelling an order</h2>
<p>You may cancel before dispatch at no cost by contacting us at
<a href="mailto:{EMAIL}">{EMAIL}</a> or {PHONE}. Because we pay on delivery,
there is nothing to refund for an order cancelled before dispatch.</p>

<h2>Returns</h2>
<p>You may return an eligible item within <strong>{RETURN_WINDOW}</strong> of
delivery if it is unused, in its original condition and packaging. To start a
return, contact us with your order number.</p>

<h2>Items that cannot be returned</h2>
<ul>
  <li>Custom, bespoke or made-to-measure pieces, unless faulty.</li>
  <li>Items damaged by misuse after delivery.</li>
  <li>[PLACEHOLDER: any other exclusions, e.g. clearance items.]</li>
</ul>

<h2>Damaged, faulty or wrong items</h2>
<p>Please inspect your delivery on arrival. If an item is damaged, faulty or not
what you ordered, tell us within [PLACEHOLDER: e.g. 48 hours] with photos and we
will arrange a repair, replacement or refund at no cost to you. This does not
affect your statutory rights.</p>

<h2>Refunds (cash on delivery)</h2>
<p>Because orders are paid in cash on delivery, approved refunds are paid by
<strong>{REFUND_METHOD}</strong>. We will ask for the details needed to pay you.
Refunds are issued within <strong>{REFUND_DAYS}</strong> after we receive and
check the returned item, or after we confirm a fault. Store credit is offered
only as an option you may choose, never in place of a cash refund you are owed.</p>

<h2>Return shipping</h2>
<p>[PLACEHOLDER: who pays return shipping - we cover it for faulty/wrong items;
for change-of-mind returns state your policy.]</p>
{_CONTACT_BLOCK}
"""


SHIPPING = f"""
{_DISCLAIMER}
<h1>Shipping Policy</h1>
<p><em>Last updated: [PLACEHOLDER: date].</em></p>
<h2>Where we deliver</h2>
<p>We deliver across Pakistan. [PLACEHOLDER: list any areas you cannot serve.]</p>

<h2>Delivery times</h2>
<p>Ready-made pieces are usually dispatched within [PLACEHOLDER: e.g. 2–3 working
days]. Delivery then takes about [PLACEHOLDER: Karachi/Sindh vs other provinces
timelines]. Made-to-order and bespoke pieces take longer; we will confirm a
timeline when you order.</p>

<h2>Delivery charges</h2>
<p>Delivery is calculated at checkout based on your address and order size. Orders
over Rs 20,000 qualify for free delivery. [PLACEHOLDER: confirm the threshold and
any surcharges, e.g. remote areas or large items.]</p>

<h2>Cash on delivery</h2>
<p>Orders are paid in cash to the delivery team on arrival. Please have the exact
amount ready. [PLACEHOLDER: any COD ceiling or verification step.]</p>

<h2>Tracking and couriers</h2>
<p>We deliver through {COURIERS}. Where a tracking number is available we will
share it so you can follow your order.</p>
{_CONTACT_BLOCK}
"""


COOKIES = f"""
{_DISCLAIMER}
<h1>Cookie &amp; Storage Notice</h1>
<p><em>Last updated: [PLACEHOLDER: date].</em></p>
<p>Woodcroft does <strong>not</strong> use advertising or analytics cookies, and
we do not load any third-party trackers, pixels or advertising scripts. Because
of this, no intrusive "accept cookies" banner is needed.</p>

<h2>What we store on your device</h2>
<p>To make the site work, we save a small amount of information in your browser's
local storage. This stays on your device and is not shared with anyone:</p>
<ul>
  <li><strong>Sign-in token</strong> - keeps you logged in.</li>
  <li><strong>Cart and wishlist</strong> - remembers items you added.</li>
  <li><strong>Theme</strong> - remembers your light/dark preference.</li>
</ul>

<h2>Security logs</h2>
<p>For security we also record the IP address, browser (user-agent) and time of
sign-ins on our server, as described in our
<a href="/page/privacy">Privacy Policy</a>.</p>

<h2>Managing storage</h2>
<p>You can clear this information at any time from your browser settings. Clearing
it will sign you out and empty your saved cart.</p>
{_CONTACT_BLOCK}
"""


ACCESSIBILITY = f"""
<h1>Accessibility Statement</h1>
<p><em>Last updated: [PLACEHOLDER: date].</em></p>
<p>We want Woodcroft to be usable by as many people as possible and are working
towards the WCAG 2.1 AA standard. The site includes a skip-to-content link,
visible keyboard focus, respect for reduced-motion settings, labelled controls
and alternative text on meaningful images.</p>

<h2>Known limitations</h2>
<p>We are still improving some areas, including keyboard focus handling in a few
overlays and colour contrast on some minor text. We do not yet claim full WCAG
2.1 AA conformance and are actively addressing these.</p>

<h2>Tell us</h2>
<p>If you have trouble using any part of the site, or need information in another
format, please contact <a href="mailto:{EMAIL}">{EMAIL}</a> and we will help and
use your feedback to improve.</p>
"""


ABOUT = f"""
<h1>About Woodcroft</h1>
<p>Woodcroft is a workshop in Karachi making solid-timber furniture and woodware
for people who intend to keep it. [PLACEHOLDER: your real story - founding year
"{FOUNDED}" only if accurate, materials, and what makes your pieces yours.]</p>
<p>Questions? Write to <a href="mailto:{EMAIL}">{EMAIL}</a> and a person will
reply.</p>
"""


SUSTAINABILITY = f"""
<h1>Sustainability</h1>
<p>[PLACEHOLDER: describe only sourcing and sustainability practices you can
actually stand behind - avoid unverifiable claims such as "every board from a
named mill" unless it is true and documented.]</p>
<p>Questions? Write to <a href="mailto:{EMAIL}">{EMAIL}</a>.</p>
"""


# slug -> (title, html). Titles match the existing seeded pages.
LEGAL_PAGES: dict[str, tuple[str, str]] = {
    "privacy": ("Privacy Policy", PRIVACY),
    "terms": ("Terms of Service", TERMS),
    "returns": ("Return & Refund Policy", RETURNS),
    "shipping": ("Shipping Policy", SHIPPING),
    "cookies": ("Cookie & Storage Notice", COOKIES),
    "accessibility": ("Accessibility Statement", ACCESSIBILITY),
    "about": ("About Woodcroft", ABOUT),
    "sustainability": ("Sustainability", SUSTAINABILITY),
}
