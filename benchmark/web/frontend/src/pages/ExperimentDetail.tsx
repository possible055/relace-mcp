import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, FileText, Clock, Target, Percent } from 'lucide-react'
import { fetchExperiment, fetchMetricsSummary, apiErrorMessage } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Skeleton } from '../components/ui/Skeleton'

function MetricCard({
  label,
  value,
  icon: Icon,
  format = 'number',
}: {
  label: string
  value: number
  icon: React.ComponentType<{ className?: string }>
  format?: 'number' | 'percent' | 'time'
}) {
  const formatted =
    format === 'percent'
      ? `${(value * 100).toFixed(1)}%`
      : format === 'time'
        ? `${value.toFixed(2)}s`
        : value.toFixed(2)

  return (
    <Card className="p-4">
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-[var(--cds-layer-02)] p-2">
          <Icon className="h-5 w-5 text-[var(--cds-icon-secondary)]" />
        </div>
        <div>
          <div className="type-label-01 text-[var(--cds-text-helper)]">{label}</div>
          <div className="type-heading-compact-02 text-[var(--cds-text-primary)]">{formatted}</div>
        </div>
      </div>
    </Card>
  )
}

export default function ExperimentDetail() {
  const { experimentId } = useParams<{ experimentId: string }>()

  const experimentQuery = useQuery({
    queryKey: ['experiment', experimentId],
    queryFn: () => fetchExperiment(experimentId!),
    enabled: !!experimentId,
  })

  const metricsQuery = useQuery({
    queryKey: ['metrics', experimentId],
    queryFn: () => fetchMetricsSummary(experimentId!),
    enabled: !!experimentId,
  })

  if (experimentQuery.isLoading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    )
  }

  if (experimentQuery.error) {
    return (
      <div className="p-6">
        <div className="text-[var(--cds-text-error)]">{apiErrorMessage(experimentQuery.error)}</div>
      </div>
    )
  }

  const experiment = experimentQuery.data!
  const metrics = metricsQuery.data
  const state = experiment.state
  const manifest = experiment.manifest
  const summary = experiment.summary
  const summaryStats =
    typeof summary.stats === 'object' && summary.stats !== null ? summary.stats : {}
  const totalCases =
    typeof state.total_cases === 'number' ? state.total_cases : Number(state.total_cases ?? 0)
  const statusText = typeof state.status === 'string' ? state.status : 'unknown'

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center gap-4">
        <Link
          to="/experiments"
          className="rounded-lg p-2 transition-colors hover:bg-[var(--cds-layer-hover-01)]"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div>
          <h1 className="type-heading-04 text-[var(--cds-text-primary)]">{experiment.name}</h1>
          <div className="type-body-compact-01 text-[var(--cds-text-helper)]">
            {experiment.kind} • {statusText} • {totalCases} cases
          </div>
        </div>
      </div>

      {metrics && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <MetricCard label="File Recall" value={metrics.avg_file_recall} icon={Target} format="percent" />
          <MetricCard label="File Precision" value={metrics.avg_file_precision} icon={Percent} format="percent" />
          <MetricCard label="Avg Turns" value={metrics.avg_turns_used} icon={FileText} />
          <MetricCard label="Avg Latency" value={metrics.avg_latency_s} icon={Clock} format="time" />
        </div>
      )}

      <Card className="p-4">
        <Link
          to={`/experiments/${experimentId}/cases`}
          className="-m-4 flex items-center justify-between rounded-lg p-4 transition-colors hover:bg-[var(--cds-layer-hover-01)]"
        >
          <div>
            <div className="type-heading-compact-01 text-[var(--cds-text-primary)]">View Cases</div>
            <div className="type-body-compact-01 text-[var(--cds-text-helper)]">{totalCases} benchmark cases</div>
          </div>
          <ArrowLeft className="h-5 w-5 rotate-180" />
        </Link>
      </Card>

      <Card className="p-4">
        <h2 className="mb-4 type-heading-compact-01 text-[var(--cds-text-primary)]">Summary</h2>
        <pre className="max-h-64 overflow-auto rounded-lg bg-[var(--cds-layer-02)] p-4 type-code-01 text-[var(--cds-text-secondary)]">
          {JSON.stringify(summaryStats, null, 2)}
        </pre>
      </Card>

      <Card className="p-4">
        <h2 className="mb-4 type-heading-compact-01 text-[var(--cds-text-primary)]">Manifest</h2>
        <pre className="max-h-96 overflow-auto rounded-lg bg-[var(--cds-layer-02)] p-4 type-code-01 text-[var(--cds-text-secondary)]">
          {JSON.stringify(manifest, null, 2)}
        </pre>
      </Card>
    </div>
  )
}
