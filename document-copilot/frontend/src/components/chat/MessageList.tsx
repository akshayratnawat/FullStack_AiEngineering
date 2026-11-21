import type { ChatStatus, UIMessage } from 'ai'
import { useEffect, useRef } from 'react'

import AnswerText from '@/components/chat/AnswerText'
import SourceChips from '@/components/chat/SourceChips'
import { describeError } from '@/lib/chat'
import { isFailedReply, sourcesOf } from '@/lib/citations'
import { cn } from '@/lib/utils'

// The source an analyst has opened: which message, and which [n] in it.
export interface SelectedSource {
  messageId: string
  marker: number
  figure: string | null // the number the clicked marker follows, highlighted in the passage
}

interface Props {
  messages: UIMessage[]
  status: ChatStatus
  error: Error | undefined
  selected: SelectedSource | null
  onSelectSource: (selection: SelectedSource) => void
}

function textOf(message: UIMessage): string {
  return message.parts.map((part) => (part.type === 'text' ? part.text : '')).join('')
}

export default function MessageList({ messages, status, error, selected, onSelectSource }: Props) {
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

        {messages.map((message) => {
          const sources = message.role === 'assistant' ? sourcesOf(message) : []
          const selectedMarker = selected?.messageId === message.id ? selected.marker : null
          const select = (marker: number, figure: string | null = null) =>
            onSelectSource({ messageId: message.id, marker, figure })

          return (
            <div
              key={message.id}
              className={cn(
                'max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm',
                message.role === 'user' ? 'self-end bg-primary text-primary-foreground' : 'self-start bg-muted',
                isFailedReply(message) && 'border border-dashed border-muted-foreground/40',
              )}
            >
              {isFailedReply(message) && (
                <p className="mb-1 text-xs font-medium text-muted-foreground">No answer given</p>
              )}
              <AnswerText
                text={textOf(message)}
                sources={sources}
                selectedMarker={selectedMarker}
                onSelect={select}
              />
              {streamingReply && message === lastMessage && (
                <span aria-hidden className="ml-0.5 animate-pulse">
                  ▍
                </span>
              )}
              <SourceChips sources={sources} selectedMarker={selectedMarker} onSelect={select} />
            </div>
          )
        })}

        {/* Sent, and nothing has come back yet. */}
        {status === 'submitted' && (
          <div className="self-start rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
            <span className="animate-pulse">Searching the filings…</span>
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
