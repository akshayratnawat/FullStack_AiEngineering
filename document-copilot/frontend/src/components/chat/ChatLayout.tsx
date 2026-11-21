import { useCallback, useEffect, useState } from 'react'
import { Outlet, useMatch, useNavigate } from 'react-router-dom'

import type { ChatOutletContext } from '@/components/chat/chat-context'
import ThreadSidebar from '@/components/chat/ThreadSidebar'
import {
  createThread,
  deleteThread,
  describeError,
  listThreads,
  renameThread,
  type Thread,
} from '@/lib/chat'
import { ApiError } from '@/lib/http'

// A layout route: the sidebar stays put while the page beside it changes.
// It owns the thread list so both the sidebar and the open chat can refresh it.
export default function ChatLayout() {
  const navigate = useNavigate()
  const openThreadId = useMatch('/chat/:threadId')?.params.threadId
  const [threads, setThreads] = useState<Thread[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null) // the list could not load
  const [actionError, setActionError] = useState<string | null>(null) // a create/rename/delete failed
  const [creating, setCreating] = useState(false)

  const refreshThreads = useCallback(async () => {
    try {
      setThreads(await listThreads())
      setLoadError(null)
    } catch (failure) {
      setLoadError(describeError(failure))
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
        if (!cancelled) setLoadError(describeError(failure))
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Try the failed load again, showing the loading state while it runs.
  const retryLoad = useCallback(() => {
    setLoadError(null)
    void refreshThreads()
  }, [refreshThreads])

  const startChat = useCallback(
    async (question?: string) => {
      setCreating(true)
      setActionError(null)
      try {
        const thread = await createThread()
        await refreshThreads()
        // The question travels in the navigation state; the chat sends it once it opens.
        navigate(`/chat/${thread.id}`, { state: question ? { question } : undefined })
      } catch (failure) {
        setActionError(describeError(failure))
      } finally {
        setCreating(false)
      }
    },
    [navigate, refreshThreads],
  )

  async function handleRename(threadId: string, title: string): Promise<boolean> {
    setActionError(null)
    try {
      await renameThread(threadId, title)
      await refreshThreads()
      return true
    } catch (failure) {
      setActionError(describeError(failure))
      return false
    }
  }

  async function handleDelete(threadId: string) {
    setActionError(null)
    try {
      await deleteThread(threadId)
    } catch (failure) {
      // A thread that is already gone is what the user wanted; anything else is a real failure.
      if (!(failure instanceof ApiError && failure.status === 404)) {
        setActionError(describeError(failure))
        return
      }
    }
    // Leave the deleted chat before the list changes, so it never shows a missing thread.
    if (threadId === openThreadId) navigate('/', { replace: true })
    await refreshThreads()
  }

  const context: ChatOutletContext = { refreshThreads, startChat }

  return (
    <div className="flex h-screen">
      <ThreadSidebar
        threads={threads}
        loadError={loadError}
        actionError={actionError}
        creating={creating}
        onNewChat={() => void startChat()}
        onRetry={retryLoad}
        onRename={handleRename}
        onDelete={handleDelete}
      />
      <main className="min-w-0 flex-1">
        <Outlet context={context} />
      </main>
    </div>
  )
}
