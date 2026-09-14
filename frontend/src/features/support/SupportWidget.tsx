/**
 * Support widget.
 *
 * A floating button that opens a WhatsApp chat with the shop. WhatsApp is how
 * customers in Pakistan actually reach a business, and it needs no third-party
 * script on the page.
 */

import { MessageCircle } from 'lucide-react'

// +92 315 3441833 in wa.me form (country code, no spaces, no leading zero).
const WHATSAPP_NUMBER = '923153441833'
const WHATSAPP_URL =
  `https://wa.me/${WHATSAPP_NUMBER}?text=` +
  encodeURIComponent('Hi Woodcroft, I have a question about')

export function SupportWidget() {
  return (
    <a
      href={WHATSAPP_URL}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Chat with us on WhatsApp"
      className="fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full
                 bg-[#25D366] px-4 py-3 text-sm font-medium text-white shadow-lg
                 transition-transform hover:scale-105 wc-no-print"
    >
      <MessageCircle size={20} strokeWidth={1.75} />
      <span className="hidden sm:inline">Chat with us</span>
    </a>
  )
}
