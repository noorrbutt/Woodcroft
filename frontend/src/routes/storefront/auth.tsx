/** Sign in, register, password reset and email verification. */

import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { ApiError, post } from '@/lib/api'
import { Button, Checkbox, Field, Input, Spinner } from '@/components/ui'
import { useAuthStore } from '@/features/auth/store'
import type { ApiMessage } from '@/lib/types'

function Shell({ title, subtitle, children }: {
  title: string
  subtitle?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="wc-container flex min-h-[70vh] items-center justify-center py-16">
      <div className="w-full max-w-sm">
        <h1 className="text-3xl">{title}</h1>
        {subtitle && <p className="mt-2 text-sm text-muted">{subtitle}</p>}
        {children}
      </div>
    </div>
  )
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="border border-[var(--wc-danger)] bg-danger-bg px-3 py-2 text-sm text-[var(--wc-danger)]"
    >
      {message}
    </div>
  )
}

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const login = useAuthStore((state) => state.login)
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = params.get('next') ?? '/account'

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(email, password, remember)
      toast.success('Welcome back')
      navigate(next, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not sign you in')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Shell
      title="Sign in"
      subtitle={<>New here? <Link to="/register" className="wc-link">Create an account</Link></>}
    >
      <form onSubmit={submit} className="mt-8 space-y-4">
        {error && <ErrorBox message={error} />}
        <Field label="Email" id="email">
          <Input id="email" type="email" autoComplete="email" required
                 value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password" id="password">
          <Input id="password" type="password" autoComplete="current-password" required
                 value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <div className="flex items-center justify-between">
          <Checkbox label="Remember me" checked={remember}
                    onChange={(e) => setRemember(e.target.checked)} />
          <Link to="/forgot-password" className="text-xs text-muted hover:text-ink">
            Forgot password?
          </Link>
        </div>
        <Button type="submit" fullWidth loading={loading}>Sign in</Button>
      </form>

      <div className="mt-8 border border-line bg-sunken p-4 text-xs text-muted">
        <p className="mb-2 font-medium text-ink">Demo accounts</p>
        <ul className="space-y-1 font-mono text-[0.7rem]">
          <li>admin@woodcroft.pk / woodcroft-admin</li>
          <li>staff@woodcroft.pk / woodcroft-staff</li>
          <li>customer@woodcroft.pk / woodcroft-demo</li>
        </ul>
      </div>
    </Shell>
  )
}

export function RegisterPage() {
  const [form, setForm] = useState({ full_name: '', email: '', password: '', phone: '' })
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const register = useAuthStore((state) => state.register)
  const navigate = useNavigate()

  const bind = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((current) => ({ ...current, [key]: event.target.value }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setFieldErrors({})
    setLoading(true)
    try {
      await register({
        full_name: form.full_name,
        email: form.email,
        password: form.password,
        phone: form.phone || undefined,
      })
      toast.success('Account created. Check your email to confirm it.')
      navigate('/account', { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        const fields = err.fieldErrors
        setFieldErrors(fields)
        if (Object.keys(fields).length === 0) setError(err.message)
      } else {
        setError('Could not create your account')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Shell
      title="Create an account"
      subtitle={<>Already have one? <Link to="/login" className="wc-link">Sign in</Link></>}
    >
      <form onSubmit={submit} className="mt-8 space-y-4">
        {error && <ErrorBox message={error} />}
        <Field label="Full name" id="name" error={fieldErrors.full_name} required>
          <Input id="name" required autoComplete="name"
                 value={form.full_name} onChange={bind('full_name')} />
        </Field>
        <Field label="Email" id="email" error={fieldErrors.email} required>
          <Input id="email" type="email" required autoComplete="email"
                 value={form.email} onChange={bind('email')} />
        </Field>
        <Field label="Mobile" id="phone" error={fieldErrors.phone}
               hint="Pakistani mobile, for delivery updates">
          <Input id="phone" type="tel" placeholder="0300 1234567" autoComplete="tel"
                 value={form.phone} onChange={bind('phone')} />
        </Field>
        <Field label="Password" id="password" error={fieldErrors.password}
               hint="At least 8 characters" required>
          <Input id="password" type="password" required autoComplete="new-password"
                 value={form.password} onChange={bind('password')} />
        </Field>
        <Button type="submit" fullWidth loading={loading}>Create account</Button>
        <p className="text-xs text-faint">
          By creating an account you agree to our{' '}
          <Link to="/page/terms" className="wc-link">Terms</Link> and{' '}
          <Link to="/page/privacy" className="wc-link">Privacy Policy</Link>.
        </p>
      </form>
    </Shell>
  )
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [loading, setLoading] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    try {
      await post<ApiMessage>('/auth/forgot-password', { email })
    } catch {
      /* deliberately ignored */
    } finally {
      // The same outcome either way. Reporting whether the address exists
      // would turn this into an account finder.
      setSent(true)
      setLoading(false)
    }
  }

  if (sent) {
    return (
      <Shell title="Check your email">
        <p className="mt-3 text-sm text-muted">
          If {email} is registered with us, a reset link is on its way. It
          expires in two hours.
        </p>
        <p className="mt-6 border border-line bg-sunken p-3 text-xs text-faint">
          No SMTP is configured here, so the message went to the outbox. An
          admin can read it under Admin, Notifications.
        </p>
        <Link to="/login" className="wc-btn wc-btn-outline mt-8">Back to sign in</Link>
      </Shell>
    )
  }

  return (
    <Shell title="Reset your password" subtitle="We will email you a link to set a new one.">
      <form onSubmit={submit} className="mt-8 space-y-4">
        <Field label="Email" id="email">
          <Input id="email" type="email" required autoComplete="email"
                 value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Button type="submit" fullWidth loading={loading}>Send reset link</Button>
        <Link to="/login" className="block text-center text-xs text-muted hover:text-ink">
          Back to sign in
        </Link>
      </form>
    </Shell>
  )
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await post<ApiMessage>('/auth/reset-password', { token, password })
      toast.success('Password reset. Please sign in.')
      navigate('/login', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not reset your password')
    } finally {
      setLoading(false)
    }
  }

  if (!token) {
    return (
      <Shell title="That link is not valid">
        <p className="mt-3 text-sm text-muted">The reset link is missing its token.</p>
        <Link to="/forgot-password" className="wc-btn wc-btn-primary mt-8">
          Request a new one
        </Link>
      </Shell>
    )
  }

  return (
    <Shell title="Set a new password">
      <form onSubmit={submit} className="mt-8 space-y-4">
        {error && <ErrorBox message={error} />}
        <Field label="New password" id="password" hint="At least 8 characters">
          <Input id="password" type="password" required autoComplete="new-password"
                 value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <p className="text-xs text-faint">
          Resetting your password signs you out on every other device.
        </p>
        <Button type="submit" fullWidth loading={loading}>Reset password</Button>
      </form>
    </Shell>
  )
}

export function VerifyEmailPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const [state, setState] = useState<'working' | 'done' | 'failed'>('working')

  useEffect(() => {
    if (!token) {
      setState('failed')
      return
    }
    post<ApiMessage>('/auth/verify-email', { token })
      .then(() => setState('done'))
      .catch(() => setState('failed'))
  }, [token])

  return (
    <div className="wc-container flex min-h-[70vh] flex-col items-center justify-center text-center">
      {state === 'working' && <Spinner className="size-6 text-faint" />}
      {state === 'done' && (
        <>
          <h1 className="text-3xl">Email confirmed</h1>
          <p className="mt-3 text-sm text-muted">Thank you. Your account is ready.</p>
          <Link to="/account" className="wc-btn wc-btn-primary mt-8">Go to your account</Link>
        </>
      )}
      {state === 'failed' && (
        <>
          <h1 className="text-3xl">That link did not work</h1>
          <p className="mt-3 max-w-sm text-sm text-muted">
            It may have expired or already been used. You can request a new one
            from your account settings.
          </p>
          <Link to="/account" className="wc-btn wc-btn-outline mt-8">Go to your account</Link>
        </>
      )}
    </div>
  )
}
