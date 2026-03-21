import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

type CardProps = {
  children: ReactNode
  className?: string
}

export function Card({ children, className }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-[var(--cds-radius-sm)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] shadow-[var(--cds-shadow-sm)]',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function CardHeader({ children, className }: CardProps) {
  return (
    <div
      className={cn(
        'flex flex-row items-center justify-between p-[var(--cds-spacing-05)]',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function CardTitle({ children, className }: CardProps) {
  return (
    <h3 className={cn('type-heading-02 text-[var(--cds-text-primary)] truncate', className)}>
      {children}
    </h3>
  )
}

export function CardContent({ children, className }: CardProps) {
  const base = className ? '' : 'p-[var(--cds-spacing-05)] pt-0'
  return <div className={cn(base, className)}>{children}</div>
}
