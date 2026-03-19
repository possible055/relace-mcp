import type { ReactNode } from 'react'

type CardProps = {
  children: ReactNode
  className?: string
}

export function Card({ children, className = '' }: CardProps) {
  return (
    <section
      className={`rounded-[var(--cds-radius-sm)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] shadow-[var(--cds-shadow-sm)] ${className}`}
    >
      {children}
    </section>
  )
}

export function CardHeader({ children, className = '' }: CardProps) {
  return (
    <div
      className={`flex items-center justify-between gap-4 border-b border-[var(--cds-border-subtle-01)] p-[var(--cds-spacing-05)] ${className}`}
    >
      {children}
    </div>
  )
}

export function CardTitle({ children, className = '' }: CardProps) {
  return <h2 className={`type-heading-02 text-[var(--cds-text-primary)] ${className}`}>{children}</h2>
}

export function CardContent({ children, className = '' }: CardProps) {
  return <div className={`p-[var(--cds-spacing-05)] ${className}`}>{children}</div>
}
