import type { UIMessage } from 'ai'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import ChatSession from '@/components/chat/ChatSession'
import { describeError, loadMessages } from '@/lib/chat'

type State =
  | { phase: 'loading' }
  | { phase: 'failed'; message: string }
  | { phase: 'ready'; messages: UIMessage[] }

// Loads a thread's stored messages, then hands them to the live chat.
// Mount it with `key={threadId}`: a different thread starts again from "loading".
export default function ChatThread({ threadId }: { threadId: string }) {
  const [state, setState] = useState<State>({ phase: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    loadMessages(threadId, controller.signal)
      .then((messages) => setState({ phase: 'ready', messages }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return // we left the page; nothing to show
        setState({ phase: 'failed', message: describeError(error) })
      })
    return () => controller.abort()
  }, [threadId])

  if (state.phase === 'loading') {
    return <p className="p-6 text-muted-foreground">Loading conversation…</p>
  }

  if (state.phase === 'failed') {
    return (
      <div className="flex flex-col items-start gap-3 p-6">
        <p role="alert" className="text-destructive">
          {state.message}
        </p>
        <Link to="/" className="text-sm underline underline-offset-4">
          Back to your conversations
        </Link>
      </div>
    )
  }

  return <ChatSession threadId={threadId} initialMessages={state.messages} />
}
