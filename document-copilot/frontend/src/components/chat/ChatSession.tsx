import { useChat } from '@ai-sdk/react'
import type { UIMessage } from 'ai'
import { useCallback, useState } from 'react'

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
  const { refreshThreads } = useChatOutlet()
  const [transport] = useState(() => createChatTransport(threadId))
  const [selected, setSelected] = useState<SelectedSource | null>(null)

  const { messages, sendMessage, status, stop, error, clearError } = useChat({
    id: threadId,
    messages: initialMessages,
    transport,
    // The reply is saved when it ends, which is also when the thread gets its title.
    onFinish: () => void refreshThreads(),
  })

  function handleSend(text: string) {
    if (error) clearError()
    void sendMessage({ text })
  }

  const closeSource = useCallback(() => setSelected(null), [])

  // The open source, looked up from the messages so it always shows what the answer cited.
  const selectedMessage = selected && messages.find((message) => message.id === selected.messageId)
  const openSource =
    selected && selectedMessage
      ? sourcesOf(selectedMessage).find((source) => source.marker === selected.marker)
      : undefined

  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <MessageList
          messages={messages}
          status={status}
          error={error}
          selected={selected}
          onSelectSource={setSelected}
        />
        <MessageInput
          busy={status === 'submitted' || status === 'streaming'}
          onSend={handleSend}
          onStop={stop}
        />
      </div>
      {openSource && <SourcePanel source={openSource} highlight={selected?.figure ?? null} onClose={closeSource} />}
    </div>
  )
}
