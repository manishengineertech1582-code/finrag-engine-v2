import { useEffect } from 'react'
import { AlertCircle, CheckCircle2, Clock3, Database, FileText, Loader2, Trash2 } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import type { DocumentRecord } from '@/lib/api'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useDocuments } from '@/lib/hooks/useDocuments'
import { useJobPolling } from '@/lib/hooks/useJobPolling'
import { useAuthStore } from '@/state/authStore'
import { useAppStore, type UploadEntry } from '@/state/appStore'
import { formatBytes, formatRelativeTime, humanizeDocType } from '@/lib/utils'
import { JobStatusBadge } from './JobStatusBadge'

function progressForStatus(status: UploadEntry['status']) {
  switch (status) {
    case 'uploading':
      return 22
    case 'pending':
      return 36
    case 'processing':
      return 76
    case 'completed':
      return 100
    case 'skipped':
      return 100
    case 'failed':
      return 100
    default:
      return 0
  }
}

function progressTheme(status: UploadEntry['status']) {
  if (status === 'completed') return 'bg-emerald-500'
  if (status === 'failed') return 'bg-red-500'
  if (status === 'skipped') return 'bg-slate-500'
  return 'bg-blue-500'
}

function FileRow({ upload }: { upload: UploadEntry }) {
  const updateUpload = useAppStore((state) => state.updateUpload)
  const removeUpload = useAppStore((state) => state.removeUpload)
  const queryClient = useQueryClient()

  const shouldPoll = !!upload.jobId && ['pending', 'processing'].includes(upload.status)
  const { data: jobStatus } = useJobPolling(shouldPoll ? upload.jobId : null)

  useEffect(() => {
    if (!jobStatus) return

    const patch: Partial<UploadEntry> = {
      status: jobStatus.status as UploadEntry['status'],
    }

    if (jobStatus.result) {
      patch.chunksIndexed = jobStatus.result.chunks_indexed
      patch.docType = jobStatus.result.doc_type
    }

    if (jobStatus.error) {
      patch.error = jobStatus.error
    }

    updateUpload(upload.id, patch)

    if (jobStatus.status === 'completed') {
      queryClient.invalidateQueries({ queryKey: ['health'] })
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    }
  }, [jobStatus, queryClient, updateUpload, upload.id])

  return (
    <article className="rounded-[24px] border border-[var(--color-border)] bg-black/20 p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <p className="truncate text-sm font-semibold text-white">{upload.filename}</p>
            <JobStatusBadge status={upload.status} />
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-[var(--color-text-secondary)]">
            <span>{formatBytes(upload.size)}</span>
            {upload.docType && <span>{humanizeDocType(upload.docType)}</span>}
            {upload.chunksIndexed !== undefined && <span>{upload.chunksIndexed} chunks indexed</span>}
            <span>{formatRelativeTime(upload.createdAt)}</span>
          </div>

          <Progress
            value={progressForStatus(upload.status)}
            indicatorClassName={progressTheme(upload.status)}
            className="mt-4 h-2.5 bg-black/30"
          />

          {upload.error && <p className="mt-3 text-sm text-red-300">{upload.error}</p>}
          {upload.message && upload.status === 'skipped' && (
            <p className="mt-3 text-sm text-[var(--color-text-secondary)]">{upload.message}</p>
          )}
        </div>

        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => removeUpload(upload.id)}
          aria-label={`Remove ${upload.filename} from session history`}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </article>
  )
}

function PersistedDocRow({ document }: { document: DocumentRecord }) {
  return (
    <article className="rounded-[24px] border border-[var(--color-border)] bg-black/20 p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <p className="truncate text-sm font-semibold text-white">{document.filename}</p>
            <Badge variant="success">Indexed</Badge>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-[var(--color-text-secondary)]">
            <span>{humanizeDocType(document.doc_type)}</span>
            <span>{document.chunks_indexed} chunks</span>
            <span>{formatRelativeTime(document.ingested_at)}</span>
          </div>

          <div className="mt-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)]/50 px-4 py-3 text-sm text-[var(--color-text-secondary)]">
            Persisted in the backend registry and ready for retrieval.
          </div>
        </div>

        <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 p-3 text-[var(--color-primary)]">
          <Database className="h-4 w-4" />
        </div>
      </div>
    </article>
  )
}

export function FileList() {
  const uploads = useAppStore((state) => state.uploads)
  const clearUploads = useAppStore((state) => state.clearUploads)
  const user = useAuthStore((state) => state.user)
  const { data: documentList, isLoading } = useDocuments(user?.id)

  const persistedDocuments = documentList?.documents ?? []
  const persistedFilenames = new Set(persistedDocuments.map((document) => document.filename))
  const sessionUploads = uploads.filter(
    (upload) => !(upload.status === 'completed' && persistedFilenames.has(upload.filename)),
  )

  const hasItems = sessionUploads.length > 0 || persistedDocuments.length > 0

  if (!hasItems) {
    return (
      <div className="rounded-[28px] border border-dashed border-[var(--color-border)] px-6 py-12 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-[20px] border border-[var(--color-border)] bg-black/20 text-[var(--color-text-secondary)]">
          <FileText className="h-5 w-5" />
        </div>
        <p className="mt-4 text-base font-medium text-white">No documents uploaded yet</p>
        <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">
          Upload a file above to start building the retrieval index.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2 text-sm text-[var(--color-text-secondary)]">
          <span>{persistedDocuments.length} indexed</span>
          <span className="text-slate-600">/</span>
          <span>{sessionUploads.length} session items</span>
          {isLoading && (
            <span className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-black/20 px-3 py-1.5 text-xs">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Refreshing
            </span>
          )}
        </div>

        {sessionUploads.length > 0 && (
          <Button type="button" variant="ghost" onClick={clearUploads}>
            <Trash2 className="h-4 w-4" />
            Clear session history
          </Button>
        )}
      </div>

      {sessionUploads.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <Clock3 className="h-4 w-4 text-[var(--color-primary)]" />
            Session activity
          </div>
          {sessionUploads.map((upload) => (
            <FileRow key={upload.id} upload={upload} />
          ))}
        </section>
      )}

      {persistedDocuments.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            Indexed documents
          </div>
          {persistedDocuments.map((document) => (
            <PersistedDocRow key={document.document_id} document={document} />
          ))}
        </section>
      )}

      {sessionUploads.some((upload) => upload.status === 'failed') && (
        <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-4 text-sm text-red-200">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <p>Failed uploads stay visible so they can be reviewed or dismissed without losing the rest of the timeline.</p>
          </div>
        </div>
      )}
    </div>
  )
}

