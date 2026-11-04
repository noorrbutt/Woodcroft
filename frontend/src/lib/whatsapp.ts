const number = import.meta.env.VITE_WHATSAPP_NUMBER?.replace(/\D/g, '')

export function wa(text: string): string | null {
  if (!number) return null
  return `https://wa.me/${number}?text=${encodeURIComponent(text)}`
}

export function whatsappShareUrl(text: string): string {
  return `https://wa.me/?text=${encodeURIComponent(text)}`
}
