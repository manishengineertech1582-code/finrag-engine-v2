import { Activity, AlertCircle, Database, Gauge, Sparkles } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { Progress } from '@/components/ui/progress'
import { useHealth } from '@/lib/hooks/useHealth'
import { estimateQueryTokens, formatCompactNumber, tokenLoadClasses, tokenLoadLabel, truncate } from '@/lib/utils'
import { useAppStore } from '@/state/appStore'

const PAGE_COPY: Record<string, { title: string; description: string }> = {
  '/': {
    title: 'Dashboard',
    description: 'Monitor indexing health, recent activity, and product readiness at a glance.',
  },
  '/ingest': {
    title: 'Documents',
    description: 'Upload, monitor, and validate the files powering your retrieval pipeline.',
  },
  '/query': {
    title: 'Query Workspace',
    description: 'Ask grounded questions, inspect evidence, and keep retrieval lean and precise.',
  },
}

export function Header() {
  const { pathname } = useLocation()
  const { data: health, isLoading, isError } = useHealth()
  const latestQuery = useAppStore((state) => state.recentQueries[0])

  const page = PAGE_COPY[pathname] ?? PAGE_COPY['/']
  const tokenEstimate = latestQuery
    ? estimateQueryTokens(latestQuery.question, latestQuery.answer, latestQuery.sources)
    : 0
  const tokenClasses = tokenLoadClasses(tokenEstimate)
  const tokenLabel = tokenLoadLabel(tokenEstimate)
  const tokenProgress = Math.min(100, Math.round((tokenEstimate / 2600) * 100))

  return (
    <header className="border-b border-[var(--color-border)]/90 bg-[var(--color-bg)]/80 backdrop-blur-xl">
      <div className="page-container py-5">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.22em] text-[var(--color-text-secondary)]">
              <Sparkles className="h-3.5 w-3.5 text-[var(--color-primary)]" />
              <span>Enterprise Workspace</span>
            </div>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-[var(--color-text-primary)] sm:text-[28px]">
              {page.title}
            </h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--color-text-secondary)]">
              {page.description}
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:min-w-[620px] xl:grid-cols-[1.25fr_1fr]">
            <section className="surface-card rounded-2xl p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">
                    Token Load
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-2xl font-semibold tabular-nums text-[var(--color-text-primary)]">
                      {tokenEstimate > 0 ? formatCompactNumber(tokenEstimate) : '--'}
                    </span>
                    <span className={`rounded-full border px-2 py-1 text-[11px] font-medium capitalize ${tokenClasses.badge}`}>
                      {tokenEstimate > 0 ? tokenLabel : 'idle'}
                    </span>
                  </div>
                </div>
                <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 p-2 text-[var(--color-primary)]">
                  <Gauge className="h-4 w-4" />
                </div>
              </div>

              <Progress
                value={tokenEstimate > 0 ? tokenProgress : 0}
                indicatorClassName={tokenClasses.bar}
                className="mt-4 h-2.5 bg-black/30"
              />

              <p className="mt-3 text-xs leading-5 text-[var(--color-text-secondary)]">
                {latestQuery
                  ? `Estimated from the latest response: ${truncate(latestQuery.question, 72)}`
                  : 'Token visibility stays live once a query is answered, helping you keep retrieval cost-effective.'}
              </p>
            </section>

            <section className="surface-card rounded-2xl p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">
                    System Status
                  </p>
                  {isLoading && (
                    <div className="mt-3 flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                      <span className="h-2 w-2 rounded-full bg-slate-500 animate-pulse" />
                      <span>Checking backend health...</span>
                    </div>
                  )}
                  {isError && (
                    <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-red-500/25 bg-red-500/10 px-3 py-1.5 text-sm text-red-300">
                      <AlertCircle className="h-3.5 w-3.5" />
                      <span>Backend offline</span>
                    </div>
                  )}
                  {health && (
                    <>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <div
                          className={health.vectorstore_loaded
                            ? 'inline-flex items-center gap-2 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 py-1.5 text-sm text-emerald-300'
                            : 'inline-flex items-center gap-2 rounded-full border border-amber-500/25 bg-amber-500/10 px-3 py-1.5 text-sm text-amber-300'}
                        >
                          <Activity className="h-3.5 w-3.5" />
                          <span>{health.vectorstore_loaded ? 'Live and queryable' : 'Waiting for documents'}</span>
                        </div>
                        {health.environment !== 'production' && (
                          <span className="rounded-full border border-[var(--color-border)] bg-black/20 px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">
                            {health.environment}
                          </span>
                        )}
                      </div>

                      <div className="mt-4 flex items-center gap-3 rounded-2xl border border-[var(--color-border)] bg-black/20 px-3 py-3">
                        <div className="rounded-xl bg-white/5 p-2 text-[var(--color-primary)]">
                          <Database className="h-4 w-4" />
                        </div>
                        <div>
                          <p className="text-xs text-[var(--color-text-secondary)]">Indexed vectors</p>
                          <p className="text-base font-semibold tabular-nums text-[var(--color-text-primary)]">
                            {health.indexed_vectors.toLocaleString()}
                          </p>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </header>
  )
}
