// A thin wrapper over the browser's fetch. It knows nothing about our backend or auth:
// that lives in api.ts. It joins URLs, sends and parses JSON, enforces a timeout, and
// turns every failure into one error type.

const DEFAULT_TIMEOUT_MS = 30_000

export class ApiError extends Error {
  // HTTP status, or null when no response came back at all (network, CORS, timeout).
  readonly status: number | null
  // True when the server could not be reached; the UI can say "can't reach the
  // server" instead of showing a generic error.
  readonly isNetworkError: boolean
  // The parsed response body, when there was one (FastAPI sends { detail: ... }).
  readonly body: unknown

  constructor(
    message: string,
    details: { status: number | null; isNetworkError: boolean; body?: unknown },
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = details.status
    this.isNetworkError = details.isNetworkError
    this.body = details.body
  }
}

export interface RequestOptions {
  method?: string
  body?: unknown // sent as JSON
  headers?: Record<string, string>
  timeoutMs?: number
  signal?: AbortSignal // lets the caller cancel; cancelling is not an ApiError
}

export async function request<T>(
  baseUrl: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = 'GET', body, headers = {}, timeoutMs = DEFAULT_TIMEOUT_MS, signal } = options

  const timeout = AbortSignal.timeout(timeoutMs)
  const init: RequestInit = {
    method,
    headers: {
      Accept: 'application/json',
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  }

  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, init)
  } catch (error) {
    if (signal?.aborted) throw error // the caller cancelled on purpose
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new ApiError(`The server did not answer within ${timeoutMs / 1000} seconds.`, {
        status: null,
        isNetworkError: true,
      })
    }
    // fetch rejects with a TypeError for network failures and CORS blocks alike.
    throw new ApiError('Could not reach the server.', { status: null, isNetworkError: true })
  }

  const parsed = await parseBody(response)

  if (!response.ok) {
    throw new ApiError(errorMessage(response.status, parsed), {
      status: response.status,
      isNetworkError: false,
      body: parsed,
    })
  }
  return parsed as T
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return undefined // 204 No Content and empty bodies
  try {
    return JSON.parse(text)
  } catch {
    return text // not JSON (for example a proxy's HTML error page)
  }
}

function errorMessage(status: number, body: unknown): string {
  // FastAPI reports errors as { "detail": "..." } (a string, or a list for validation errors).
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const { detail } = body
    if (typeof detail === 'string') return detail
  }
  return `Request failed with status ${status}.`
}
