import { Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from './state/authStore'
import { AppLayout } from './components/layout/AppLayout'
import { ErrorBoundary } from './components/ErrorBoundary'

const AuthPage = lazy(() => import('./features/auth/AuthPage').then((module) => ({ default: module.AuthPage })))
const Dashboard = lazy(() => import('./pages/Dashboard').then((module) => ({ default: module.Dashboard })))
const IngestionPage = lazy(() => import('./features/ingestion/IngestionPage').then((module) => ({ default: module.IngestionPage })))
const QueryPage = lazy(() => import('./features/rag/QueryPage').then((module) => ({ default: module.QueryPage })))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 30_000,
    },
    mutations: {
      retry: 0,
    },
  },
})

function RouteFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center px-6 py-12">
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/80 px-4 py-3 text-sm text-zinc-400">
        Loading view...
      </div>
    </div>
  )
}

function AuthGuard({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  if (!user) return <Navigate to="/auth" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/auth" element={<AuthPage />} />
              <Route
                element={
                  <AuthGuard>
                    <AppLayout />
                  </AuthGuard>
                }
              >
                <Route path="/" element={<Dashboard />} />
                <Route path="/ingest" element={<IngestionPage />} />
                <Route path="/query" element={<QueryPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
