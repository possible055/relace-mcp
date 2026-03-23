import { useState } from 'react'
import type { ExplorationTreeNode } from '../../lib/types'

function rangeLabel(range?: [number, number] | number[]) {
  if (!range || range.length < 2) {
    return null
  }
  return `${range[0]}-${range[1]}`
}

function statusClassName(status: string) {
  switch (status) {
    case 'ok':
      return 'text-[var(--cds-support-success)]'
    case 'partial':
      return 'text-[var(--cds-support-warning)]'
    case 'error':
      return 'text-[var(--cds-support-error)]'
    case 'missing':
      return 'text-[var(--cds-text-helper)]'
    case 'selected':
      return 'text-[var(--cds-support-info)]'
    case 'empty':
      return 'text-[var(--cds-text-helper)]'
    default:
      return 'text-[var(--cds-text-secondary)]'
  }
}

function NodeLabel({ node }: { node: ExplorationTreeNode }) {
  if (node.kind === 'file' || node.kind === 'path' || node.kind === 'function') {
    return <code className="break-all text-[13px] text-[var(--cds-text-primary)]">{node.label}</code>
  }
  return <span className="type-body-compact-01 text-[var(--cds-text-primary)]">{node.label}</span>
}

function NodeMeta({ node }: { node: ExplorationTreeNode }) {
  const parts: string[] = []

  if (typeof node.latency_ms === 'number') {
    parts.push(`${node.latency_ms.toFixed(1)} ms`)
  }
  if (node.is_success === false) {
    parts.push('failed')
  }

  const lines = rangeLabel(node.lines)
  if (lines) {
    parts.push(`lines ${lines}`)
  }

  if (parts.length === 0) {
    return null
  }

  return (
    <div className="mt-1 type-label-01 text-[var(--cds-text-helper)]">
      {parts.join(' · ')}
    </div>
  )
}

function TreeNode({ node, depth = 0 }: { node: ExplorationTreeNode; depth?: number }) {
  const hasChildren = node.children.length > 0
  const [open, setOpen] = useState(node.kind === 'case' || node.kind === 'turn')

  return (
    <div className={depth > 0 ? 'pl-4' : ''}>
      <div className="rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] p-3 shadow-[var(--cds-shadow-sm)]">
        <div className="flex items-start gap-2">
          {hasChildren ? (
            <button
              type="button"
              onClick={() => setOpen((current) => !current)}
              aria-expanded={open}
              className="mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-[var(--cds-radius-sm)] text-[var(--cds-text-helper)] hover:bg-[var(--cds-layer-hover-01)]"
            >
              {open ? '▾' : '▸'}
            </button>
          ) : (
            <span className="mt-0.5 inline-flex h-5 w-5 items-center justify-center text-[var(--cds-text-helper)]">
              •
            </span>
          )}

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="type-label-01 uppercase tracking-[0.08em] text-[var(--cds-text-helper)]">
                {node.kind}
              </span>
              <NodeLabel node={node} />
              <span
                className={`rounded-full border border-[var(--cds-border-subtle-01)] px-2 py-0.5 type-label-01 ${statusClassName(node.status)}`}
              >
                {node.status}
              </span>
            </div>
            <NodeMeta node={node} />
            {node.detail ? (
              <div className="mt-2 whitespace-pre-wrap type-body-compact-01 text-[var(--cds-text-secondary)]">
                {node.detail}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {hasChildren && open ? (
        <div className="mt-2 space-y-2 border-l border-[var(--cds-border-subtle-01)] pl-4">
          {node.children.map((child) => (
            <TreeNode key={child.id} node={child} depth={depth + 1} />
          ))}
        </div>
      ) : null}
    </div>
  )
}

export default function ExplorationTree({ root }: { root: ExplorationTreeNode }) {
  return <TreeNode node={root} />
}
