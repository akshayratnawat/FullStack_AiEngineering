import { useState } from 'react'

import { useChatOutlet } from '@/components/chat/chat-context'
import MessageInput from '@/components/chat/MessageInput'
import NewChatIntro from '@/components/chat/NewChatIntro'

// Shown at "/": a new chat, before anything is asked. The conversation is created when the first
// question is sent, so opening this screen (or "New chat") leaves nothing behind.
export default function ChatHomePage() {
  const { startChat, requestAsk } = useChatOutlet()
  const [starting, setStarting] = useState(false)

  async function begin(question: string) {
    setStarting(true) // one question starts one chat, not several
    await startChat(question)
    setStarting(false)
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center px-4 py-10">
          {/* A sample question never needs the "by invitation" notice: it plays a stored answer. */}
          <NewChatIntro onPick={(question) => void begin(question)} disabled={starting} />
        </div>
      </div>
      <MessageInput
        busy={starting}
        // A typed question by a visitor shows the notice instead of starting a chat.
        onSend={(text) => requestAsk(text) && void begin(text)}
        onStop={() => {}}
      />
    </div>
  )
}
