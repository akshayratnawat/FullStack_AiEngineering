import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

interface Props {
  busy: boolean // a reply is on its way
  onSend: (text: string) => void
  onStop: () => void
}

export default function MessageInput({ busy, onSend, onStop }: Props) {
  const [text, setText] = useState('')
  const textarea = useRef<HTMLTextAreaElement>(null)

  // A mouse and keyboard (a "fine" pointer) as opposed to a touch screen. On a phone, focusing the box
  // on its own would open the on-screen keyboard over the page every time a chat is opened.
  const hasKeyboard = () => window.matchMedia('(pointer: fine)').matches

  // Ready to type: on opening a chat, and again once a reply has finished (not on a phone).
  useEffect(() => {
    if (!busy && hasKeyboard()) textarea.current?.focus()
  }, [busy])

  function submit() {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    onSend(trimmed)
    setText('')
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    submit()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Escape stops a reply that is still coming in.
    if (event.key === 'Escape' && busy) {
      event.preventDefault()
      onStop()
      return
    }
    // Enter sends; Shift+Enter adds a new line. On a phone Enter is a new line and the Send button
    // sends, as in ChatGPT. Not while an input method is composing text.
    if (event.nativeEvent.isComposing || !hasKeyboard()) return
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={handleSubmit} className="border-t p-3 md:p-4">
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <Textarea
          ref={textarea}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about the filings…"
          aria-label="Message"
          rows={2}
          className="min-h-0 resize-none"
        />
        {busy ? (
          <Button type="button" variant="outline" onClick={onStop}>
            Stop
          </Button>
        ) : (
          <Button type="submit" disabled={!text.trim()}>
            Send
          </Button>
        )}
      </div>
    </form>
  )
}
