import { Link } from 'react-router-dom'
import { Activity, ArrowRight, Database, FileUp, Files, MessageSquareText, Sparkles, Timer } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useDocuments } from '@/lib/hooks/useDocuments'
import { useHealth } from '@/lib/hooks/useHealth'
import { confidenceLabel, formatCompactNumber, formatRelativeTime, truncate } from '@/lib/utils'
import { useAuthStore } from '@/state/authStore'
import { useAppStore } from '@/state/appStore'

function MetricCard({
  label,
  value,
  description,
  icon: Icon,
}: {
  label: string
  value: string
  description: string
  icon: LucideIcon
}) {
  return (
    <div className="surface-card rounded-[28px] p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">
            {label}
          </p>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-white">{value}</p>
          <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{description}</p>
        </div>
        <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 p-3 text-[var(--color-primary)]">
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </div>
  )
}

export function Dashboard() {
  const { data: health } = useHealth()
  const user = useAuthStore((state) => state.user)
  const { data: documents } = useDocuments(user?.id)
  const uploads = useAppStore((state) => state.uploads)
  const recentQueries = useAppStore((state) => state.recentQueries)
  const totalQueriesCount = useAppStore((state) => state.totalQueriesCount)

  const persistedDocuments = documents?.documents ?? []
  const inFlightUploads = uploads.filter((upload) => ['uploading', 'pending', 'processing'].includes(upload.status))
  const totalChunks = persistedDocuments.reduce((sum, document) => sum + document.chunks_indexed, 0)

  return (
    <div className="page-container space-y-8 py-8">
      <section className="grid gap-4 xl:grid-cols-[1.45fr_0.95fr]">
        <div className="rounded-[32px] border border-[var(--color-border)] bg-[linear-gradient(135deg,rgba(17,24,39,0.96),rgba(11,15,20,0.92))] p-6 shadow-[0_40px_120px_-75px_rgba(59,130,246,0.7)] sm:p-8">
          <Badge variant="accent">Live enterprise workspace</Badge>
          <h2 className="mt-5 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Production-grade retrieval, ready for demos and daily use.
          </h2>
          <p className="mt-4 max-w-2xl text-base leading-7 text-[var(--color-text-secondary)]">
            Monitor indexing readiness, upload flow, and question activity from one place. The entire UI is optimized for fast walkthroughs and high-signal answers.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link to="/query">
                <MessageSquareText className="h-4 w-4" />
                Open query workspace
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link to="/ingest">
                <FileUp className="h-4 w-4" />
                Upload documents
              </Link>
            </Button>
          </div>
        </div>

        <div className="surface-card rounded-[32px] p-6 sm:p-7">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 p-3 text-[var(--color-primary)]">
              <Activity className="h-5 w-5" />
            </div>
            <div>
              <p className="text-lg font-semibold text-white">Pipeline health</p>
              <p className="text-sm text-[var(--color-text-secondary)]">Current system readiness for querying.</p>
            </div>
          </div>

          <div className="mt-6 grid gap-3">
            <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">Query engine</p>
              <div className="mt-3 flex items-center gap-2">
                <span className={health?.vectorstore_loaded ? 'h-2.5 w-2.5 rounded-full bg-emerald-400' : 'h-2.5 w-2.5 rounded-full bg-amber-400'} />
                <span className="text-sm font-medium text-white">
                  {health?.vectorstore_loaded ? 'Ready for grounded answers' : 'Waiting on indexed files'}
                </span>
              </div>
            </div>

            <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">In-flight uploads</p>
              <p className="mt-3 text-2xl font-semibold text-white">{inFlightUploads.length}</p>
              <p className="mt-1 text-sm text-[var(--color-text-secondary)]">Files currently uploading or indexing.</p>
            </div>

            <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">Latest activity</p>
              <p className="mt-3 text-sm font-medium text-white">
                {recentQueries[0]?.question ? truncate(recentQueries[0].question, 68) : 'No queries yet'}
              </p>
              <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
                {recentQueries[0]?.timestamp ? formatRelativeTime(recentQueries[0].timestamp) : 'Ask the first question to start the timeline.'}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Documents"
          value={formatCompactNumber(persistedDocuments.length)}
          description="Persisted files available for retrieval in the current workspace."
          icon={Files}
        />
        <MetricCard
          label="Vectors"
          value={health ? health.indexed_vectors.toLocaleString() : '--'}
          description={`${formatCompactNumber(totalChunks)} chunk references currently loaded into the vector store.`}
          icon={Database}
        />
        <MetricCard
          label="Queries"
          value={formatCompactNumber(totalQueriesCount)}
          description="Total query count tracked locally for this session history."
          icon={MessageSquareText}
        />
        <MetricCard
          label="Latency posture"
          value={recentQueries[0]?.latency_ms != null ? `${Math.round(recentQueries[0].latency_ms)} ms` : '--'}
          description="Most recent answer latency so you can keep demos moving quickly."
          icon={Timer}
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="surface-card rounded-[28px] p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-xl font-semibold text-white">Recent documents</h3>
              <p className="mt-1 text-sm text-[var(--color-text-secondary)]">Latest indexed files and chunk coverage.</p>
            </div>
            <Button asChild variant="ghost">
              <Link to="/ingest">
                Manage documents
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>

          <div className="mt-5 space-y-3">
            {persistedDocuments.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-[var(--color-border)] px-5 py-10 text-center text-sm text-[var(--color-text-secondary)]">
                No indexed documents yet. Upload files to activate retrieval.
              </div>
            ) : (
              persistedDocuments.slice(0, 5).map((document) => (
                <div key={document.document_id} className="rounded-2xl border border-[var(--color-border)] bg-black/20 px-4 py-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <p className="min-w-0 flex-1 truncate text-sm font-semibold text-white">{document.filename}</p>
                    <Badge variant="success">{document.chunks_indexed} chunks</Badge>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-[var(--color-text-secondary)]">
                    <span>{document.doc_type.toUpperCase()}</span>
                    <span>{formatRelativeTime(document.ingested_at)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="surface-card rounded-[28px] p-6">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 p-3 text-[var(--color-primary)]">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-white">Recent answers</h3>
              <p className="mt-1 text-sm text-[var(--color-text-secondary)]">Confidence and evidence footprint for the latest asks.</p>
            </div>
          </div>

          <div className="mt-5 space-y-3">
            {recentQueries.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-[var(--color-border)] px-5 py-10 text-center text-sm text-[var(--color-text-secondary)]">
                The query timeline will appear here after the first grounded answer.
              </div>
            ) : (
              recentQueries.slice(0, 5).map((query, index) => {
                const confidence = confidenceLabel(query.confidence)
                const badgeVariant = confidence === 'high' ? 'success' : confidence === 'medium' ? 'warning' : 'error'

                return (
                  <div key={`${query.request_id ?? query.timestamp}-${index}`} className="rounded-2xl border border-[var(--color-border)] bg-black/20 px-4 py-4">
                    <div className="flex items-start gap-3">
                      <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 px-2.5 py-1 text-xs font-semibold text-[var(--color-text-secondary)]">
                        {index + 1}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold leading-6 text-white">{truncate(query.question, 88)}</p>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <Badge variant={badgeVariant}>{Math.round(query.confidence * 100)}% confidence</Badge>
                          <Badge variant="default">{query.sources.length} sources</Badge>
                          <span className="text-xs text-[var(--color-text-secondary)]">{formatRelativeTime(query.timestamp)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
