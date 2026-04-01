import { useMemo, useState } from 'react'
import { Info, ShieldCheck, UploadCloud, X } from 'lucide-react'
import { DropZone } from '@/components/ingest/DropZone'
import { FileList } from '@/components/ingest/FileList'
import { useDocuments } from '@/lib/hooks/useDocuments'
import { useHealth } from '@/lib/hooks/useHealth'
import { useAuthStore } from '@/state/authStore'
import { useAppStore } from '@/state/appStore'

const OCR_NOTE_DISMISSED_KEY = 'finrag-hide-ocr-note'

export function IngestionPage() {
  const { data: health } = useHealth()
  const user = useAuthStore((state) => state.user)
  const uploads = useAppStore((state) => state.uploads)
  const { data: documents } = useDocuments(user?.id)
  const [ocrNoteDismissed, setOcrNoteDismissed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(OCR_NOTE_DISMISSED_KEY) === 'true'
  })

  const ocrUnavailable = !!health && (!health.ocr?.poppler || !health.ocr?.tesseract)
  const missingDependencies: string[] = []
  if (health && !health.ocr?.poppler) missingDependencies.push('Poppler')
  if (health && !health.ocr?.tesseract) missingDependencies.push('Tesseract')

  const hasPdfDocuments = useMemo(() => {
    const persistedPdf = (documents?.documents ?? []).some((document) => document.doc_type === 'pdf')
    const sessionPdf = uploads.some(
      (upload) => upload.docType === 'pdf' || upload.filename.toLowerCase().endsWith('.pdf'),
    )
    return persistedPdf || sessionPdf
  }, [documents?.documents, uploads])

  const showOcrNote = ocrUnavailable && hasPdfDocuments && !ocrNoteDismissed
  const persistedDocuments = documents?.documents ?? []
  const activeUploads = uploads.filter((upload) => ['uploading', 'pending', 'processing'].includes(upload.status))

  const dismissOcrNote = () => {
    setOcrNoteDismissed(true)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(OCR_NOTE_DISMISSED_KEY, 'true')
    }
  }

  return (
    <div className="page-container space-y-6 py-8">
      <section className="grid gap-4 xl:grid-cols-[1.35fr_0.9fr]">
        <div className="rounded-[32px] border border-[var(--color-border)] bg-[linear-gradient(135deg,rgba(17,24,39,0.96),rgba(11,15,20,0.92))] p-6 shadow-[0_40px_120px_-75px_rgba(59,130,246,0.7)] sm:p-8">
          <div className="inline-flex h-14 w-14 items-center justify-center rounded-[22px] border border-blue-500/25 bg-blue-500/10 text-blue-300">
            <UploadCloud className="h-6 w-6" />
          </div>
          <h2 className="mt-5 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Upload and index documents with live visibility.
          </h2>
          <p className="mt-4 max-w-2xl text-base leading-7 text-[var(--color-text-secondary)]">
            Drag in PDFs, spreadsheets, DOCX files, or flat text and watch ingestion progress in real time. The page is optimized for low-friction demo flows and clear operational feedback.
          </p>
        </div>

        <div className="surface-card rounded-[32px] p-6">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 p-3 text-[var(--color-primary)]">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <p className="text-lg font-semibold text-white">Workspace summary</p>
              <p className="text-sm text-[var(--color-text-secondary)]">Current ingestion state for the signed-in user.</p>
            </div>
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">Indexed documents</p>
              <p className="mt-3 text-3xl font-semibold text-white">{persistedDocuments.length}</p>
            </div>
            <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">Active uploads</p>
              <p className="mt-3 text-3xl font-semibold text-white">{activeUploads.length}</p>
            </div>
          </div>

          <div className="mt-3 rounded-2xl border border-[var(--color-border)] bg-black/20 p-4">
            <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">OCR readiness</p>
            <p className="mt-3 text-sm font-medium text-white">
              {ocrUnavailable ? 'Optional OCR dependencies are partially unavailable' : 'OCR dependencies are available'}
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">
              {ocrUnavailable
                ? `${missingDependencies.join(' and ')} ${missingDependencies.length === 1 ? 'is' : 'are'} missing. Text PDFs still index normally.`
                : 'Scanned PDF support is enabled for this environment.'}
            </p>
          </div>
        </div>
      </section>

      {showOcrNote && (
        <section className="rounded-[28px] border border-sky-500/20 bg-sky-500/10 px-5 py-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 rounded-2xl bg-sky-500/12 p-2 text-sky-200">
                <Info className="h-4 w-4" />
              </div>
              <div>
                <p className="text-sm font-semibold text-sky-100">OCR tools are optional for scanned PDFs</p>
                <p className="mt-1 text-sm leading-6 text-sky-100/80">
                  {missingDependencies.join(' and ')} {missingDependencies.length === 1 ? 'is' : 'are'} not installed on this machine. Text-based PDFs are indexed normally. Install these tools only if you need OCR for image-only pages.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={dismissOcrNote}
              className="inline-flex h-9 w-9 items-center justify-center rounded-2xl border border-sky-500/20 text-sky-100 transition-colors hover:bg-sky-500/10"
              aria-label="Dismiss OCR note"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </section>
      )}

      <section className="surface-card rounded-[32px] p-4 sm:p-6">
        <DropZone />
      </section>

      <section className="surface-card rounded-[32px] p-4 sm:p-6">
        <div className="mb-5">
          <h3 className="text-xl font-semibold text-white">Upload history</h3>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
            Track active jobs, completed indexing, and recent ingestion outcomes in one timeline.
          </p>
        </div>
        <FileList />
      </section>
    </div>
  )
}
