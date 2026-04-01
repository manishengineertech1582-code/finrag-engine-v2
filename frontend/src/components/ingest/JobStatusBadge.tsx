import { Badge } from '@/components/ui/badge'
import type { UploadEntry } from '@/state/appStore'

interface Props {
  status: UploadEntry['status']
}

export function JobStatusBadge({ status }: Props) {
  switch (status) {
    case 'uploading':
      return <Badge variant="processing">Uploading</Badge>
    case 'pending':
      return <Badge variant="processing">Queued</Badge>
    case 'processing':
      return <Badge variant="processing">Indexing</Badge>
    case 'completed':
      return <Badge variant="success">Indexed</Badge>
    case 'failed':
      return <Badge variant="error">Failed</Badge>
    case 'skipped':
      return <Badge variant="default">Skipped</Badge>
    default:
      return null
  }
}
