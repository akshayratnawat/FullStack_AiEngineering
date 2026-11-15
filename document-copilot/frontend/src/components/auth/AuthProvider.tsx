import type { Session } from '@supabase/supabase-js'
import { useEffect, useState, type ReactNode } from 'react'

import { AuthContext } from '@/components/auth/auth-context'
import { supabase } from '@/lib/supabase'

// Keeps the current Supabase session in one place so any component can read it
// with useAuth(). The listener fires once right away with the stored session
// (or null), and again on every sign-in, sign-out and token refresh.
export default function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession)
      setLoading(false)
    })
    return () => subscription.unsubscribe()
  }, [])

  return <AuthContext value={{ loading, session }}>{children}</AuthContext>
}
