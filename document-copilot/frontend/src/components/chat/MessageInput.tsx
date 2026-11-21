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

  // Ready to type: on opening a chat, and again once a reply has finished.
  useEffect(() => {
    if (!busy) textarea.current?.focus()
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
    // Enter sends; Shift+Enter adds a new line. Not while an input method is composing text.
    if (event.nativeEvent.isComposing) return
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={handleSubmit} className="border-t p-4">
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <Textarea
          ref={textarea}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about the filings…  (Enter to send, Shift+Enter for a new line)"
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
