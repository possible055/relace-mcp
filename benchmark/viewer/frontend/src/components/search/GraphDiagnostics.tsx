import { AlertTriangle } from 'lucide-react'

type GraphDiagnosticsProps = {
  title?: string
  message: string
  availableKeys?: string[]
  stats?: Array<{ label: string; value: string | number }>
}

export default function GraphDiagnostics({
  title = 'Graph Unavailable',
  message,
  availableKeys = [],
  stats = [],
}: GraphDiagnosticsProps) {
  return (
    <div className="space-y-3">
      <div className="type-heading-01 text-[var(--cds-text-primary)]">{title}</div>
      <div className="flex items-start gap-3 rounded-[var(--cds-radius-md)] border border-[var(--cds-support-warning)]/30 bg-[var(--cds-support-warning)]/10 p-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--cds-support-warning)]" />
        <div className="space-y-2">
          <div className="type-body-compact-01 text-[var(--cds-text-primary)]">{message}</div>
          <div className="type-label-01 text-[var(--cds-text-helper)]">
            這通常表示 backend process 仍在跑舊碼，或目前載入的是尚未升級的 bundle payload。
          </div>
        </div>
      </div>

      {stats.length > 0 ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {stats.map((item) => (
            <div
              key={item.label}
              className="rounded-[var(--cds-radius-sm)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-02)] px-3 py-2"
            >
              <div className="type-label-01 text-[var(--cds-text-helper)]">{item.label}</div>
              <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                {String(item.value)}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {availableKeys.length > 0 ? (
        <div>
          <div className="mb-1 type-label-01 text-[var(--cds-text-helper)]">Available Fields</div>
          <code className="block whitespace-pre-wrap break-all rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2 type-body-compact-01 text-[var(--cds-text-primary)]">
            {availableKeys.join(', ')}
          </code>
        </div>
      ) : null}
    </div>
  )
}
