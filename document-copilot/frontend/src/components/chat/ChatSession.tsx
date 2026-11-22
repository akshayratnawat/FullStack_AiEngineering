import { useChat } from '@ai-sdk/react'
import type { UIMessage } from 'ai'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { useChatOutlet } from '@/components/chat/chat-context'
import MessageInput from '@/components/chat/MessageInput'
import MessageList, { type SelectedSource } from '@/components/chat/MessageList'
import SourcePanel from '@/components/chat/SourcePanel'
import { createChatTransport } from '@/lib/chat'
import { sourcesOf } from '@/lib/citations'

interface Props {
  threadId: string
  initialMessages: UIMessage[] // the stored history; the SDK manages everything after it
}

// One live conversation. Mount it with `key={threadId}` so each thread gets a fresh chat.
export default function ChatSession({ threadId, initialMessages }: Props) {
  const { refreshThreads, requestAsk } = useChatOutlet()
  const location = useLocation()
  const navigate = useNavigate()
  const [transport] = useState(() => createChatTransport(threadId))
  const [selected, setSelected] = useState<SelectedSource | null>(null)

  const { messages, sendMessage, status, stop, error, clearError } = useChat({
    id: threadId,
    messages: initialMessages,
    transport,
    // The reply is saved when it ends, which is also when the thread gets its title.
    onFinish: () => void refreshThreads(),
  })

  // Asks a question with no check: used for the sample questions, which the backend answers from
  // a stored answer for anyone, and for the question a chat is opened with.
  const ask = useCallback(
    (text: string) => {
      if (error) clearError()
      void sendMessage({ text })
    },
    [error, clearError, sendMessage],
  )

  // What the user types, and "Try again": a visitor needing a live answer sees the notice instead.
  const send = useCallback(
    (text: string) => {
      if (requestAsk(text)) ask(text)
    },
    [requestAsk, ask],
  )

  // A question picked or typed on the new-chat screen arrives in the navigation state. Ask it once,
  // then drop it from the history entry so a refresh or a Back does not ask it again.
  //
  // It is sent from a timer, not straight from the effect, on purpose: in development React mounts
  // every component, unmounts it and mounts it again, and `useChat` stops its chat on that unmount.
  // A question sent immediately was stopped by it and never came back (the first click did nothing).
  // The unmount cancels the timer and the remount sets it again, so the question goes out once.
  useEffect(() => {
    const question = (location.state as { question?: string } | null)?.question
    if (!question) return
    const timer = setTimeout(() => {
      navigate(location.pathname, { replace: true, state: null })
      void sendMessage({ text: question })
    }, 0)
    return () => clearTimeout(timer)
  }, [location, navigate, sendMessage])

  const closeSource = useCallback(() => setSelected(null), [])

  // The open source, looked up from the messages so it always shows what the answer cited.
  const selectedMessage = selected && messages.find((message) => message.id === selected.messageId)
  const sources = useMemo(() => (selectedMessage ? sourcesOf(selectedMessage) : []), [selectedMessage])
  const position = selected ? sources.findIndex((source) => source.marker === selected.marker) : -1
  const openSource = position >= 0 ? sources[position] : undefined

  // Step to the previous or next source of the same answer. The figure highlight belongs to the
  // marker that was clicked, so it is dropped when moving on.
  const stepSource = useCallback(
    (delta: number) => {
      const next = sources[position + delta]
      if (selected && next) setSelected({ ...selected, marker: next.marker, figure: null })
    },
    [sources, position, selected],
  )

  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <MessageList
          messages={messages}
          status={status}
          error={error}
          selected={selected}
          onSelectSource={setSelected}
          onRetry={send}
          onAsk={ask}
        />
        <MessageInput
          busy={status === 'submitted' || status === 'streaming'}
          onSend={send}
          onStop={stop}
        />
      </div>
      {openSource && (
        <SourcePanel
          source={openSource}
          highlight={selected?.figure ?? null}
          position={position}
          total={sources.length}
          onStep={stepSource}
          onClose={closeSource}
        />
      )}
    </div>
  )
}
