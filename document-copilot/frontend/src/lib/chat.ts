// Everything the chat screens need from the backend: the thread calls, and the
// transport that tells the AI SDK where and how to stream.

import { DefaultChatTransport, type UIMessage } from 'ai'

import { api, getAccessToken } from '@/lib/api'
import { env } from '@/lib/env'
import { ApiError } from '@/lib/http'

export interface Thread {
  id: string
  title: string | null // null until the first question names it
  created_at: string
  updated_at: string
}

export const listThreads = () => api.get<Thread[]>('/threads')
export const createThread = () => api.post<Thread>('/threads')
export const renameThread = (threadId: string, title: string) =>
  api.patch<Thread>(`/threads/${threadId}`, { title })
export const deleteThread = (threadId: string) => api.delete<void>(`/threads/${threadId}`)
export const loadMessages = (threadId: string, signal?: AbortSignal) =>
  api.get<UIMessage[]>(`/threads/${threadId}/messages`, { signal })

// The SDK makes the streaming request itself, so it cannot go through `api`: this
// gives it the same token and the thread id the backend needs.
export function createChatTransport(threadId: string) {
  return new DefaultChatTransport({
    api: `${env.apiBaseUrl}/chat/stream`,
    headers: async (): Promise<Record<string, string>> => {
      const token = await getAccessToken()
      return token ? { Authorization: `Bearer ${token}` } : {}
    },
    body: { threadId },
  })
}

const TRY_AGAIN = 'The server had a problem. Please try again in a moment.'
const CANNOT_REACH = 'Could not reach the server. Is the backend running?'

// One readable sentence for any failure from the calls above or from the stream.
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.isNetworkError) return CANNOT_REACH
    if (error.status === 401) return 'Your session has expired. Please sign in again.'
    // 403 carries the backend's own reason: another user's chat, or an account not allowed in.
    if (error.status === 403) return error.message
    if (error.status === 404) return 'This conversation no longer exists.'
    // A 5xx is our side (or the database being busy), not something the user did.
    if (error.status !== null && error.status >= 500) return TRY_AGAIN
    return error.message
  }
  if (error instanceof Error) {
    // The SDK reports a failed request by putting the response body in the message.
    try {
      const body: unknown = JSON.parse(error.message)
      if (typeof body === 'object' && body !== null && 'detail' in body) {
        if (typeof body.detail === 'string') return body.detail
      }
    } catch {
      // Not JSON: fall through to the plain message.
    }
    if (error instanceof TypeError) return CANNOT_REACH // fetch's network/CORS failure
    return error.message
  }
  return 'Something went wrong. Please try again.'
}
