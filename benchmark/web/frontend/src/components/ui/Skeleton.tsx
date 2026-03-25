import { cn } from '../../lib/utils'

export function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-accent-01)]',
        className,
      )}
    />
  )
}
