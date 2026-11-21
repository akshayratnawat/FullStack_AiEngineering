// Checks, right after sign-in, that this account may use the app. Supabase lets anyone sign up;
// the backend only serves Driftwood addresses that have been confirmed.

import { api } from '@/lib/api'
import { ApiError } from '@/lib/http'
import { supabase } from '@/lib/supabase'

// null when the account may use the app; otherwise the reason it may not, and it is signed out.
export async function checkAccess(): Promise<string | null> {
  try {
    await api.get('/me')
    return null
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      await supabase.auth.signOut()
      return error.message // the backend's reason: not a Driftwood address, or not confirmed yet
    }
    throw error
  }
}
