import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, FileSearch, FileSpreadsheet, FileText, Sheet } from 'lucide-react'
import { cn, docTypeColors, humanizeDocType, truncate } from '@/lib/utils'
import type { ChunkSource } from '@/lib/api'

interface SourceCardProps {
  source: ChunkSource
  index: number
  id?: string
  highlighted?: boolean
}

function SourceIcon({ docType }: { docType: string }) {
  if (docType === 'excel' || docType === 'csv') {
    return <FileSpreadsheet className="h-4 w-4" />
  }
  if (docType === 'pdf') {
    return <FileSearch className="h-4 w-4" />
  }
  if (docType === 'docx') {
    return <FileText className="h-4 w-4" />
  }
  return <Sheet className="h-4 w-4" />
}

export function SourceCard({ source, index, id, highlighted = false }: SourceCardProps) {
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (highlighted) {
      setExpanded(true)
    }
  }, [highlighted])

  const metadata = useMemo(
    () => [
      { label: 'Location', value: source.page_or_sheet || 'Document context' },
      { label: 'Type', value: humanizeDocType(source.doc_type) },
      { label: 'Chunk', value: truncate(source.chunk_id, 18) },
    ],
    [source.chunk_id, source.doc_type, source.page_or_sheet],
  )

  return (
    <article
      id={id}
      className={cn(
        'group rounded-2xl border bg-[var(--color-card)]/88 transition-all duration-200',
        highlighted
          ? 'border-blue-500/40 shadow-[0_0_0_1px_rgba(59,130,246,0.18),0_20px_45px_-32px_rgba(59,130,246,0.75)]'
          : 'border-[var(--color-border)] hover:border-slate-600/80 hover:bg-[var(--color-card)]',
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-start gap-3 p-4 text-left"
        aria-expanded={expanded}
      >
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-[var(--color-border)] bg-black/20 text-[var(--color-primary)]">
          <SourceIcon docType={source.doc_type} />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full border border-[var(--color-border)] bg-black/20 px-2 text-[11px] font-semibold text-[var(--color-text-secondary)]">
              {index + 1}
            </span>
            <p className="truncate text-sm font-semibold text-[var(--color-text-primary)]">
              {truncate(source.source, 46)}
            </p>
            <span className={cn('rounded-full border px-2.5 py-1 text-[11px] font-medium', docTypeColors[source.doc_type] ?? docTypeColors.unknown)}>
              {humanizeDocType(source.doc_type)}
            </span>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--color-text-secondary)]">
            <span>{source.page_or_sheet || 'Document context'}</span>
            {source.user_id && <span className="tabular-nums">Scoped</span>}
          </div>

          <p className={cn('mt-3 text-sm leading-6 text-slate-300', expanded ? 'line-clamp-none' : 'line-clamp-4')}>
            {source.snippet || 'No snippet available for this chunk.'}
          </p>
        </div>

        <ChevronDown
          className={cn(
            'mt-1 h-4 w-4 shrink-0 text-[var(--color-text-secondary)] transition-transform duration-200',
            expanded && 'rotate-180',
          )}
        />
      </button>

      {expanded && (
        <div className="border-t border-[var(--color-border)] px-4 py-4">
          <div className="grid gap-3 sm:grid-cols-3">
            {metadata.map((item) => (
              <div key={item.label} className="rounded-2xl border border-[var(--color-border)] bg-black/20 p-3">
                <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">
                  {item.label}
                </p>
                <p className="mt-2 break-all text-sm text-[var(--color-text-primary)]">{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </article>
  )
}
