import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'

export function AppLayout() {
  return (
    <div className="min-h-screen bg-[var(--color-bg)] text-[var(--color-text-primary)]">
      <div className="flex min-h-screen flex-col lg:flex-row">
        <Sidebar />
        <div className="flex min-h-screen min-w-0 flex-1 flex-col">
          <Header />
          <main className="flex-1 overflow-y-auto pb-8">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  )
}
