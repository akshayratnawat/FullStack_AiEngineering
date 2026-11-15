import type { Session } from '@supabase/supabase-js'
import { createContext, useContext } from 'react'

interface AuthState {
  // True until Supabase has told us whether anyone is signed in.
  loading: boolean
  session: Session | null
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const state = useContext(AuthContext)
  if (!state) throw new Error('useAuth must be used inside <AuthProvider>.')
  return state
}
