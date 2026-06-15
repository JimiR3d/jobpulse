import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import {
  LayoutDashboard, Database, User, BarChart2,
  Zap, LogOut, Menu, X
} from 'lucide-react'
import { supabase } from './lib/supabase'
import Dashboard from './pages/Dashboard'
import Sources from './pages/Sources'
import Profile from './pages/Profile'
import Analytics from './pages/Analytics'

// ── Auth page ─────────────────────────────────────────────────
function AuthPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState('login') // login | signup
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    setMessage('')

    try {
      if (mode === 'signup') {
        const { error } = await supabase.auth.signUp({ email, password })
        if (error) throw error
        setMessage('Check your email for a confirmation link!')
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      {/* Background glow */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-96 h-96
          rounded-full bg-brand-600/10 blur-3xl" />
      </div>

      <div className="w-full max-w-md animate-in">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-3">
            <div className="w-9 h-9 rounded-xl bg-brand-600 flex items-center justify-center shadow-lg shadow-brand-900/50">
              <Zap size={18} className="text-white" />
            </div>
            <span className="text-2xl font-bold text-gray-100">JobPulse</span>
          </div>
          <p className="text-gray-400 text-sm">Your AI-powered remote job radar</p>
        </div>

        <div className="card">
          {/* Mode tabs */}
          <div className="flex items-center gap-1 mb-6 bg-gray-800 p-1 rounded-lg">
            <button
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-all ${
                mode === 'login' ? 'bg-gray-700 text-gray-100' : 'text-gray-500 hover:text-gray-300'
              }`}
              onClick={() => setMode('login')}
            >
              Sign In
            </button>
            <button
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-all ${
                mode === 'signup' ? 'bg-gray-700 text-gray-100' : 'text-gray-500 hover:text-gray-300'
              }`}
              onClick={() => setMode('signup')}
            >
              Sign Up
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-xs font-medium text-gray-400 block mb-1.5">Email</label>
              <input
                type="email"
                className="input"
                placeholder="you@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-400 block mb-1.5">Password</label>
              <input
                type="password"
                className="input"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                minLength={6}
              />
            </div>

            {error && (
              <p className="text-sm text-red-400 bg-red-900/20 border border-red-800/50 rounded-lg p-3">
                {error}
              </p>
            )}
            {message && (
              <p className="text-sm text-emerald-400 bg-emerald-900/20 border border-emerald-800/50 rounded-lg p-3">
                {message}
              </p>
            )}

            <button
              type="submit"
              className="btn btn-primary w-full justify-center py-2.5"
              disabled={loading}
            >
              {loading ? 'Please wait…' : mode === 'login' ? 'Sign In' : 'Create Account'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-gray-600 mt-6">
          AI-powered · $0/month · Worldwide remote only
        </p>
      </div>
    </div>
  )
}

// ── Sidebar ───────────────────────────────────────────────────
const NAV_LINKS = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/sources',   icon: Database,        label: 'Sources' },
  { to: '/profile',   icon: User,            label: 'Profile' },
  { to: '/analytics', icon: BarChart2,       label: 'Analytics' },
]

function Sidebar({ onSignOut, onClose, isMobile }) {
  return (
    <aside className={`flex flex-col gap-1 py-5 px-3 h-full ${isMobile ? '' : ''}`}>
      {/* Logo */}
      <div className="flex items-center justify-between px-2 mb-6">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center shadow-md shadow-brand-900/50">
            <Zap size={14} className="text-white" />
          </div>
          <span className="text-base font-bold text-gray-100">JobPulse</span>
        </div>
        {isMobile && (
          <button onClick={onClose} className="btn btn-ghost btn-sm p-1.5">
            <X size={16} />
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-0.5 flex-1">
        {NAV_LINKS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            onClick={isMobile ? onClose : undefined}
            className={({ isActive }) => isActive ? 'nav-link-active' : 'nav-link'}
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Sign out */}
      <button
        onClick={onSignOut}
        className="nav-link text-gray-500 hover:text-red-400 mt-2"
      >
        <LogOut size={16} />
        Sign Out
      </button>
    </aside>
  )
}

// ── Main App ──────────────────────────────────────────────────
export default function App() {
  const [session, setSession] = useState(undefined) // undefined = loading
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => setSession(session))
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_, session) => {
      setSession(session)
    })
    return () => subscription.unsubscribe()
  }, [])

  async function handleSignOut() {
    await supabase.auth.signOut()
  }

  // Loading state
  if (session === undefined) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="spinner w-8 h-8" />
      </div>
    )
  }

  // Unauthenticated
  if (!session) return <AuthPage />

  // Authenticated — show main app
  return (
    <BrowserRouter>
      <div className="flex min-h-screen">
        {/* Desktop sidebar */}
        <div className="hidden md:flex flex-col w-[var(--sidebar-width)] bg-gray-950 border-r border-gray-800 shrink-0 sticky top-0 h-screen">
          <Sidebar onSignOut={handleSignOut} />
        </div>

        {/* Mobile overlay */}
        {mobileOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
            onClick={() => setMobileOpen(false)}
          />
        )}

        {/* Mobile sidebar */}
        <div className={`fixed inset-y-0 left-0 z-50 w-64 bg-gray-950 border-r border-gray-800
          transition-transform duration-250 md:hidden
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}`}>
          <Sidebar onSignOut={handleSignOut} onClose={() => setMobileOpen(false)} isMobile />
        </div>

        {/* Main content */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Mobile top bar */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800 md:hidden sticky top-0 z-30 bg-gray-950/90 backdrop-blur-sm">
            <button
              onClick={() => setMobileOpen(true)}
              className="btn btn-ghost btn-sm p-1.5"
            >
              <Menu size={18} />
            </button>
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded bg-brand-600 flex items-center justify-center">
                <Zap size={11} className="text-white" />
              </div>
              <span className="text-sm font-bold text-gray-100">JobPulse</span>
            </div>
          </div>

          <main className="flex-1">
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/sources" element={<Sources />} />
              <Route path="/profile" element={<Profile />} />
              <Route path="/analytics" element={<Analytics />} />
            </Routes>
          </main>
        </div>
      </div>
    </BrowserRouter>
  )
}
