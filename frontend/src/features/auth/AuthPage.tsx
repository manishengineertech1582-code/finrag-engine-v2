import { useState } from 'react'
import { Zap, Loader2, AlertCircle, CheckCircle } from 'lucide-react'
import { supabase, isSupabaseConfigured } from '@/lib/supabase'
import { useAuthStore } from '@/state/authStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

type Mode = 'signin' | 'signup'

export function AuthPage() {
  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)
  const setSession = useAuthStore((s) => s.setSession)

  const handle = async () => {
    if (loading) return

    if (!isSupabaseConfigured || !supabase) {
      setError('Supabase is not configured. Use guest mode or add frontend env variables.')
      return
    }

    if (!email.trim() || !password.trim()) {
      setError('Email and password are required.')
      return
    }

    setError('')
    setSuccess('')
    setLoading(true)

    try {
      if (mode === 'signup') {
        const { error: err } = await supabase.auth.signUp({ email, password })
        if (err) throw err
        setSuccess('Account created successfully. You can now sign in.')
      } else {
        const { data, error: err } = await supabase.auth.signInWithPassword({ email, password })
        if (err) throw err

        if (data.session) {
          setSession(data.session.user, data.session.access_token)
        } else {
          setError('Sign-in succeeded, but no session was returned.')
        }
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Authentication failed.'

      if (message.toLowerCase().includes('rate limit')) {
        setError('Too many attempts. Please wait a minute and try again.')
      } else if (message.toLowerCase().includes('invalid login credentials')) {
        setError('Invalid email or password.')
      } else {
        setError(message)
      }
    } finally {
      setLoading(false)
    }
  }

  const handleGuestSignIn = () => {
    setSession(
      {
        id: 'guest',
        email: 'guest@finrag.dev',
        aud: '',
        role: '',
        created_at: new Date().toISOString(),
        app_metadata: {},
        user_metadata: {},
      } as import('@supabase/supabase-js').User,
      ''
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-600 shadow-xl shadow-violet-600/30">
            <Zap className="h-6 w-6 text-white" strokeWidth={2.5} />
          </div>
          <h1 className="text-xl font-semibold text-zinc-100">FinRAG Engine</h1>
          <p className="mt-1 text-sm text-zinc-500">
            {mode === 'signin' ? 'Sign in to your workspace' : 'Create your account'}
          </p>
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 shadow-xl">
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">
                Email address
              </label>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                onKeyDown={(e) => e.key === 'Enter' && handle()}
                autoFocus
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-zinc-400">
                Password
              </label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                onKeyDown={(e) => e.key === 'Enter' && handle()}
              />
            </div>

            {error && (
              <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {error}
              </div>
            )}

            {success && (
              <div className="flex items-start gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-400">
                <CheckCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {success}
              </div>
            )}

            <Button className="w-full" onClick={handle} disabled={loading || !isSupabaseConfigured}>
              {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {mode === 'signin' ? 'Sign in' : 'Create account'}
            </Button>

            <p className="text-center text-xs text-zinc-500">
              {mode === 'signin' ? "Don't have an account? " : 'Already have an account? '}
              <button
                type="button"
                onClick={() => {
                  setMode(mode === 'signin' ? 'signup' : 'signin')
                  setError('')
                  setSuccess('')
                }}
                className="font-medium text-violet-400 hover:text-violet-300"
              >
                {mode === 'signin' ? 'Sign up' : 'Sign in'}
              </button>
            </p>
          </div>
        </div>

        {!isSupabaseConfigured && (
          <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
            <p className="mb-2 text-center text-xs text-zinc-500">
              Supabase not configured — continue as guest
            </p>
            <Button variant="secondary" className="w-full" onClick={handleGuestSignIn}>
              Continue as Guest
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}