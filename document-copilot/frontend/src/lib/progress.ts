// The research behind an answer: each search, read and check the backend reports while it works.
// It streams as one `data-progress` part that the SDK replaces in place after every step, and is
// saved with the reply, so a reloaded thread can still show how an answer was found.

import type { UIMessage } from 'ai'

export interface Progress {
  steps: string[]
  done: boolean // false while the answer is still being prepared
}

const PROGRESS_PART = 'data-progress'

export function progressOf(message: UIMessage): Progress | null {
  const part = message.parts.find((candidate) => candidate.type === PROGRESS_PART)
  if (!part || !('data' in part)) return null
  const data = part.data as Partial<Progress> | null
  if (!data || !Array.isArray(data.steps)) return null
  return {
    steps: data.steps.filter((step): step is string => typeof step === 'string'),
    done: data.done === true,
  }
}
