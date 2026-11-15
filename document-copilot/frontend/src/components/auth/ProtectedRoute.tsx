import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '@/components/auth/auth-context'

// A layout route: wrap the pages that need a signed-in user inside it.
// This only decides what the browser shows; the backend still rejects
// requests without a valid token (get_current_user).
export default function ProtectedRoute() {
  const { loading, session } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading…</p>
      </main>
    )
  }

  // Remember where the user was going, so sign-in can send them back there.
  if (!session) return <Navigate to="/login" replace state={{ from: location }} />

  return <Outlet />
}
