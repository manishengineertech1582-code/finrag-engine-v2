import { useMemo, useState, type ReactNode } from 'react'
import { BookOpenText, ChevronDown, Clock3, Sparkles, Target } from 'lucide-react'
import type { ChunkSource, QueryResponse } from '@/lib/api'
import { SourceCard } from '@/components/results/SourceCard'
import { Progress } from '@/components/ui/progress'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  cn,
  confidenceClasses as getConfidenceClasses,
  sourceKey,
} from '@/lib/utils'
import { StreamingText } from './StreamingText'

interface AnswerDisplayProps {
  response: QueryResponse
  question: string
}

interface SourceEntry extends ChunkSource {
  index: number
  key: string
  anchorId: string
}

interface CitationEntry {
  number: number
  fileName: string
  location: string
  source: SourceEntry | null
  key: string
}

const INLINE_SOURCE_LIMIT = 4
const SOURCE_PATTERN = /\[source:\s*([^,\]]+)\s*,\s*([^\]]+)\]/gi

function normalizeValue(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, ' ')
}

function createAnchorId(key: string, index: number): string {
  return `source-card-${index + 1}-${key.replace(/[^a-z0-9]+/g, '-')}`
}

function matchSource(fileName: string, location: string, sourceEntries: SourceEntry[]): SourceEntry | undefined {
  const normalizedFile = normalizeValue(fileName)
  const normalizedLocation = normalizeValue(location)

  return sourceEntries.find((entry) => {
    const entryFile = normalizeValue(entry.source)
    const entryLocation = normalizeValue(entry.page_or_sheet)
    return (
      (entryFile === normalizedFile || entryFile.endsWith(normalizedFile) || normalizedFile.endsWith(entryFile)) &&
      (entryLocation === normalizedLocation || entryLocation.includes(normalizedLocation) || normalizedLocation.includes(entryLocation))
    )
  })
}

function buildSourceEntries(sources: ChunkSource[]): SourceEntry[] {
  return sources.map((source, index) => {
    const key = sourceKey(source.source, source.page_or_sheet)
    return {
      ...source,
      index,
      key,
      anchorId: createAnchorId(key, index),
    }
  })
}

function buildCitationRegistry(answer: string, sourceEntries: SourceEntry[]) {
  const registry = new Map<string, CitationEntry>()
  let sequence = 1
  let match: RegExpExecArray | null
  const pattern = new RegExp(SOURCE_PATTERN)

  while ((match = pattern.exec(answer)) !== null) {
    const fileName = match[1].trim()
    const location = match[2].trim()
    const matchedSource = matchSource(fileName, location, sourceEntries) ?? null
    const key = matchedSource?.key ?? sourceKey(fileName, location)

    if (!registry.has(key)) {
      registry.set(key, {
        number: sequence,
        fileName,
        location,
        source: matchedSource,
        key,
      })
      sequence += 1
    }
  }

  return registry
}

function renderBoldText(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={`${keyPrefix}-strong-${index}`} className="font-semibold text-white">
          {part.slice(2, -2)}
        </strong>
      )
    }
    return <span key={`${keyPrefix}-text-${index}`}>{part}</span>
  })
}

function renderInlineContent(
  text: string,
  citations: Map<string, CitationEntry>,
  sourceEntries: SourceEntry[],
  interactive: boolean,
  onCitationClick: (citation: CitationEntry) => void,
  keyPrefix: string,
) {
  const nodes: ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null
  let localIndex = 0
  const pattern = new RegExp(SOURCE_PATTERN)

  while ((match = pattern.exec(text)) !== null) {
    const before = text.slice(lastIndex, match.index)
    if (before) {
      nodes.push(...renderBoldText(before, `${keyPrefix}-before-${localIndex}`))
    }

    const fileName = match[1].trim()
    const location = match[2].trim()
    const source = matchSource(fileName, location, sourceEntries) ?? null
    const key = source?.key ?? sourceKey(fileName, location)
    const citation = citations.get(key) ?? {
      number: source ? source.index + 1 : citations.size + localIndex + 1,
      fileName,
      location,
      source,
      key,
    }

    const citationButton = (
      <button
        type="button"
        onClick={() => interactive && onCitationClick(citation)}
        className="mx-1 inline-flex rounded-md px-1 py-0.5 text-sm font-semibold text-blue-400 transition-colors hover:text-blue-300 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/60"
        aria-label={`Jump to source ${citation.number}`}
      >
        [{citation.number}]
      </button>
    )

    nodes.push(
      interactive ? (
        <Tooltip key={`${keyPrefix}-citation-${localIndex}`}>
          <TooltipTrigger asChild>{citationButton}</TooltipTrigger>
          <TooltipContent className="max-w-xs rounded-2xl border border-[var(--color-border)] bg-[#0f1724] p-3 text-left shadow-2xl">
            <p className="text-xs font-semibold text-white">{citation.fileName}</p>
            <p className="mt-1 text-[11px] uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">
              {citation.source?.page_or_sheet ?? citation.location}
            </p>
            <p className="mt-2 line-clamp-3 text-xs leading-5 text-slate-300">
              {citation.source?.snippet || `Reference in ${citation.location}`}
            </p>
          </TooltipContent>
        </Tooltip>
      ) : (
        <span key={`${keyPrefix}-citation-${localIndex}`} className="mx-1 inline-flex rounded-md px-1 py-0.5 text-sm font-semibold text-blue-400">
          [{citation.number}]
        </span>
      ),
    )

    lastIndex = pattern.lastIndex
    localIndex += 1
  }

  const after = text.slice(lastIndex)
  if (after) {
    nodes.push(...renderBoldText(after, `${keyPrefix}-after-${localIndex}`))
  }

  return nodes
}

function renderAnswerBlocks(
  text: string,
  citations: Map<string, CitationEntry>,
  sourceEntries: SourceEntry[],
  interactive: boolean,
  onCitationClick: (citation: CitationEntry) => void,
) {
  const normalized = text.replace(/\r/g, '')
  const lines = normalized.split('\n')
  const blocks: ReactNode[] = []
  const paragraphBuffer: string[] = []

  const flushParagraph = () => {
    if (!paragraphBuffer.length) return
    const content = paragraphBuffer.join(' ').trim()
    if (!content) {
      paragraphBuffer.length = 0
      return
    }

    blocks.push(
      <p key={`paragraph-${blocks.length}`} className="text-base leading-7 text-[var(--color-text-primary)]">
        {renderInlineContent(content, citations, sourceEntries, interactive, onCitationClick, `paragraph-${blocks.length}`)}
      </p>,
    )

    paragraphBuffer.length = 0
  }

  lines.forEach((rawLine) => {
    const line = rawLine.trim()

    if (!line) {
      flushParagraph()
      return
    }

    if (line.startsWith('### ')) {
      flushParagraph()
      blocks.push(
        <h3 key={`heading-${blocks.length}`} className="pt-2 text-lg font-semibold tracking-tight text-white">
          {line.replace(/^###\s+/, '')}
        </h3>,
      )
      return
    }

    if (/^[-*]\s+/.test(line)) {
      flushParagraph()
      blocks.push(
        <div key={`bullet-${blocks.length}`} className="flex gap-3 text-base leading-7 text-[var(--color-text-primary)]">
          <span className="mt-[11px] h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400" />
          <div>
            {renderInlineContent(line.replace(/^[-*]\s+/, ''), citations, sourceEntries, interactive, onCitationClick, `bullet-${blocks.length}`)}
          </div>
        </div>,
      )
      return
    }

    if (/^\d+\.\s+/.test(line)) {
      flushParagraph()
      const [marker, ...rest] = line.split(/\s+/)
      blocks.push(
        <div key={`ordered-${blocks.length}`} className="flex gap-3 text-base leading-7 text-[var(--color-text-primary)]">
          <span className="min-w-6 font-semibold text-blue-400">{marker}</span>
          <div>
            {renderInlineContent(rest.join(' '), citations, sourceEntries, interactive, onCitationClick, `ordered-${blocks.length}`)}
          </div>
        </div>,
      )
      return
    }

    paragraphBuffer.push(line)
  })

  flushParagraph()

  return blocks.length ? blocks : [<p key="empty" className="text-base leading-7 text-[var(--color-text-primary)]">No answer returned.</p>]
}

export function AnswerDisplay({ response, question }: AnswerDisplayProps) {
  const [showAllSources, setShowAllSources] = useState(false)
  const [showDetails, setShowDetails] = useState(false)
  const [activeSourceKey, setActiveSourceKey] = useState<string | null>(null)

  const sourceEntries = useMemo(() => buildSourceEntries(response.sources), [response.sources])
  const citations = useMemo(() => buildCitationRegistry(response.answer, sourceEntries), [response.answer, sourceEntries])
  const visibleSources = showAllSources ? sourceEntries : sourceEntries.slice(0, INLINE_SOURCE_LIMIT)
  const hiddenSources = Math.max(0, sourceEntries.length - INLINE_SOURCE_LIMIT)
  const confidenceTheme = getConfidenceClasses(response.confidence_score)
  const confidencePercent = Math.round(response.confidence_score * 100)

  const retrievalTags = useMemo(() => {
    const tags: string[] = []
    if (response.retrieval_meta?.hybrid_search) tags.push('Hybrid')
    if (response.retrieval_meta?.multi_query) tags.push('MultiQuery')
    if ((response.retrieval_meta?.compound_clause_count ?? 1) > 1) tags.push('Focused')
    tags.push('Reranked')
    return tags
  }, [response.retrieval_meta?.compound_clause_count, response.retrieval_meta?.hybrid_search, response.retrieval_meta?.multi_query])

  const handleCitationClick = (citation: CitationEntry) => {
    if (!citation.source) return
    setActiveSourceKey(citation.key)
    const element = document.getElementById(citation.source.anchorId)
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return (
    <TooltipProvider>
      <article className="mx-auto w-full max-w-[800px] space-y-4">
        <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 px-5 py-4">
          <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-[var(--color-text-secondary)]">
            Question
          </p>
          <p className="mt-2 text-base font-medium leading-7 text-[var(--color-text-primary)]">{question}</p>
        </div>

        <div className="overflow-hidden rounded-[28px] border border-[var(--color-border)] bg-[var(--color-card)] shadow-[0_28px_70px_-42px_rgba(15,23,42,0.9)]">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] px-6 py-5">
            <div>
              <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-[var(--color-text-secondary)]">
                Answer
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {retrievalTags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full border border-[var(--color-border)] bg-black/20 px-2.5 py-1 text-[11px] font-medium text-slate-300"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>

            {response.retrieval_meta?.latency_ms != null && (
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-black/20 px-3 py-1.5 text-xs text-[var(--color-text-secondary)]">
                <Clock3 className="h-3.5 w-3.5" />
                <span>{response.retrieval_meta.latency_ms.toFixed(0)} ms</span>
              </div>
            )}
          </div>

          <div className="px-6 py-6">
            <StreamingText
              text={response.answer}
              render={(visibleText, done) => (
                <div className="space-y-4">
                  {renderAnswerBlocks(visibleText, citations, sourceEntries, done, handleCitationClick)}
                  {!done && (
                    <span className="inline-block h-[1.15em] w-[2px] animate-pulse bg-[var(--color-primary)] align-text-bottom" />
                  )}
                </div>
              )}
            />
          </div>

          <div className="border-t border-[var(--color-border)] px-6 py-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-[var(--color-text-primary)]">Confidence</p>
                <p className="mt-1 text-xs text-[var(--color-text-secondary)]">
                  Grounding score based on the retrieved supporting evidence.
                </p>
              </div>
              <div className={cn('rounded-full border px-3 py-1.5 text-sm font-semibold tabular-nums', confidenceTheme.track, confidenceTheme.text)}>
                {confidencePercent}%
              </div>
            </div>
            <Progress
              value={confidencePercent}
              indicatorClassName={confidenceTheme.bar}
              className="mt-4 h-2.5 bg-black/30"
            />
          </div>

          {sourceEntries.length > 0 && (
            <div className="border-t border-[var(--color-border)] px-6 py-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <BookOpenText className="h-4 w-4 text-[var(--color-primary)]" />
                    <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">Sources</h3>
                  </div>
                  <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
                    Click any citation to jump here and inspect the exact chunk used to answer.
                  </p>
                </div>
                <div className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-black/20 px-3 py-1.5 text-xs text-[var(--color-text-secondary)]">
                  <Target className="h-3.5 w-3.5" />
                  <span>{sourceEntries.length} evidence chunk{sourceEntries.length === 1 ? '' : 's'}</span>
                </div>
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-2">
                {visibleSources.map((source) => (
                  <SourceCard
                    key={source.chunk_id}
                    id={source.anchorId}
                    source={source}
                    index={source.index}
                    highlighted={activeSourceKey === source.key}
                  />
                ))}
              </div>

              {hiddenSources > 0 && (
                <button
                  type="button"
                  onClick={() => setShowAllSources((value) => !value)}
                  className="mt-4 inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-black/20 px-3 py-2 text-sm text-[var(--color-text-secondary)] transition-colors hover:border-slate-600 hover:text-white"
                >
                  <ChevronDown className={cn('h-4 w-4 transition-transform', showAllSources && 'rotate-180')} />
                  <span>{showAllSources ? 'Show fewer sources' : `Show ${hiddenSources} more sources`}</span>
                </button>
              )}
            </div>
          )}

          {response.retrieval_meta && (
            <div className="border-t border-[var(--color-border)] bg-black/20 px-6 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={() => setShowDetails((value) => !value)}
                  className="inline-flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-[var(--color-text-secondary)] transition-colors hover:text-white"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  <span>Retrieval details</span>
                  <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', showDetails && 'rotate-180')} />
                </button>

                {response.request_id && (
                  <span className="text-[11px] text-[var(--color-text-secondary)]">
                    Request {response.request_id.slice(0, 8)}
                  </span>
                )}
              </div>

              {showDetails && (
                <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)]/60 p-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">Queries</p>
                    <p className="mt-2 text-lg font-semibold text-white">{response.retrieval_meta.queries_generated}</p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)]/60 p-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">Candidates</p>
                    <p className="mt-2 text-lg font-semibold text-white">{response.retrieval_meta.candidates_before_rerank}</p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)]/60 p-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">After rerank</p>
                    <p className="mt-2 text-lg font-semibold text-white">{response.retrieval_meta.candidates_after_rerank}</p>
                  </div>
                  <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)]/60 p-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">Mode</p>
                    <p className="mt-2 text-sm font-semibold text-white">
                      {response.retrieval_meta.compound_clause_count && response.retrieval_meta.compound_clause_count > 1
                        ? `${response.retrieval_meta.compound_clause_count} focused clauses`
                        : retrievalTags.join(' / ')}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </article>
    </TooltipProvider>
  )
}





