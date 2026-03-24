import { BarChart3 } from 'lucide-react'

export default function Header() {
  return (
    <header className="border-b border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)]">
      <div className="flex h-12 items-center gap-3 px-6">
        <BarChart3 className="h-5 w-5 text-[var(--cds-icon-secondary)]" />
        <h1 className="type-heading-02 text-[var(--cds-text-primary)]">Experiments</h1>
      </div>
    </header>
  )
}
