import { createClient } from '@supabase/supabase-js'

import { env } from '@/lib/env'

// The single Supabase client for the whole browser app. Import this one; never call
// createClient elsewhere, because several clients would fight over the stored session.
// It is used for auth only (email sign-in). The anon key is public by design:
// what a user can reach is limited by the database's row-level security.
// Defaults are kept on purpose: the session is saved in localStorage so a reload keeps
// the user signed in, and the access token is refreshed in the background.
export const supabase = createClient(env.supabaseUrl, env.supabaseAnonKey)
