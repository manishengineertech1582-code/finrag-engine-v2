/**
 * Central API client - all requests go through here.
 */

import axios, { AxiosError } from 'axios'

export interface ChunkSource {
  source: string
  page_or_sheet: string
  doc_type: string
  chunk_id: string
  user_id: string | null
  snippet: string | null
}

export interface RetrievalMeta {
  queries_generated: number
  candidates_before_rerank: number
  candidates_after_rerank: number
  hybrid_search: boolean
  multi_query: boolean
  latency_ms: number | null
  multi_intent_detected?: boolean
  compound_clause_count?: number
}

export interface QueryResponse {
  answer: string
  sources: ChunkSource[]
  total_chunks_retrieved: number
  confidence_score: number
  retrieval_meta: RetrievalMeta | null
  request_id: string | null
}

export interface QueryRequest {
  question: string
  user_id?: string
  source_filter?: string
  doc_type_filter?: string
  top_k?: number
}

export interface IngestJobResponse {
  job_id: string
  status: 'pending' | 'skipped'
  message: string
}

export interface JobStatusResponse {
  job_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  created_at: string
  filename?: string
  user_id?: string
  file_hash?: string
  started_at?: string
  completed_at?: string
  failed_at?: string
  error?: string
  result?: {
    filename: string
    doc_type: string
    chunks_indexed: number
    user_id?: string
  }
}

export interface OcrDependencies {
  poppler: boolean
  tesseract: boolean
}

export interface HealthResponse {
  status: string
  vectorstore_loaded: boolean
  indexed_vectors: number
  environment: string
  ocr: OcrDependencies
}

export interface DocumentRecord {
  document_id: string
  filename: string
  doc_type: string
  chunks_indexed: number
  ingested_at: string
  user_id: string | null
  file_hash: string | null
}

export interface DocumentListResponse {
  documents: DocumentRecord[]
  total: number
}

const client = axios.create({
  baseURL: '',
  timeout: 120_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('finrag_access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string }>) => {
    const detail = error.response?.data?.detail
    const message = typeof detail === 'string'
      ? detail
      : error.message || 'An unexpected error occurred.'
    return Promise.reject(new Error(message))
  },
)

export const api = {
  health: async (): Promise<HealthResponse> => {
    const { data } = await client.get<HealthResponse>('/health')
    return data
  },

  ingest: async (file: File, userId?: string): Promise<IngestJobResponse> => {
    const form = new FormData()
    form.append('file', file)
    if (userId) form.append('user_id', userId)
    const { data } = await client.post<IngestJobResponse>('/api/ingest', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  getJob: async (jobId: string): Promise<JobStatusResponse> => {
    const { data } = await client.get<JobStatusResponse>(`/api/jobs/${jobId}`)
    return data
  },

  query: async (request: QueryRequest, signal?: AbortSignal): Promise<QueryResponse> => {
    const { data } = await client.post<QueryResponse>('/api/ask', request, { signal })
    return data
  },

  getDocuments: async (userId?: string): Promise<DocumentListResponse> => {
    const params = userId ? { user_id: userId } : {}
    const { data } = await client.get<DocumentListResponse>('/api/documents', { params })
    return data
  },
}
