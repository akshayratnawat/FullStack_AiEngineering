import type { UIMessage } from 'ai'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import ChatSession from '@/components/chat/ChatSession'
import { Button } from '@/components/ui/button'
import { describeError, loadMessages } from '@/lib/chat'

type State =
  | { phase: 'loading' }
  | { phase: 'failed'; message: string }
  | { phase: 'ready'; messages: UIMessage[] }

// Loads a thread's stored messages, then hands them to the live chat.
// Mount it with `key={threadId}`: a different thread starts again from "loading".
export default function ChatThread({ threadId }: { threadId: string }) {
  const [state, setState] = useState<State>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0) // bumped by "Try again" to load once more

  useEffect(() => {
    const controller = new AbortController()
    loadMessages(threadId, controller.signal)
      .then((messages) => setState({ phase: 'ready', messages }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return // we left the page; nothing to show
        setState({ phase: 'failed', message: describeError(error) })
      })
    return () => controller.abort()
  }, [threadId, attempt])

  function retry() {
    setState({ phase: 'loading' })
    setAttempt((count) => count + 1)
  }

  if (state.phase === 'loading') {
    return (
      <div role="status" aria-label="Loading conversation" className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
        <div className="h-10 w-2/5 animate-pulse self-end rounded-lg bg-primary/20" />
        <div className="h-28 w-4/5 animate-pulse rounded-lg bg-muted" />
        <div className="h-10 w-1/3 animate-pulse self-end rounded-lg bg-primary/20" />
      </div>
    )
  }

  if (state.phase === 'failed') {
    return (
      <div className="flex flex-col items-start gap-3 p-6">
        <p role="alert" className="text-destructive">
          {state.message}
        </p>
        <div className="flex items-center gap-4">
          <Button variant="outline" size="sm" onClick={retry}>
            Try again
          </Button>
          <Link to="/" className="text-sm underline underline-offset-4">
            Back to your conversations
          </Link>
        </div>
      </div>
    )
  }

  return <ChatSession threadId={threadId} initialMessages={state.messages} />
}
