import { useCallback, useEffect, useState } from 'react'
import { Outlet, useLocation, useMatch, useNavigate } from 'react-router-dom'

import { ArrowUpRight, Menu } from 'lucide-react'

import type { ChatOutletContext } from '@/components/chat/chat-context'
import DemoNoticeDialog from '@/components/chat/DemoNoticeDialog'
import ThreadSidebar from '@/components/chat/ThreadSidebar'
import { Button } from '@/components/ui/button'
import { getAccount } from '@/lib/account'
import { env } from '@/lib/env'
import { cn } from '@/lib/utils'
import { hasStoredAnswer } from '@/lib/examples'
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
  const { pathname } = useLocation()
  const openThreadId = useMatch('/chat/:threadId')?.params.threadId
  const [threads, setThreads] = useState<Thread[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null) // the list could not load
  const [actionError, setActionError] = useState<string | null>(null) // a create/rename/delete failed
  // Whether this account may ask live questions; null until /me answers. While unknown nothing is
  // blocked here: the backend decides, so a slow answer can never wrongly lock the owner out.
  const [canAsk, setCanAsk] = useState<boolean | null>(null)
  const [noticeOpen, setNoticeOpen] = useState(false)
  // On a phone the chat list is a drawer that slides over the chat; from the md breakpoint up it is
  // a fixed column beside it and this does nothing. The drawer remembers which page it was opened
  // on, so going to another chat (or "New chat") closes it without any extra code.
  const [menuOpenAt, setMenuOpenAt] = useState<string | null>(null)
  const menuOpen = menuOpenAt === pathname
  const setMenuOpen = (open: boolean) => setMenuOpenAt(open ? pathname : null)

  useEffect(() => {
    if (!menuOpen) return
    const close = (event: KeyboardEvent) => event.key === 'Escape' && setMenuOpenAt(null)
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [menuOpen])

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

  useEffect(() => {
    let cancelled = false
    getAccount()
      .then((account) => {
        if (!cancelled) setCanAsk(account.can_ask)
      })
      .catch(() => {
        // Left unknown: the app still works, and the backend refuses what it must.
      })
    return () => {
      cancelled = true
    }
  }, [])

  const requestAsk = useCallback(
    (question: string) => {
      // A sample question is replayed by the backend without a model call, so anyone may ask it.
      if (canAsk !== false || hasStoredAnswer(question)) return true
      setNoticeOpen(true)
      return false
    },
    [canAsk],
  )

  // Try the failed load again, showing the loading state while it runs.
  const retryLoad = useCallback(() => {
    setLoadError(null)
    void refreshThreads()
  }, [refreshThreads])

  const startChat = useCallback(
    async (question?: string) => {
      setActionError(null)
      try {
        const thread = await createThread()
        await refreshThreads()
        // The question travels in the navigation state; the chat sends it once it opens.
        navigate(`/chat/${thread.id}`, { state: question ? { question } : undefined })
      } catch (failure) {
        setActionError(describeError(failure))
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

  const context: ChatOutletContext = { refreshThreads, startChat, requestAsk }

  return (
    // dvh, not vh: on a phone "100vh" is taller than the visible area while the browser's address
    // bar is showing, which pushes the message box off the bottom of the screen.
    <div className="flex h-dvh">
      {menuOpen && (
        <button
          type="button"
          aria-label="Close menu"
          onClick={() => setMenuOpen(false)}
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
        />
      )}
      <div
        className={cn(
          'fixed inset-y-0 left-0 z-40 w-72 max-w-[85vw] transition-transform duration-200',
          'md:static md:z-auto md:w-64 md:max-w-none md:shrink-0 md:translate-x-0',
          // Closed on a phone: off screen and out of the tab order (md:visible keeps it on a desktop).
          menuOpen ? 'translate-x-0' : 'invisible -translate-x-full md:visible',
        )}
      >
        <ThreadSidebar
          threads={threads}
          loadError={loadError}
          actionError={actionError}
          onNewChat={() => navigate('/')}
          onRetry={retryLoad}
          onRename={handleRename}
          onDelete={handleDelete}
        />
      </div>
      <main className="flex min-w-0 flex-1 flex-col">
        {/* Top bar. On a phone it always shows, for the menu button. On a larger screen it shows only
            when it has something to say: a way to reach the owner for a live demo, and, for a
            visitor, why asking is limited. */}
        <header
          className={cn(
            'flex items-center gap-2 border-b bg-muted/30 px-2 py-2 md:px-4',
            !(env.contactUrl || canAsk === false) && 'md:hidden',
          )}
        >
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label="Open chats"
            onClick={() => setMenuOpen(true)}
          >
            <Menu />
          </Button>
          <p className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
            <span className="text-sm font-medium text-foreground md:hidden">
              {canAsk === false ? 'Visitor view' : 'Document Copilot'}
            </span>
            {canAsk === false && (
              <span className="hidden md:inline">
                You are viewing as a visitor. Try the sample questions to see how answers and sources work;
                your own questions are limited to approved accounts.
              </span>
            )}
          </p>
          {env.contactUrl && (
            <Button
              variant="outline"
              size="sm"
              className="shrink-0"
              render={<a href={env.contactUrl} target="_blank" rel="noreferrer" />}
            >
              <span className="sm:hidden">Contact</span>
              <span className="hidden sm:inline">Contact Akshay</span>
              <ArrowUpRight />
            </Button>
          )}
        </header>
        <div className="min-h-0 flex-1">
          <Outlet context={context} />
        </div>
      </main>
      <DemoNoticeDialog open={noticeOpen} onClose={() => setNoticeOpen(false)} />
    </div>
  )
}
