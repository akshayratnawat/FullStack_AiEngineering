import type { ChatStatus, UIMessage } from 'ai'
import { useEffect, useRef } from 'react'

import { describeError } from '@/lib/chat'
import { cn } from '@/lib/utils'

interface Props {
  messages: UIMessage[]
  status: ChatStatus
  error: Error | undefined
}

// Only text parts exist so far; citations arrive with retrieval.
function textOf(message: UIMessage): string {
  return message.parts.map((part) => (part.type === 'text' ? part.text : '')).join('')
}

export default function MessageList({ messages, status, error }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Keep the newest text in view as it streams in.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, status])

  const lastMessage = messages.at(-1)
  const streamingReply = status === 'streaming' && lastMessage?.role === 'assistant'

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
        {messages.length === 0 && (
          <p className="py-16 text-center text-muted-foreground">
            Ask a question to start the conversation.
          </p>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={cn(
              'max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm',
              message.role === 'user' ? 'self-end bg-primary text-primary-foreground' : 'self-start bg-muted',
            )}
          >
            {textOf(message)}
            {streamingReply && message === lastMessage && (
              <span aria-hidden className="ml-0.5 animate-pulse">
                ▍
              </span>
            )}
          </div>
        ))}

        {/* Sent, and nothing has come back yet. */}
        {status === 'submitted' && (
          <div className="self-start rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
            <span className="animate-pulse">Thinking…</span>
          </div>
        )}

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {describeError(error)}
          </p>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
