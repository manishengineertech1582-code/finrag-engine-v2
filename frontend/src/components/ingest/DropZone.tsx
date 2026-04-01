import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { AlertCircle, FileText, Sparkles, UploadCloud } from 'lucide-react'
import { cn, formatBytes } from '@/lib/utils'
import { useIngest } from '@/lib/hooks/useIngest'
import { useAuthStore } from '@/state/authStore'

const ACCEPTED_TYPES = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
  'text/csv': ['.csv'],
  'text/plain': ['.txt'],
}
const MAX_SIZE = 50 * 1024 * 1024

interface DropZoneProps {
  onUploaded?: () => void
}

export function DropZone({ onUploaded }: DropZoneProps) {
  const { mutateAsync: upload, isPending } = useIngest()
  const user = useAuthStore((state) => state.user)
  const [rejections, setRejections] = useState<string[]>([])

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      setRejections([])
      for (const file of acceptedFiles) {
        await upload({ file, userId: user?.id }).catch(() => {
          // Upload state is handled in the shared store.
        })
      }
      onUploaded?.()
    },
    [onUploaded, upload, user?.id],
  )

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    onDropRejected: (items) => {
      setRejections(items.map((item) => `${item.file.name}: ${item.errors[0]?.message}`))
    },
    accept: ACCEPTED_TYPES,
    maxSize: MAX_SIZE,
    multiple: true,
  })

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={cn(
          'relative overflow-hidden rounded-[28px] border border-dashed p-8 text-center transition-all duration-200 sm:p-10',
          isDragActive && !isDragReject
            ? 'border-blue-500/50 bg-blue-500/10 shadow-[0_0_0_1px_rgba(59,130,246,0.18),0_26px_60px_-40px_rgba(59,130,246,0.65)]'
            : isDragReject
            ? 'border-red-500/40 bg-red-500/10'
            : 'border-[var(--color-border)] bg-[linear-gradient(180deg,rgba(17,24,39,0.82),rgba(11,15,20,0.82))] hover:border-slate-600/80 hover:bg-[linear-gradient(180deg,rgba(17,24,39,0.92),rgba(11,15,20,0.92))]',
          isPending && 'pointer-events-none opacity-70',
        )}
      >
        <input {...getInputProps()} />

        <div className="absolute inset-x-0 top-0 h-24 bg-[radial-gradient(circle_at_top,rgba(59,130,246,0.16),transparent_60%)]" />

        <div className="relative mx-auto flex max-w-2xl flex-col items-center">
          <div
            className={cn(
              'flex h-16 w-16 items-center justify-center rounded-[24px] border text-blue-300 transition-colors',
              isDragActive && !isDragReject
                ? 'border-blue-500/35 bg-blue-500/15'
                : 'border-[var(--color-border)] bg-black/20',
            )}
          >
            {isDragReject ? <AlertCircle className="h-7 w-7 text-red-300" /> : <UploadCloud className="h-7 w-7" />}
          </div>

          <p className="mt-6 text-2xl font-semibold tracking-tight text-white">
            {isDragActive ? (isDragReject ? 'This file type is not supported' : 'Drop files to start indexing') : 'Drop documents here or click to browse'}
          </p>
          <p className="mt-3 max-w-xl text-sm leading-6 text-[var(--color-text-secondary)]">
            Upload PDFs, DOCX files, spreadsheets, CSVs, and text files. The pipeline indexes text immediately and surfaces live job status below.
          </p>

          <div className="mt-6 flex flex-wrap justify-center gap-2">
            {['PDF', 'DOCX', 'XLSX', 'CSV', 'TXT'].map((format) => (
              <span
                key={format}
                className="rounded-full border border-[var(--color-border)] bg-black/20 px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)]"
              >
                {format}
              </span>
            ))}
            <span className="rounded-full border border-[var(--color-border)] bg-black/20 px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)]">
              Max {formatBytes(MAX_SIZE)}
            </span>
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-3 text-xs text-[var(--color-text-secondary)]">
            <span className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-black/20 px-3 py-1.5">
              <Sparkles className="h-3.5 w-3.5 text-[var(--color-primary)]" />
              Live job polling
            </span>
            <span className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-black/20 px-3 py-1.5">
              <FileText className="h-3.5 w-3.5 text-[var(--color-primary)]" />
              Grounded retrieval ready after indexing
            </span>
          </div>

          {isPending && (
            <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-blue-500/25 bg-blue-500/10 px-4 py-2 text-sm text-blue-200">
              <span className="h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
              Uploading and queueing files...
            </div>
          )}
        </div>
      </div>

      {rejections.length > 0 && (
        <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-4 text-sm text-red-200">
          {rejections.map((rejection, index) => (
            <p key={`${rejection}-${index}`}>{rejection}</p>
          ))}
        </div>
      )}
    </div>
  )
}
