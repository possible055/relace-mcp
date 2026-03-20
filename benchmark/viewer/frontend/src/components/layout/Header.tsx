import { BarChart3, FolderGit2, GitCompareArrows } from 'lucide-react'
import { useLocation } from 'react-router-dom'

function pageInfo(pathname: string): { title: string; Icon: typeof BarChart3; subtitle: string } {
  if (pathname.startsWith('/compare')) {
    return {
      title: 'Case Compare',
      Icon: GitCompareArrows,
      subtitle: 'Compare code-space exploration across runs and trials.',
    }
  }
  if (pathname.startsWith('/runs/')) {
    return {
      title: 'Run Detail',
      Icon: FolderGit2,
      subtitle: 'Inspect a single run, case timeline, and selected code regions.',
    }
  }
  return {
    title: 'Experiments',
    Icon: BarChart3,
    subtitle: 'Browse benchmark runs, models, and search configurations.',
  }
}

export default function Header() {
  const location = useLocation()
  const { title, Icon, subtitle } = pageInfo(location.pathname)
  return (
    <header className="sticky top-0 z-40 border-b border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)]">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-6 px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <Icon className="h-8 w-8 text-[var(--cds-interactive)]" />
          <div>
            <h1 className="type-heading-03 text-[var(--cds-text-primary)]">{title}</h1>
            <p className="type-label-01 text-[var(--cds-text-helper)]">{subtitle}</p>
          </div>
        </div>
      </div>
    </header>
  )
}
