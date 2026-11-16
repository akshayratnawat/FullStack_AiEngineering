import { useChat } from '@ai-sdk/react'
import type { UIMessage } from 'ai'
import { useState } from 'react'

import { useChatOutlet } from '@/components/chat/chat-context'
import MessageInput from '@/components/chat/MessageInput'
import MessageList from '@/components/chat/MessageList'
import { createChatTransport } from '@/lib/chat'

interface Props {
  threadId: string
  initialMessages: UIMessage[] // the stored history; the SDK manages everything after it
}

// One live conversation. Mount it with `key={threadId}` so each thread gets a fresh chat.
export default function ChatSession({ threadId, initialMessages }: Props) {
  const { refreshThreads } = useChatOutlet()
  const [transport] = useState(() => createChatTransport(threadId))

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

  return (
    <div className="flex h-full flex-col">
      <MessageList messages={messages} status={status} error={error} />
      <MessageInput
        busy={status === 'submitted' || status === 'streaming'}
        onSend={handleSend}
        onStop={stop}
      />
    </div>
  )
}
