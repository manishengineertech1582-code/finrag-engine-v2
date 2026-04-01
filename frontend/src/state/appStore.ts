import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ChunkSource, RetrievalMeta } from '../lib/api'

export interface UploadEntry {
  id: string
  filename: string
  size: number
  status: 'uploading' | 'pending' | 'processing' | 'completed' | 'failed' | 'skipped'
  jobId: string | null
  createdAt: string
  message?: string
  error?: string
  chunksIndexed?: number
  docType?: string
}

export interface RecentQuery {
  question: string
  answer: string
  sources: ChunkSource[]
  confidence: number
  timestamp: string
  retrieval_meta?: RetrievalMeta | null
  request_id?: string | null
  latency_ms?: number | null
}

export const HISTORY_LIMIT = 5

interface AppState {
  uploads: UploadEntry[]
  recentQueries: RecentQuery[]
  totalQueriesCount: number
  addUpload: (entry: UploadEntry) => void
  updateUpload: (id: string, patch: Partial<UploadEntry>) => void
  removeUpload: (id: string) => void
  addRecentQuery: (query: RecentQuery) => void
  clearUploads: () => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      uploads: [],
      recentQueries: [],
      totalQueriesCount: 0,

      addUpload: (entry) =>
        set((state) => ({ uploads: [entry, ...state.uploads].slice(0, 50) })),

      updateUpload: (id, patch) =>
        set((state) => ({
          uploads: state.uploads.map((upload) => (upload.id === id ? { ...upload, ...patch } : upload)),
        })),

      removeUpload: (id) =>
        set((state) => ({
          uploads: state.uploads.filter((upload) => upload.id !== id),
        })),

      addRecentQuery: (query) =>
        set((state) => ({
          recentQueries: [query, ...state.recentQueries].slice(0, HISTORY_LIMIT),
          totalQueriesCount: state.totalQueriesCount + 1,
        })),

      clearUploads: () => set({ uploads: [] }),
    }),
    {
      name: 'finrag-app',
      partialize: (state) => ({
        uploads: state.uploads,
        recentQueries: state.recentQueries,
        totalQueriesCount: state.totalQueriesCount,
      }),
    },
  ),
)
