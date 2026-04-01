import { useQuery } from '@tanstack/react-query'
import { api, type JobStatusResponse } from '../api'

const TERMINAL_STATUSES = new Set(['completed', 'failed'])

export function useJobPolling(jobId: string | null) {
  return useQuery<JobStatusResponse>({
    queryKey: ['job', jobId],
    queryFn: () => api.getJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (!status || TERMINAL_STATUSES.has(status)) return false
      return 1500  // poll every 1.5s while pending/processing
    },
    retry: 3,
  })
}
