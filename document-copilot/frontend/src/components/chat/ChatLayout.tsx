import { useCallback, useEffect, useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'

import type { ChatOutletContext } from '@/components/chat/chat-context'
import ThreadSidebar from '@/components/chat/ThreadSidebar'
import { createThread, describeError, listThreads, type Thread } from '@/lib/chat'

// A layout route: the sidebar stays put while the page beside it changes.
// It owns the thread list so both the sidebar and the open chat can refresh it.
export default function ChatLayout() {
  const navigate = useNavigate()
  const [threads, setThreads] = useState<Thread[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const refreshThreads = useCallback(async () => {
    try {
      setThreads(await listThreads())
      setError(null)
    } catch (failure) {
      setError(describeError(failure))
    }
  }, [])

  // The first load. It runs in the effect itself so leaving the page can cancel it.
  useEffect(() => {
    let cancelled = false
    listThreads()
      .then((loaded) => {
        if (!cancelled) setThreads(loaded)
      })
      .catch((failure: unknown) => {
        if (!cancelled) setError(describeError(failure))
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleNewChat() {
    setCreating(true)
    try {
      const thread = await createThread()
      await refreshThreads()
      navigate(`/chat/${thread.id}`)
    } catch (failure) {
      setError(describeError(failure))
    } finally {
      setCreating(false)
    }
  }

  const context: ChatOutletContext = { refreshThreads }

  return (
    <div className="flex h-screen">
      <ThreadSidebar
        threads={threads}
        error={error}
        creating={creating}
        onNewChat={handleNewChat}
      />
      <main className="min-w-0 flex-1">
        <Outlet context={context} />
      </main>
    </div>
  )
}
