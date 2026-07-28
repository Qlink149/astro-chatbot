import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, setToken } from '@/lib/api'
import { Input } from '@/components/ui/input'
import { toast } from 'sonner'
import { Loader2, MoonStar, Eye, EyeOff } from 'lucide-react'

const BRAND_PANEL_GRADIENT = `
  radial-gradient(ellipse 66% 56% at 92% 6%, rgba(194,155,60,0.55) 0%, rgba(140,104,38,0.30) 26%, rgba(41,33,115,0.32) 52%, transparent 70%),
  radial-gradient(ellipse 64% 54% at 82% 60%, rgba(23,20,71,0.99) 0%, rgba(15,13,52,0.9) 30%, rgba(8,7,30,0.58) 58%, transparent 78%),
  radial-gradient(ellipse 44% 36% at 90% 96%, rgba(74,61,158,0.62) 0%, rgba(41,33,115,0.38) 44%, transparent 64%),
  radial-gradient(ellipse 30% 24% at 15% 82%, rgba(194,155,60,0.16) 0%, transparent 56%),
  radial-gradient(ellipse 50% 44% at 50% 50%, rgba(12,10,40,0.24) 0%, transparent 65%),
  linear-gradient(142deg, #050414 0%, #0b0a26 26%, #171447 62%, #060515 100%)
`

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await login({ username, password })
      setToken(res.token)
      localStorage.setItem('agent_username', username)
      toast.success('Logged in successfully')
      navigate('/')
    } catch (err) {
      toast.error(err.message || 'Login failed')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-svh overflow-y-auto grid grid-cols-1 md:grid-cols-2">
      {/* Brand Side */}
      <div
        className="hidden md:flex flex-col justify-between text-white p-12 lg:p-20 relative overflow-hidden"
        style={{ background: BRAND_PANEL_GRADIENT }}
      >
        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <div
              className="flex h-10 w-10 items-center justify-center rounded-xl shadow-lg"
              style={{
                background: 'linear-gradient(135deg, #d9bc72 0%, #c29b3c 40%, #292173 100%)',
                boxShadow: '0 8px 24px rgba(194,155,60,0.28)',
              }}
            >
              <MoonStar className="h-5 w-5 text-white" />
            </div>
            <span className="text-xl font-bold tracking-tight">Samara by Clara</span>
          </div>
        </div>

        <div className="relative z-10">
          <h2 className="text-4xl lg:text-5xl font-bold tracking-tight mb-4 font-display">
            Your jyotish bot, under your control.
          </h2>
          <p className="text-lg text-white/60 max-w-md">
            See every seeker, read their kundli conversations, and monitor readings — all in one place.
          </p>
        </div>
      </div>

      {/* Form Side */}
      <div
        className="relative flex items-center justify-center p-8 lg:p-12"
        style={{ background: 'var(--bg)' }}
      >
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background: 'radial-gradient(ellipse 60% 50% at 80% 20%, rgb(var(--lavender-rgb) / 0.18) 0%, transparent 70%)',
          }}
        />

        <div className="relative w-full max-w-[400px] space-y-8">
          {/* Mobile logo */}
          <div className="flex md:hidden items-center gap-3">
            <div
              className="flex h-9 w-9 items-center justify-center rounded-xl"
              style={{
                background: 'linear-gradient(135deg, #d9bc72 0%, #c29b3c 40%, #292173 100%)',
              }}
            >
              <MoonStar className="h-4 w-4 text-white" />
            </div>
            <span className="text-lg font-bold" style={{ color: 'var(--text)' }}>Samara by Clara</span>
          </div>

          <div className="space-y-2">
            <span
              className="inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.20em]"
              style={{
                background: 'rgb(var(--royal-rgb) / 0.08)',
                border: '1px solid rgb(var(--royal-rgb) / 0.14)',
                color: 'var(--royal)',
              }}
            >
              Dashboard
            </span>
            <h1 className="text-3xl font-bold tracking-tight font-display" style={{ color: 'var(--text)' }}>
              Welcome back
            </h1>
            <p className="text-muted-foreground">Sign in to access the dashboard.</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium" style={{ color: 'var(--text)' }}>Username</label>
                <Input
                  type="text"
                  placeholder="Enter your username"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  required
                  className="login-input brand-input h-11 rounded-xl"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium" style={{ color: 'var(--text)' }}>Password</label>
                <div className="relative">
                  <Input
                    type={showPassword ? 'text' : 'password'}
                    placeholder="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    required
                    className="login-input brand-input h-11 rounded-xl pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 transition-colors text-muted-foreground hover:text-foreground"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="login-btn h-12 w-full rounded-xl text-sm font-semibold text-white outline-none transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-60"
              style={{
                background: 'linear-gradient(135deg, #4a3d9e 0%, #292173 50%, #171447 100%)',
                boxShadow: '0 12px 32px rgba(41,33,115,0.32)',
              }}
            >
              {loading ? (
                <span className="inline-flex items-center justify-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" /> Signing in...
                </span>
              ) : (
                'Sign In'
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
