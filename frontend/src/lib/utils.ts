import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import type { ChunkSource } from './api'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 60) return 'just now'
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`
  return `${Math.floor(diffSec / 86400)}d ago`
}

export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str
  return `${str.slice(0, maxLength)}...`
}

export function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

export function confidenceLabel(score: number): 'high' | 'medium' | 'low' {
  if (score >= 0.8) return 'high'
  if (score >= 0.5) return 'medium'
  return 'low'
}

export function confidenceClasses(score: number) {
  const label = confidenceLabel(score)
  if (label === 'high') {
    return {
      bar: 'bg-emerald-500',
      text: 'text-emerald-300',
      track: 'bg-emerald-500/10',
    }
  }
  if (label === 'medium') {
    return {
      bar: 'bg-amber-500',
      text: 'text-amber-300',
      track: 'bg-amber-500/10',
    }
  }
  return {
    bar: 'bg-red-500',
    text: 'text-red-300',
    track: 'bg-red-500/10',
  }
}

export function estimateTextTokens(text: string): number {
  const normalized = text.trim()
  if (!normalized) return 0
  return Math.max(1, Math.ceil(normalized.length / 4))
}

export function estimateQueryTokens(question: string, answer: string, sources: ChunkSource[]): number {
  const sourcePayload = sources
    .map((source) => `${source.source} ${source.page_or_sheet} ${source.snippet ?? ''}`)
    .join(' ')
  return estimateTextTokens(question) + estimateTextTokens(answer) + Math.ceil(estimateTextTokens(sourcePayload) * 0.7)
}

export function tokenLoadLabel(tokens: number): 'lean' | 'balanced' | 'heavy' {
  if (tokens < 900) return 'lean'
  if (tokens < 2200) return 'balanced'
  return 'heavy'
}

export function tokenLoadClasses(tokens: number) {
  const label = tokenLoadLabel(tokens)
  if (label === 'lean') {
    return {
      bar: 'bg-emerald-500',
      text: 'text-emerald-300',
      badge: 'border-emerald-500/25 bg-emerald-500/12 text-emerald-300',
    }
  }
  if (label === 'balanced') {
    return {
      bar: 'bg-amber-500',
      text: 'text-amber-300',
      badge: 'border-amber-500/25 bg-amber-500/12 text-amber-300',
    }
  }
  return {
    bar: 'bg-red-500',
    text: 'text-red-300',
    badge: 'border-red-500/25 bg-red-500/12 text-red-300',
  }
}

export function sourceKey(source: string, location: string): string {
  return `${source.trim().toLowerCase()}::${location.trim().toLowerCase()}`
}

export function humanizeDocType(docType: string): string {
  if (!docType) return 'Unknown'
  if (docType === 'docx') return 'DOCX'
  if (docType === 'csv') return 'CSV'
  if (docType === 'pdf') return 'PDF'
  if (docType === 'txt') return 'TXT'
  if (docType === 'excel') return 'XLSX'
  return docType.toUpperCase()
}

export const docTypeColors: Record<string, string> = {
  pdf: 'border-red-500/20 bg-red-500/10 text-red-200',
  docx: 'border-blue-500/20 bg-blue-500/10 text-blue-200',
  excel: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-200',
  csv: 'border-cyan-500/20 bg-cyan-500/10 text-cyan-200',
  txt: 'border-zinc-500/20 bg-zinc-500/10 text-zinc-200',
  unknown: 'border-zinc-500/20 bg-zinc-500/10 text-zinc-200',
}
