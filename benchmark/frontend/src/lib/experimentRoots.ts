export function encodeExperimentRoot(root: string): string {
  const bytes = new TextEncoder().encode(root)
  const binary = Array.from(bytes, (value) => String.fromCharCode(value)).join('')
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '')
}

export function decodeExperimentRoot(value: string): string {
  try {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
    const pad = normalized.length % 4
    const padded = normalized + (pad === 0 ? '' : '='.repeat(4 - pad))
    const binary = atob(padded)
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0))
    return new TextDecoder().decode(bytes)
  } catch {
    return ''
  }
}
