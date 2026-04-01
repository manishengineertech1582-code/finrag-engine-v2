import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Files, Search, LogOut, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/state/authStore'
import { supabase } from '@/lib/supabase'
import { Button } from '@/components/ui/button'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard', exact: true },
  { to: '/ingest', icon: Files, label: 'Documents' },
  { to: '/query', icon: Search, label: 'Query' },
]

export function Sidebar() {
  const { user, clearSession } = useAuthStore()

  const handleSignOut = async () => {
    await supabase?.auth.signOut()
    clearSession()
  }

  return (
    <aside className="border-b border-slate-800/80 bg-[#0a0f16]/95 lg:sticky lg:top-0 lg:h-screen lg:w-[272px] lg:shrink-0 lg:border-b-0 lg:border-r lg:border-slate-800/80">
      <div className="flex h-full flex-col px-4 py-4 lg:px-5 lg:py-6">
        <div className="flex items-center gap-3 rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 shadow-[0_18px_40px_-28px_rgba(59,130,246,0.8)]">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-500/15 text-blue-300">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-semibold tracking-tight text-slate-100">FinRAG</p>
            <p className="text-xs text-slate-400">Enterprise retrieval workspace</p>
          </div>
        </div>

        <div className="mt-8 hidden text-[11px] font-medium uppercase tracking-[0.24em] text-slate-500 lg:block">
          Workspace
        </div>

        <nav className="mt-4 flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">
          {navItems.map(({ to, icon: Icon, label, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              className={({ isActive }) =>
                cn(
                  'group flex min-w-fit items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition-all duration-150 lg:min-w-0',
                  isActive
                    ? 'bg-blue-500/12 text-blue-200 shadow-[0_14px_32px_-26px_rgba(59,130,246,0.75)] ring-1 ring-blue-500/20'
                    : 'text-slate-400 hover:bg-slate-900/80 hover:text-slate-100',
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="mt-6 rounded-2xl border border-slate-800 bg-slate-950/60 p-4 text-sm text-slate-400 lg:mt-8">
          <p className="text-sm font-semibold text-slate-100">Built for live demos</p>
          <p className="mt-2 leading-6">
            Fast retrieval, grounded answers, and a clean query workflow designed for enterprise walkthroughs.
          </p>
        </div>

        {user && (
          <div className="mt-6 rounded-2xl border border-slate-800 bg-slate-950/60 p-4 lg:mt-auto">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-900 text-sm font-semibold text-slate-100 ring-1 ring-slate-700">
                {user.email?.[0]?.toUpperCase() ?? 'U'}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-slate-100">{user.email}</p>
                <p className="text-xs text-slate-500">Signed in</p>
              </div>
            </div>
            <Button variant="secondary" className="mt-4 w-full justify-center" onClick={handleSignOut}>
              <LogOut className="h-4 w-4" />
              Logout
            </Button>
          </div>
        )}
      </div>
    </aside>
  )
}
