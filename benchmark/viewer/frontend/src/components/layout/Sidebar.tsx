import { useCallback, useState } from 'react'
import { ChevronLeft, FlaskConical, GitCompareArrows, Layers3 } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const COLLAPSED_KEY = 'sidebar-collapsed'

const links = [
  { to: '/experiments', label: 'Experiments', icon: Layers3 },
  { to: '/compare', label: 'Case Compare', icon: GitCompareArrows },
]

function expandingLabelClass(collapsed: boolean, expandedWidthClass: string): string {
  return `pointer-events-none overflow-hidden whitespace-nowrap transition-[max-width,opacity] duration-200 motion-reduce:transition-none ${
    collapsed ? 'max-w-0 opacity-0' : `${expandedWidthClass} opacity-100`
  }`
}

function primaryItemClassName(collapsed: boolean, isActive: boolean): string {
  const stateClass = isActive
    ? 'bg-[var(--cds-layer-accent-01)] text-[var(--cds-text-primary)]'
    : 'text-[var(--cds-text-secondary)] hover:bg-[var(--cds-layer-hover-01)] hover:text-[var(--cds-text-primary)]'
  const indicatorClass =
    isActive && !collapsed
      ? "before:absolute before:left-0 before:top-0 before:h-full before:w-[3px] before:rounded-r-[2px] before:bg-[var(--cds-interactive)] before:content-['']"
      : ''

  return `relative flex h-10 items-center overflow-hidden whitespace-nowrap rounded-[var(--cds-radius-sm)] transition-[padding-left,padding-right,background-color,color] duration-200 motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-[var(--cds-focus)] focus-visible:outline-offset-0 ${
    collapsed ? 'px-5' : 'px-3'
  } ${stateClass} ${indicatorClass}`
}

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_KEY) === '1')

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev
      localStorage.setItem(COLLAPSED_KEY, next ? '1' : '0')
      return next
    })
  }, [])

  return (
    <aside
      className={`hidden h-screen shrink-0 flex-col overflow-hidden border-r border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] transition-[width] duration-200 motion-reduce:transition-none md:flex ${
        collapsed ? 'w-14' : 'w-72'
      }`}
    >
      <div
        className={`flex h-12 shrink-0 items-center overflow-hidden border-b border-[var(--cds-border-strong-01)] transition-[padding-left,padding-right] duration-200 motion-reduce:transition-none ${
          collapsed ? 'px-[18px]' : 'px-3'
        }`}
      >
        <FlaskConical className="h-5 w-5 shrink-0 text-[var(--cds-icon-interactive)]" />
        <span aria-hidden={collapsed} className={expandingLabelClass(collapsed, 'max-w-48')}>
          <span className="ml-3 block whitespace-nowrap type-heading-01 text-[var(--cds-text-primary)]">
            Benchmark Analyzer
          </span>
        </span>
      </div>

      <nav aria-label="Primary" className="flex-1 space-y-0.5 overflow-y-auto py-2">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            aria-label={link.label}
            title={collapsed ? link.label : undefined}
            className={({ isActive }) => primaryItemClassName(collapsed, isActive)}
          >
            {({ isActive }) => (
              <>
                <link.icon
                  className={`h-4 w-4 shrink-0 ${isActive ? 'text-[var(--cds-icon-interactive)]' : 'text-[var(--cds-icon-secondary)]'}`}
                />
                <span aria-hidden={collapsed} className={expandingLabelClass(collapsed, 'max-w-40')}>
                  <span className="ml-3 block whitespace-nowrap type-body-compact-01">{link.label}</span>
                </span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="shrink-0 border-t border-[var(--cds-border-subtle-01)] py-2">
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand sidebar' : undefined}
          className={`flex h-10 w-full items-center overflow-hidden whitespace-nowrap rounded-[var(--cds-radius-sm)] text-[var(--cds-text-secondary)] transition-[padding-left,padding-right,background-color,color] duration-200 motion-reduce:transition-none hover:bg-[var(--cds-layer-hover-01)] hover:text-[var(--cds-text-primary)] focus-visible:outline-2 focus-visible:outline-[var(--cds-focus)] focus-visible:outline-offset-0 ${
            collapsed ? 'px-5' : 'px-3'
          }`}
        >
          <ChevronLeft
            className={`h-4 w-4 shrink-0 transition-transform duration-200 motion-reduce:transition-none ${
              collapsed ? 'rotate-180' : ''
            }`}
          />
          <span aria-hidden={collapsed} className={expandingLabelClass(collapsed, 'max-w-40')}>
            <span className="ml-3 block whitespace-nowrap type-label-01">Collapse</span>
          </span>
        </button>
      </div>
    </aside>
  )
}
