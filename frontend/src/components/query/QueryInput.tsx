import { useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { ArrowRight, Loader2, Settings2, SlidersHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn, estimateTextTokens, tokenLoadClasses, tokenLoadLabel } from '@/lib/utils'

interface QueryInputProps {
  onSubmit: (question: string, options: QueryOptions) => Promise<void> | void
  isLoading: boolean
  disabled?: boolean
  compact?: boolean
}

export interface QueryOptions {
  top_k: number
  doc_type_filter?: string
  user_id?: string
}

const DOC_TYPES = [
  { value: '', label: 'All document types' },
  { value: 'pdf', label: 'PDF only' },
  { value: 'docx', label: 'DOCX only' },
  { value: 'excel', label: 'Excel only' },
  { value: 'csv', label: 'CSV only' },
  { value: 'txt', label: 'TXT only' },
]
const TOP_K_OPTIONS = [4, 6, 8, 12, 16]

export function QueryInput({ onSubmit, isLoading, disabled, compact = false }: QueryInputProps) {
  const [question, setQuestion] = useState('')
  const [showOptions, setShowOptions] = useState(false)
  const [topK, setTopK] = useState(8)
  const [docType, setDocType] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const estimatedPromptTokens = useMemo(() => {
    const base = estimateTextTokens(question)
    return Math.max(0, base + topK * 110)
  }, [question, topK])

  const tokenTheme = tokenLoadClasses(estimatedPromptTokens)
  const tokenLabel = tokenLoadLabel(estimatedPromptTokens)

  const resizeTextarea = () => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    const minHeight = compact ? 96 : 168
    textarea.style.height = `${Math.max(minHeight, Math.min(textarea.scrollHeight, 260))}px`
  }

  const resetInput = () => {
    setQuestion('')
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = compact ? '96px' : '168px'
    textarea.focus()
  }

  const handleSubmit = async () => {
    const trimmedQuestion = question.trim()
    if (!trimmedQuestion || disabled || isLoading) return

    try {
      await onSubmit(trimmedQuestion, {
        top_k: topK,
        doc_type_filter: docType || undefined,
      })
      resetInput()
    } catch {
      // Keep the draft so the user can refine and retry.
    }
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void handleSubmit()
    }
  }

  return (
    <div className="space-y-3">
      <div
        className={cn(
          'rounded-[28px] border bg-[#0f1724]/92 p-3 shadow-[0_26px_60px_-40px_rgba(15,23,42,0.95)] transition-all duration-200',
          disabled
            ? 'border-[var(--color-border)] opacity-70'
            : 'border-[var(--color-border)] focus-within:border-blue-500/45 focus-within:shadow-[0_0_0_1px_rgba(59,130,246,0.22),0_24px_60px_-34px_rgba(59,130,246,0.65)]',
        )}
      >
        <textarea
          ref={textareaRef}
          value={question}
          onChange={(event) => {
            setQuestion(event.target.value)
            resizeTextarea()
          }}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={disabled || isLoading}
          aria-label="Ask anything about your documents"
          placeholder={disabled ? 'Upload documents to start querying...' : 'Ask anything about your documents...'}
          className={cn(
            'w-full resize-none bg-transparent px-3 pt-3 text-[15px] leading-7 text-[var(--color-text-primary)] outline-none placeholder:text-slate-500',
            compact ? 'min-h-[96px] pb-4' : 'min-h-[168px] pb-6 text-base',
          )}
          style={{ height: compact ? '96px' : '168px' }}
        />

        <div className="mt-2 border-t border-[var(--color-border)] px-2 pt-3">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
            <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-secondary)]">
              <button
                type="button"
                onClick={() => setShowOptions((value) => !value)}
                className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-black/20 px-3 py-1.5 transition-colors hover:border-slate-600 hover:text-white"
              >
                <Settings2 className="h-3.5 w-3.5" />
                <span>{showOptions ? 'Hide options' : 'Tune retrieval'}</span>
              </button>

              <span className={cn('rounded-full border px-3 py-1.5 font-medium capitalize', tokenTheme.badge)}>
                {estimatedPromptTokens > 0 ? `Est. prompt ${estimatedPromptTokens} tokens - ${tokenLabel}` : 'Token estimate appears as you type'}
              </span>

              <span className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-black/20 px-3 py-1.5">
                <SlidersHorizontal className="h-3.5 w-3.5" />
                <span>top_k {topK}</span>
              </span>

              <span className="text-[11px] uppercase tracking-[0.18em]">Enter to send, Shift+Enter for a new line</span>
            </div>

            <Button
              type="button"
              size="lg"
              onClick={() => void handleSubmit()}
              disabled={!question.trim() || disabled || isLoading}
              className="w-full rounded-2xl xl:w-auto"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Generating answer</span>
                </>
              ) : (
                <>
                  <span>Ask</span>
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </Button>
          </div>

          {showOptions && (
            <div className="mt-3 grid gap-3 rounded-2xl border border-[var(--color-border)] bg-black/20 p-4 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">
                  Retrieval depth
                </span>
                <select
                  value={topK}
                  onChange={(event) => setTopK(Number(event.target.value))}
                  className="w-full rounded-2xl border border-[var(--color-border)] bg-[#0b111b] px-3 py-3 text-sm text-[var(--color-text-primary)] outline-none transition-colors focus:border-blue-500/50"
                >
                  {TOP_K_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      top_k {option}
                    </option>
                  ))}
                </select>
              </label>

              <label className="space-y-2">
                <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--color-text-secondary)]">
                  Source filter
                </span>
                <select
                  value={docType}
                  onChange={(event) => setDocType(event.target.value)}
                  className="w-full rounded-2xl border border-[var(--color-border)] bg-[#0b111b] px-3 py-3 text-sm text-[var(--color-text-primary)] outline-none transition-colors focus:border-blue-500/50"
                >
                  {DOC_TYPES.map((option) => (
                    <option key={option.value || 'all'} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
