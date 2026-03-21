import { BarChart3, FolderGit2, GitCompareArrows } from 'lucide-react'
import { useLocation } from 'react-router-dom'

function pageInfo(pathname: string): { title: string; Icon: typeof BarChart3 } {
  if (pathname.startsWith('/compare')) {
    return { title: 'Case Compare', Icon: GitCompareArrows }
  }
  if (pathname.startsWith('/runs/')) {
    return { title: 'Run Detail', Icon: FolderGit2 }
  }
  return { title: 'Experiments', Icon: BarChart3 }
}

export default function Header() {
  const location = useLocation()
  const { title, Icon } = pageInfo(location.pathname)
  return (
    <header className="sticky top-0 z-40 border-b border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)]">
      <div className="flex h-12 items-center gap-3 px-6">
        <Icon className="h-5 w-5 text-[var(--cds-icon-secondary)]" />
        <h1 className="type-heading-02 text-[var(--cds-text-primary)]">{title}</h1>
      </div>
    </header>
  )
}
