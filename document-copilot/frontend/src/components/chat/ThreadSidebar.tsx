import { NavLink } from 'react-router-dom'

import { useAuth } from '@/components/auth/auth-context'
import { Button } from '@/components/ui/button'
import type { Thread } from '@/lib/chat'
import { cn } from '@/lib/utils'
import { supabase } from '@/lib/supabase'

interface Props {
  threads: Thread[] | null // null while the first load is running
  error: string | null
  creating: boolean
  onNewChat: () => void
}

export default function ThreadSidebar({ threads, error, creating, onNewChat }: Props) {
  const { session } = useAuth()

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r bg-muted/30">
      <div className="flex flex-col gap-3 p-3">
        <h1 className="px-1 text-lg font-semibold">Document Copilot</h1>
        <Button onClick={onNewChat} disabled={creating}>
          {creating ? 'Creating…' : 'New chat'}
        </Button>
      </div>

      <nav aria-label="Conversations" className="flex-1 overflow-y-auto px-2">
        {error && (
          <p role="alert" className="px-2 py-1 text-sm text-destructive">
            {error}
          </p>
        )}
        {threads === null && !error && (
          <p className="px-2 py-1 text-sm text-muted-foreground">Loading…</p>
        )}
        {threads?.length === 0 && (
          <p className="px-2 py-1 text-sm text-muted-foreground">No conversations yet.</p>
        )}
        <ul className="flex flex-col gap-1">
          {threads?.map((thread) => (
            <li key={thread.id}>
              <NavLink
                to={`/chat/${thread.id}`}
                className={({ isActive }) =>
                  cn(
                    'block truncate rounded-md px-2 py-1.5 text-sm hover:bg-muted',
                    isActive && 'bg-muted font-medium',
                    !thread.title && 'text-muted-foreground',
                  )
                }
              >
                {thread.title ?? 'New chat'}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="flex flex-col gap-2 border-t p-3">
        <p className="truncate text-sm text-muted-foreground">{session?.user.email}</p>
        <Button variant="outline" size="sm" onClick={() => supabase.auth.signOut()}>
          Sign out
        </Button>
      </div>
    </aside>
  )
}
