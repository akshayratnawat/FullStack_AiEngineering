// What the backend says about the signed-in account. Anyone with a confirmed email may sign up and
// look around; only approved accounts may ask live questions (each answer spends model tokens).

import { api } from '@/lib/api'
import { ApiError } from '@/lib/http'
import { supabase } from '@/lib/supabase'

export interface Account {
  id: string
  email: string
  can_ask: boolean // false for a visitor: the recorded examples work, live questions do not
}

export const getAccount = () => api.get<Account>('/me')

// null when the account may use the app; otherwise the reason it may not, and it is signed out.
export async function checkAccess(): Promise<string | null> {
  try {
    await api.get('/me')
    return null
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      await supabase.auth.signOut()
      return error.message // the backend's reason: the email is not confirmed yet
    }
    throw error
  }
}
