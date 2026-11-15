import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { supabase } from '@/lib/supabase'

// Placeholder: shows who is signed in, so we can see that sign-in worked.
// It becomes the chat list later; route protection is a separate step.
export default function HomePage() {
  // undefined = still loading, null = signed out, string = the signed-in email
  const [email, setEmail] = useState<string | null | undefined>(undefined)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setEmail(data.session?.user.email ?? null))
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) =>
      setEmail(session?.user.email ?? null),
    )
    return () => subscription.unsubscribe()
  }, [])

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-3xl font-semibold">Document Copilot</h1>
      {email === undefined && <p className="text-muted-foreground">Loading…</p>}
      {email === null && (
        <p className="text-muted-foreground">
          You are not signed in.{' '}
          <Link to="/login" className="underline underline-offset-4">
            Sign in
          </Link>
        </p>
      )}
      {typeof email === 'string' && (
        <>
          <p className="text-muted-foreground">Signed in as {email}</p>
          <Button variant="outline" onClick={() => supabase.auth.signOut()}>
            Sign out
          </Button>
        </>
      )}
    </main>
  )
}
