import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

/**
 * Fetch the persistent document list from the backend registry.
 * This is the authoritative source of truth — survives page refreshes,
 * browser cache clears, and server restarts.
 *
 * Refetches on window focus and after every successful ingestion
 * (callers should invalidate ['documents'] on ingest completion).
 */
export function useDocuments(userId?: string) {
  return useQuery({
    queryKey: ['documents', userId],
    queryFn: () => api.getDocuments(userId),
    staleTime: 30_000,      // 30 s — fresh enough for most UX needs
    refetchOnWindowFocus: true,
  })
}
