import { useCallback, useRef, useState } from 'react'
import { api, type QueryRequest, type QueryResponse } from '../api'
import { useAppStore } from '../../state/appStore'

export function useRagQuery() {
  const addRecentQuery = useAppStore((s) => s.addRecentQuery)
  const [isPending, setIsPending] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // Store the active AbortController so we can cancel previous in-flight requests.
  // useRef avoids re-renders on every new controller.
  const abortRef = useRef<AbortController | null>(null)

  const mutateAsync = useCallback(
    async (request: QueryRequest): Promise<QueryResponse> => {
      // Cancel any previous in-flight request before issuing a new one.
      // This prevents stale responses from older queries overwriting newer results.
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      setIsPending(true)
      setError(null)

      try {
        const data = await api.query(request, controller.signal)

        // Defence-in-depth: if this controller was aborted between the await
        // resolving and here (very tight race), discard the result silently.
        if (controller.signal.aborted) {
          setIsPending(false)
          return data
        }

        addRecentQuery({
          question: request.question,
          answer: data.answer,
          sources: data.sources,
          confidence: data.confidence_score,
          timestamp: new Date().toISOString(),
          retrieval_meta: data.retrieval_meta,
          request_id: data.request_id,
          latency_ms: data.retrieval_meta?.latency_ms ?? null,
        })

        return data
      } catch (err) {
        // Axios throws CanceledError when AbortSignal fires.
        // This is an intentional cancellation, not a user-visible failure.
        if (err instanceof Error && err.name === 'CanceledError') {
          setIsPending(false)
          throw err
        }
        const e = err instanceof Error ? err : new Error('Query failed')
        setError(e)
        throw e
      } finally {
        // Only clear pending if this controller is still the active one.
        // If a newer request has already taken over, let that one own the state.
        if (abortRef.current === controller) {
          setIsPending(false)
        }
      }
    },
    [addRecentQuery],
  )

  return { mutateAsync, isPending, error }
}
