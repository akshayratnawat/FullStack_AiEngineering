import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import PasswordInput from '@/components/auth/PasswordInput'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { checkAccess } from '@/lib/account'
import { describeError } from '@/lib/chat'
import { supabase } from '@/lib/supabase'

type Mode = 'login' | 'signup'

const COPY = {
  login: {
    title: 'Sign in',
    description: 'Use your Driftwood email and password to continue.',
    submit: 'Sign in',
    switchText: "Don't have an account?",
    switchLink: { to: '/signup', label: 'Sign up' },
  },
  signup: {
    title: 'Create an account',
    description: 'Sign up with your Driftwood email address and a password.',
    submit: 'Sign up',
    switchText: 'Already have an account?',
    switchLink: { to: '/login', label: 'Sign in' },
  },
} as const

export default function AuthForm({ mode }: { mode: Mode }) {
  const copy = COPY[mode]
  const navigate = useNavigate()
  // ProtectedRoute leaves the page the user was heading to in the navigation state.
  const location = useLocation()
  const destination = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? '/'
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const email = String(form.get('email')).trim()
    const password = String(form.get('password'))

    setError(null)
    setNotice(null)
    setSubmitting(true)

    // Signed in: ask the backend whether this account may use the app before going in.
    async function enter() {
      try {
        const refused = await checkAccess()
        if (refused) setError(refused)
        else navigate(destination, { replace: true })
      } catch (failure) {
        setError(describeError(failure))
      }
    }

    if (mode === 'login') {
      const { error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) setError(error.message)
      else await enter()
    } else {
      const { data, error } = await supabase.auth.signUp({ email, password })
      if (error) setError(error.message)
      // With email confirmation on, there is no session until the user clicks the link.
      else if (data.session) await enter()
      else setNotice('Check your email to confirm your account, then sign in.')
    }

    setSubmitting(false)
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{copy.title}</CardTitle>
          <CardDescription>{copy.description}</CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" name="email" type="email" autoComplete="email" required />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Password</Label>
              <PasswordInput
                id="password"
                name="password"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                minLength={8}
                required
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            {notice && <p className="text-sm text-muted-foreground">{notice}</p>}
          </CardContent>
          <CardFooter className="mt-6 flex flex-col gap-3">
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? 'Please wait…' : copy.submit}
            </Button>
            <p className="text-sm text-muted-foreground">
              {copy.switchText}{' '}
              <Link to={copy.switchLink.to} className="underline underline-offset-4">
                {copy.switchLink.label}
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </main>
  )
}
