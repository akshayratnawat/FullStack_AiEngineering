// The only file that reads environment variables. Everything else imports `env`.
// Vite copies VITE_* values into the browser bundle, so anyone can read them:
// only public values belong here (never the Supabase service-role key).

// Every placeholder value in .env.example contains this (e.g. "your-project-ref").
const PLACEHOLDER_MARKER = 'your-'

function requireVar(name: string, value: string | undefined): string {
  const trimmed = value?.trim()
  if (!trimmed) {
    throw new Error(`${name} is missing. Copy .env.example to .env and fill it in.`)
  }
  // Catches a copied .env.example whose values were never filled in.
  // Name the variable only; never echo the value.
  if (trimmed.toLowerCase().includes(PLACEHOLDER_MARKER)) {
    throw new Error(`${name} still has its .env.example placeholder.`)
  }
  return trimmed
}

function requireUrl(name: string, value: string | undefined): string {
  const trimmed = requireVar(name, value)
  try {
    new URL(trimmed)
  } catch {
    throw new Error(`${name} is not a valid URL (include http:// or https://).`)
  }
  return trimmed
}

// A link where visitors can reach the owner (a mailto: or a profile URL). Optional: without it the
// "live questions are by invitation" notice just names the owner.
function optionalUrl(name: string, value: string | undefined): string | null {
  const trimmed = value?.trim()
  return trimmed ? requireUrl(name, trimmed) : null
}

export const env = {
  contactUrl: optionalUrl('VITE_CONTACT_URL', import.meta.env.VITE_CONTACT_URL),
  // No trailing slash, so `${env.apiBaseUrl}/health` is always well formed.
  apiBaseUrl: requireUrl('VITE_API_BASE_URL', import.meta.env.VITE_API_BASE_URL).replace(/\/+$/, ''),
  supabaseUrl: requireUrl('VITE_SUPABASE_URL', import.meta.env.VITE_SUPABASE_URL),
  supabaseAnonKey: requireVar('VITE_SUPABASE_ANON_KEY', import.meta.env.VITE_SUPABASE_ANON_KEY),
}
