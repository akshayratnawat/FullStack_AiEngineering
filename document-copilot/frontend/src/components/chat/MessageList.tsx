import type { ChatStatus, UIMessage } from 'ai'
import { Check, Copy, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import AnswerText from '@/components/chat/AnswerText'
import NewChatIntro from '@/components/chat/NewChatIntro'
import ResearchSteps from '@/components/chat/ResearchSteps'
import SourceChips from '@/components/chat/SourceChips'
import { Button } from '@/components/ui/button'
import { answerWithFootnotes } from '@/lib/answer'
import { describeError } from '@/lib/chat'
import { isFailedReply, sourcesOf } from '@/lib/citations'
import { progressOf } from '@/lib/progress'
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
  onRetry: (question: string) => void // asks the same question again
  onAsk: (question: string) => void // asks a question picked from the examples
}

function textOf(message: UIMessage): string {
  return message.parts.map((part) => (part.type === 'text' ? part.text : '')).join('')
}

// Copies the answer with its sources listed, and says so for a moment.
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard access can be refused (an insecure page, a blocked permission); nothing to do.
    }
  }

  return (
    <Button variant="ghost" size="xs" onClick={() => void copy()} aria-label="Copy answer with sources">
      {copied ? <Check /> : <Copy />}
      {copied ? 'Copied' : 'Copy'}
    </Button>
  )
}

export default function MessageList({
  messages,
  status,
  error,
  selected,
  onSelectSource,
  onRetry,
  onAsk,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Keep the newest text in view as it streams in.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, status])

  const lastMessage = messages.at(-1)
  const streamingReply = status === 'streaming' && lastMessage?.role === 'assistant'
  const idle = status === 'ready' || status === 'error'
  // The last question the user asked, so a failed reply or a dropped connection can be retried.
  const lastUser = [...messages].reverse().find((message) => message.role === 'user')
  const lastQuestion = lastUser ? textOf(lastUser) : ''

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
        {messages.length === 0 && (
          <div className="py-10">
            <NewChatIntro onPick={onAsk} disabled={status !== 'ready'} />
          </div>
        )}

        {messages.map((message) => {
          const sources = message.role === 'assistant' ? sourcesOf(message) : []
          const selectedMarker = selected?.messageId === message.id ? selected.marker : null
          const failed = isFailedReply(message)
          const progress = message.role === 'assistant' ? progressOf(message) : null
          const finished = message.role === 'assistant' && !(streamingReply && message === lastMessage)
          const select = (marker: number, figure: string | null = null) =>
            onSelectSource({ messageId: message.id, marker, figure })

          return (
            <div
              key={message.id}
              className={cn(
                'max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm',
                message.role === 'user' ? 'self-end bg-primary text-primary-foreground' : 'self-start bg-muted',
                failed && 'border border-dashed border-muted-foreground/40',
              )}
            >
              {progress && <ResearchSteps progress={progress} />}
              {failed && (
                <p className="mb-1 text-xs font-medium text-muted-foreground">No answer given</p>
              )}
              <AnswerText
                text={textOf(message)}
                sources={sources}
                selectedMarker={selectedMarker}
                onSelect={select}
              />
              {streamingReply && message === lastMessage && textOf(message) && (
                <span aria-hidden className="ml-0.5 animate-pulse">
                  ▍
                </span>
              )}
              <SourceChips sources={sources} selectedMarker={selectedMarker} onSelect={select} />
              {finished && textOf(message) && (
                <div className="mt-2 flex gap-1">
                  {!failed && <CopyButton text={answerWithFootnotes(textOf(message), sources)} />}
                  {failed && message === lastMessage && idle && lastQuestion && (
                    <Button variant="ghost" size="xs" onClick={() => onRetry(lastQuestion)}>
                      <RotateCcw />
                      Try again
                    </Button>
                  )}
                </div>
              )}
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
          <div role="alert" className="flex flex-wrap items-center gap-2 text-sm text-destructive">
            <p>{describeError(error)}</p>
            {idle && lastQuestion && (
              <Button variant="outline" size="xs" onClick={() => onRetry(lastQuestion)}>
                <RotateCcw />
                Try again
              </Button>
            )}
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
