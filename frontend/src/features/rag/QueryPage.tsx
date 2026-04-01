import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertCircle, ArrowRight, FileUp, Search, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { AnswerDisplay } from '@/components/query/AnswerDisplay'
import { QueryInput, type QueryOptions } from '@/components/query/QueryInput'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { useHealth } from '@/lib/hooks/useHealth'
import { useRagQuery } from '@/lib/hooks/useQuery'
import { useAuthStore } from '@/state/authStore'
import { useAppStore } from '@/state/appStore'

const SUGGESTED_PROMPTS = [
  'Summarize the most important facts in my uploaded documents',
  'List the highest-risk items and show the evidence for each one',
  'Compare the key entities mentioned across my latest files',
  'What are the most relevant definitions or concepts in this corpus?',
]

const LOADING_STEPS = [
  'Retrieving hybrid evidence from the index',
  'Reranking the best supporting chunks',
  'Writing a grounded answer with citations',
] as const

interface PendingRequest {
  question: string
  options: QueryOptions
}

function LoadingAnswer({ pendingQuestion, step }: { pendingQuestion: string | null; step: string }) {
  return (
    <div className="mx-auto w-full max-w-[800px] space-y-4">
      {pendingQuestion && (
        <div className="rounded-2xl border border-[var(--color-border)] bg-black/20 px-5 py-4">
          <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-[var(--color-text-secondary)]">
            Question
          </p>
          <p className="mt-2 text-base font-medium leading-7 text-[var(--color-text-primary)]">{pendingQuestion}</p>
        </div>
      )}

      <div className="rounded-[28px] border border-[var(--color-border)] bg-[var(--color-card)] px-6 py-6 shadow-[0_28px_70px_-42px_rgba(15,23,42,0.9)]">
        <div className="flex items-center gap-2 text-sm font-medium text-blue-300">
          <span className="h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
          <span>{step}</span>
        </div>
        <div className="mt-5 space-y-3">
          <Skeleton className="h-4 w-full rounded-full" />
          <Skeleton className="h-4 w-[92%] rounded-full" />
          <Skeleton className="h-4 w-[84%] rounded-full" />
          <Skeleton className="h-4 w-[72%] rounded-full" />
        </div>
        <div className="mt-8 grid gap-3 md:grid-cols-2">
          <Skeleton className="h-32 rounded-2xl" />
          <Skeleton className="h-32 rounded-2xl" />
        </div>
      </div>
    </div>
  )
}

export function QueryPage() {
  const { mutateAsync: query, isPending, error } = useRagQuery()
  const { data: health } = useHealth()
  const user = useAuthStore((state) => state.user)
  const recentQueries = useAppStore((state) => state.recentQueries)
  const timeline = useMemo(() => [...recentQueries].reverse(), [recentQueries])
  const bottomRef = useRef<HTMLDivElement>(null)

  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const [lastRequest, setLastRequest] = useState<PendingRequest | null>(null)
  const [loadingStep, setLoadingStep] = useState(0)

  const noIndex = !health?.vectorstore_loaded

  useEffect(() => {
    if (!isPending) {
      setLoadingStep(0)
      setPendingQuestion(null)
      return
    }

    const first = setTimeout(() => setLoadingStep(1), 850)
    const second = setTimeout(() => setLoadingStep(2), 1900)

    return () => {
      clearTimeout(first)
      clearTimeout(second)
    }
  }, [isPending])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [timeline.length, isPending])

  const handleQuery = async (question: string, options: QueryOptions) => {
    setPendingQuestion(question)
    setLastRequest({ question, options })

    await query({
      question,
      user_id: user?.id,
      top_k: options.top_k,
      doc_type_filter: options.doc_type_filter,
    })
  }

  const handleRetry = async () => {
    if (!lastRequest) return
    await handleQuery(lastRequest.question, lastRequest.options)
  }

  return (
    <div className="page-container flex h-full flex-col gap-6 py-8">
      {timeline.length === 0 && !isPending ? (
        <section className="mx-auto flex w-full max-w-[980px] flex-1 flex-col items-center justify-center gap-8 rounded-[32px] border border-[var(--color-border)] bg-[linear-gradient(180deg,rgba(17,24,39,0.92),rgba(11,15,20,0.92))] px-6 py-12 text-center shadow-[0_40px_120px_-70px_rgba(59,130,246,0.65)] sm:px-10 sm:py-16">
          <div className="inline-flex h-16 w-16 items-center justify-center rounded-[24px] border border-blue-500/30 bg-blue-500/10 text-blue-300">
            <Sparkles className="h-7 w-7" />
          </div>

          <div className="max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
              Ask anything about your documents
            </h2>
            <p className="mt-4 text-base leading-7 text-[var(--color-text-secondary)]">
              Perplexity-style grounded answers with fast retrieval, confidence scoring, and source inspection built directly into the workflow.
            </p>
          </div>

          {noIndex ? (
            <div className="w-full max-w-[760px] rounded-3xl border border-amber-500/20 bg-amber-500/10 px-6 py-5 text-left">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-3">
                  <AlertCircle className="mt-1 h-5 w-5 text-amber-300" />
                  <div>
                    <p className="text-sm font-semibold text-amber-200">Upload documents to start querying</p>
                    <p className="mt-1 text-sm leading-6 text-amber-100/80">
                      The query workspace is ready, but the index is still empty for this user scope.
                    </p>
                  </div>
                </div>
                <Button asChild variant="secondary">
                  <Link to="/ingest">
                    <FileUp className="h-4 w-4" />
                    Upload documents
                  </Link>
                </Button>
              </div>
            </div>
          ) : (
            <div className="w-full max-w-[760px]">
              <QueryInput onSubmit={handleQuery} isLoading={isPending} compact={false} />
            </div>
          )}

          {!noIndex && (
            <div className="flex w-full max-w-[900px] flex-wrap justify-center gap-3">
              {SUGGESTED_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => void handleQuery(prompt, { top_k: 8 })}
                  className="rounded-full border border-[var(--color-border)] bg-black/20 px-4 py-2 text-sm text-[var(--color-text-secondary)] transition-colors hover:border-blue-500/35 hover:text-white"
                >
                  {prompt}
                </button>
              ))}
            </div>
          )}
        </section>
      ) : (
        <>
          <div className="mx-auto flex w-full max-w-[980px] flex-1 flex-col gap-6">
            {timeline.map((entry, index) => (
              <AnswerDisplay
                key={`${entry.request_id ?? entry.timestamp}-${index}`}
                question={entry.question}
                response={{
                  answer: entry.answer,
                  sources: entry.sources,
                  total_chunks_retrieved: entry.sources.length,
                  confidence_score: entry.confidence,
                  retrieval_meta: entry.retrieval_meta ?? null,
                  request_id: entry.request_id ?? null,
                }}
              />
            ))}

            {isPending && <LoadingAnswer pendingQuestion={pendingQuestion} step={LOADING_STEPS[loadingStep]} />}

            {error && !isPending && (
              <div className="mx-auto w-full max-w-[800px] rounded-3xl border border-red-500/20 bg-red-500/10 px-6 py-5">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-start gap-3">
                    <AlertCircle className="mt-1 h-5 w-5 text-red-300" />
                    <div>
                      <p className="text-sm font-semibold text-red-200">Answer generation failed</p>
                      <p className="mt-1 text-sm leading-6 text-red-100/80">{error.message}</p>
                    </div>
                  </div>
                  {lastRequest && (
                    <Button type="button" variant="secondary" onClick={() => void handleRetry()}>
                      <ArrowRight className="h-4 w-4" />
                      Retry
                    </Button>
                  )}
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          <div className="sticky bottom-0 z-10 mx-auto w-full max-w-[980px] pb-4">
            <div className="rounded-[32px] border border-[var(--color-border)] bg-[var(--color-bg)]/88 p-3 shadow-[0_30px_80px_-55px_rgba(15,23,42,0.98)] backdrop-blur-xl">
              {noIndex && (
                <div className="mb-3 flex items-center gap-2 rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
                  <Search className="h-4 w-4" />
                  <span>Index is empty. Upload documents before sending new queries.</span>
                </div>
              )}
              <QueryInput onSubmit={handleQuery} isLoading={isPending} disabled={noIndex} compact />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
