// The only way components talk to our FastAPI backend. Adds the signed-in user's
// Supabase token to every request so no component has to handle tokens itself.

import { env } from '@/lib/env'
import { request, type RequestOptions } from '@/lib/http'
import { supabase } from '@/lib/supabase'

// The current access token, or null when nobody is signed in. supabase-js refreshes it
// first if it has expired. Exported for calls that cannot use `api` (the chat stream).
export async function getAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

type CallOptions = Omit<RequestOptions, 'method' | 'body'>

async function send<T>(
  method: string,
  path: string,
  body?: unknown,
  options: CallOptions = {},
): Promise<T> {
  const token = await getAccessToken()
  return request<T>(env.apiBaseUrl, path, {
    ...options,
    method,
    body,
    // Without a token the request still goes out; the backend answers 401 (an ApiError).
    headers: { ...options.headers, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  })
}

export const api = {
  get: <T>(path: string, options?: CallOptions) => send<T>('GET', path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: CallOptions) =>
    send<T>('POST', path, body, options),
  put: <T>(path: string, body?: unknown, options?: CallOptions) =>
    send<T>('PUT', path, body, options),
  patch: <T>(path: string, body?: unknown, options?: CallOptions) =>
    send<T>('PATCH', path, body, options),
  delete: <T>(path: string, options?: CallOptions) => send<T>('DELETE', path, undefined, options),
}
