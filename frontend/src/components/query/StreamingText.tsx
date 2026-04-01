import { useEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface StreamingTextProps {
  text: string
  speed?: number
  interval?: number
  onComplete?: () => void
  className?: string
  render?: (visibleText: string, done: boolean) => ReactNode
}

const MAX_ANIMATED_LENGTH = 520
const MAX_FRAMES = 24

export function StreamingText({
  text,
  speed = 16,
  interval = 14,
  onComplete,
  className,
  render,
}: StreamingTextProps) {
  const [displayed, setDisplayed] = useState('')
  const [done, setDone] = useState(false)
  const indexRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const prefersReducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

    const shouldRenderInstantly = prefersReducedMotion || text.length > MAX_ANIMATED_LENGTH

    setDisplayed('')
    setDone(false)
    indexRef.current = 0

    if (!text) {
      setDone(true)
      return
    }

    if (shouldRenderInstantly) {
      setDisplayed(text)
      setDone(true)
      onComplete?.()
      return
    }

    const chunkSize = Math.max(speed, Math.ceil(text.length / MAX_FRAMES))
    const tickMs = Math.max(10, interval)

    timerRef.current = setInterval(() => {
      indexRef.current += chunkSize
      if (indexRef.current >= text.length) {
        setDisplayed(text)
        setDone(true)
        if (timerRef.current) clearInterval(timerRef.current)
        onComplete?.()
      } else {
        setDisplayed(text.slice(0, indexRef.current))
      }
    }, tickMs)

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [text, speed, interval, onComplete])

  if (render) {
    if (done) {
      return <div className={className}>{render(text, true)}</div>
    }

    return (
      <div className={cn('relative', className)}>
        <div aria-hidden className="pointer-events-none opacity-0">
          {render(text, true)}
        </div>
        <div className="absolute inset-0">{render(displayed, false)}</div>
      </div>
    )
  }

  return (
    <span className={className}>
      {displayed}
      {!done && (
        <span className="ml-0.5 inline-block h-[1.1em] w-[2px] animate-pulse bg-[var(--color-primary)] align-text-bottom" />
      )}
    </span>
  )
}
