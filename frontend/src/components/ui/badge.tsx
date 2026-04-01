import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors',
  {
    variants: {
      variant: {
        default: 'border-slate-700 bg-slate-900 text-slate-300',
        success: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300',
        warning: 'border-amber-500/20 bg-amber-500/10 text-amber-300',
        error: 'border-red-500/20 bg-red-500/10 text-red-300',
        info: 'border-blue-500/20 bg-blue-500/10 text-blue-300',
        accent: 'border-blue-500/20 bg-blue-500/10 text-blue-300',
        processing: 'border-blue-500/20 bg-blue-500/10 text-blue-200 animate-pulse',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
)

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}
