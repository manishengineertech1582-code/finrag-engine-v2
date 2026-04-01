import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 30_000,   // refresh every 30s
    retry: 2,
    staleTime: 15_000,
  })
}
