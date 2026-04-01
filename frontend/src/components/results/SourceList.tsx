import { SourceCard } from './SourceCard'
import type { ChunkSource } from '@/lib/api'

interface SourceListProps {
  sources: ChunkSource[]
}

export function SourceList({ sources }: SourceListProps) {
  if (sources.length === 0) {
    return (
      <p className="text-xs text-zinc-500 italic">No source chunks retrieved.</p>
    )
  }

  return (
    <div className="space-y-1.5">
      {sources.map((src, i) => (
        <SourceCard key={src.chunk_id || `${src.source}-${i}`} source={src} index={i} />
      ))}
    </div>
  )
}
