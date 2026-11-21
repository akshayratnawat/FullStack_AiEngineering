import { Check, Pencil, Trash2, X } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { NavLink } from 'react-router-dom'

import { useAuth } from '@/components/auth/auth-context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { Thread } from '@/lib/chat'
import { cn } from '@/lib/utils'
import { supabase } from '@/lib/supabase'

interface Props {
  threads: Thread[] | null // null while the first load is running
  loadError: string | null
  actionError: string | null
  creating: boolean
  onNewChat: () => void
  onRetry: () => void
  onRename: (threadId: string, title: string) => Promise<boolean> // true when it was saved
  onDelete: (threadId: string) => Promise<void>
}

// Which row is being edited or asked to confirm, if any. One at a time keeps the list calm.
type Editing = { id: string; mode: 'rename' | 'delete' } | null

const ROW = 'flex items-center gap-1 rounded-md px-1 hover:bg-muted'

function RenameRow({
  thread,
  onSave,
  onCancel,
}: {
  thread: Thread
  onSave: (title: string) => Promise<boolean>
  onCancel: () => void
}) {
  const [title, setTitle] = useState(thread.title ?? '')
  const [saving, setSaving] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    input.current?.focus()
    input.current?.select()
  }, [])

  async function save() {
    const trimmed = title.trim()
    if (!trimmed || saving) return
    if (trimmed === thread.title) return onCancel() // nothing changed
    setSaving(true)
    const saved = await onSave(trimmed)
    if (!saved) setSaving(false) // stay open so the user can retry; the error shows above the list
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') void save()
    if (event.key === 'Escape') onCancel()
  }

  return (
    <div className={cn(ROW, 'bg-muted')}>
      <Input
        ref={input}
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        onKeyDown={handleKeyDown}
        maxLength={120}
        disabled={saving}
        aria-label="Conversation name"
        className="h-7 min-w-0 flex-1 px-2 py-1 text-sm"
      />
      <Button
        variant="ghost"
        size="icon-xs"
        onClick={() => void save()}
        disabled={saving || !title.trim()}
        aria-label="Save name"
      >
        <Check />
      </Button>
      <Button variant="ghost" size="icon-xs" onClick={onCancel} aria-label="Cancel rename">
        <X />
      </Button>
    </div>
  )
}

function DeleteRow({
  thread,
  onConfirm,
  onCancel,
}: {
  thread: Thread
  onConfirm: () => Promise<void>
  onCancel: () => void
}) {
  const [deleting, setDeleting] = useState(false)
  const confirm = useRef<HTMLButtonElement>(null)
  useEffect(() => confirm.current?.focus(), [])

  return (
    <div
      role="alertdialog"
      aria-label={`Delete ${thread.title ?? 'this chat'}?`}
      onKeyDown={(event) => event.key === 'Escape' && onCancel()}
      className="flex flex-col gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-2 text-sm"
    >
      <p>
        Delete <span className="font-medium">{thread.title ?? 'this chat'}</span>? Its messages and
        sources are removed for good.
      </p>
      <div className="flex gap-2">
        <Button
          ref={confirm}
          variant="destructive"
          size="sm"
          disabled={deleting}
          onClick={() => {
            setDeleting(true)
            void onConfirm().finally(() => setDeleting(false))
          }}
        >
          {deleting ? 'Deleting…' : 'Delete'}
        </Button>
        <Button variant="outline" size="sm" onClick={onCancel} disabled={deleting}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

function ThreadListSkeleton() {
  return (
    <div aria-label="Loading conversations" role="status" className="flex flex-col gap-2 px-1 py-1">
      {[70, 90, 55, 80].map((width) => (
        <div
          key={width}
          className="h-7 animate-pulse rounded-md bg-muted"
          style={{ width: `${width}%` }}
        />
      ))}
    </div>
  )
}

export default function ThreadSidebar({
  threads,
  loadError,
  actionError,
  creating,
  onNewChat,
  onRetry,
  onRename,
  onDelete,
}: Props) {
  const { session } = useAuth()
  const [editing, setEditing] = useState<Editing>(null)

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r bg-muted/30">
      <div className="flex flex-col gap-3 p-3">
        <h1 className="px-1 text-lg font-semibold">Document Copilot</h1>
        <Button onClick={onNewChat} disabled={creating}>
          {creating ? 'Creating…' : 'New chat'}
        </Button>
      </div>

      <nav aria-label="Conversations" className="flex-1 overflow-y-auto px-2">
        {actionError && (
          <p role="alert" className="px-2 py-1 text-sm text-destructive">
            {actionError}
          </p>
        )}
        {loadError && (
          <div role="alert" className="flex flex-col items-start gap-2 px-2 py-1 text-sm">
            <p className="text-destructive">{loadError}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>
              Try again
            </Button>
          </div>
        )}
        {threads === null && !loadError && <ThreadListSkeleton />}
        {threads?.length === 0 && (
          <p className="px-2 py-1 text-sm text-muted-foreground">No conversations yet.</p>
        )}
        <ul className="flex flex-col gap-1">
          {threads?.map((thread) => {
            const mode = editing?.id === thread.id ? editing.mode : null
            const close = () => setEditing(null)
            return (
              <li key={thread.id}>
                {mode === 'rename' ? (
                  <RenameRow
                    thread={thread}
                    onCancel={close}
                    onSave={async (title) => {
                      const saved = await onRename(thread.id, title)
                      if (saved) close()
                      return saved
                    }}
                  />
                ) : mode === 'delete' ? (
                  <DeleteRow
                    thread={thread}
                    onCancel={close}
                    onConfirm={async () => {
                      await onDelete(thread.id)
                      close()
                    }}
                  />
                ) : (
                  <div className={cn(ROW, 'group')}>
                    <NavLink
                      to={`/chat/${thread.id}`}
                      className={({ isActive }) =>
                        cn(
                          'block min-w-0 flex-1 truncate rounded-md px-1 py-1.5 text-sm',
                          isActive && 'font-medium',
                          !thread.title && 'text-muted-foreground',
                        )
                      }
                    >
                      {thread.title ?? 'New chat'}
                    </NavLink>
                    {/* Shown on hover and whenever the row has keyboard focus. */}
                    <div className="flex opacity-0 group-focus-within:opacity-100 group-hover:opacity-100">
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        onClick={() => setEditing({ id: thread.id, mode: 'rename' })}
                        aria-label={`Rename ${thread.title ?? 'chat'}`}
                      >
                        <Pencil />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        onClick={() => setEditing({ id: thread.id, mode: 'delete' })}
                        aria-label={`Delete ${thread.title ?? 'chat'}`}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  </div>
                )}
              </li>
            )
          })}
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
