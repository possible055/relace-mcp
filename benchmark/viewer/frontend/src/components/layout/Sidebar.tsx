import { FlaskConical, GitCompareArrows, Layers3 } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const links = [
  { to: '/experiments', label: 'Experiments', icon: Layers3 },
  { to: '/compare', label: 'Case Compare', icon: GitCompareArrows },
]

export default function Sidebar() {
  return (
    <aside className="hidden md:flex h-screen w-72 shrink-0 flex-col border-r border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)]">
      <div className="flex h-16 items-center gap-3 border-b border-[var(--cds-border-subtle-01)] px-6">
        <FlaskConical className="h-7 w-7 text-[var(--cds-interactive)]" />
        <div>
          <div className="type-heading-03 text-[var(--cds-text-primary)]">Benchmark Analyzer</div>
          <div className="type-label-01 text-[var(--cds-text-helper)]">Relace MCP</div>
        </div>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-6">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-[var(--cds-radius-md)] px-3 py-2.5 type-body-compact-01 transition-colors ${
                isActive
                  ? 'border-l-3 border-[var(--cds-interactive)] bg-[var(--cds-interactive)]/10 text-[var(--cds-interactive)]'
                  : 'text-[var(--cds-text-secondary)] hover:bg-[var(--cds-layer-hover-01)] hover:text-[var(--cds-text-primary)]'
              }`
            }
          >
            <link.icon className="h-5 w-5 shrink-0" />
            <span>{link.label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
