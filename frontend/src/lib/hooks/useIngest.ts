import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { useAppStore } from '../../state/appStore'

export function useIngest() {
  const queryClient = useQueryClient()
  const addUpload = useAppStore((s) => s.addUpload)
  const updateUpload = useAppStore((s) => s.updateUpload)

  return useMutation({
    mutationFn: async ({ file, userId }: { file: File; userId?: string }) => {
      // Optimistic: add to upload list immediately
      const uploadId = `upload_${Date.now()}_${file.name}`
      addUpload({
        id: uploadId,
        filename: file.name,
        size: file.size,
        status: 'uploading',
        jobId: null,
        createdAt: new Date().toISOString(),
      })

      try {
        const job = await api.ingest(file, userId)
        updateUpload(uploadId, {
          status: job.status === 'skipped' ? 'skipped' : 'pending',
          jobId: job.job_id || null,
          message: job.message,
        })
        return { uploadId, job }
      } catch (err) {
        updateUpload(uploadId, { status: 'failed', error: (err as Error).message })
        throw err
      }
    },
    onSuccess: () => {
      // Invalidate health (vector count) and documents (persistent list)
      queryClient.invalidateQueries({ queryKey: ['health'] })
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })
}
