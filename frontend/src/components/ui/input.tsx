import * as React from 'react'
import { cn } from '@/lib/utils'

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, type, ...props }, ref) => {
  return (
    <input
      ref={ref}
      type={type}
      className={cn(
        'flex h-11 w-full rounded-xl border border-slate-800 bg-slate-950/80 px-4 py-2 text-sm text-slate-100 placeholder:text-slate-500 outline-none transition-all duration-150',
        'focus:border-blue-500/70 focus:ring-4 focus:ring-blue-500/10',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
})
Input.displayName = 'Input'
