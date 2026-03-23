import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { Clock, FileSearch, RotateCcw, Target } from 'lucide-react'
import { apiErrorMessage, fetchRunCaseDetail, isApiNotFound } from '../lib/api'
import GraphDiagnostics from '../components/search/GraphDiagnostics'
import SingleCaseJourneyGraph from '../components/search/SingleCaseJourneyGraph'
import { decodeExperimentRoot } from '../lib/experimentRoots'
import type { MetricsSnapshot } from '../lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card'
import { Skeleton } from '../components/ui/Skeleton'

function formatMetric(value: number | null | undefined): string {
  return typeof value === 'number' ? String(value) : '-'
}

function KpiCard({
  title,
  value,
  icon: Icon,
}: {
  title: string
  value: string
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>
}) {
  return (
    <Card>
      <div className="p-[var(--cds-spacing-05)]">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-[var(--cds-radius-md)] bg-[var(--cds-interactive)]/10">
            <Icon className="h-3.5 w-3.5 text-[var(--cds-interactive)]" strokeWidth={2.2} />
          </div>
          <span className="type-label-01 text-[var(--cds-text-helper)]">{title}</span>
        </div>
        <div className="mt-2 type-kpi-sm tabular-nums text-[var(--cds-text-primary)]">{value}</div>
      </div>
    </Card>
  )
}

export default function RunDetail() {
  const params = useParams()
  const experimentRoot = useMemo(
    () => (params.encodedRoot ? decodeExperimentRoot(params.encodedRoot) : ''),
    [params.encodedRoot],
  )
  const caseId = params.caseId ?? ''

  const caseQuery = useQuery({
    queryKey: ['run-case-detail', experimentRoot, caseId],
    queryFn: () => fetchRunCaseDetail(experimentRoot, caseId),
    enabled: experimentRoot.length > 0 && caseId.length > 0,
  })

  const casePayload = useMemo(
    () => caseQuery.data ?? null,
    [caseQuery.data],
  )

  if (!experimentRoot) {
    return (
      <Card>
        <CardContent className="p-[var(--cds-spacing-05)]">
          <div className="py-10 text-center type-body-compact-01 text-[var(--cds-text-helper)]">
            Missing experiment root.
          </div>
        </CardContent>
      </Card>
    )
  }

  if (caseQuery.isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 lg:grid-cols-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
        <Skeleton className="h-20" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  if (caseQuery.isError && !isApiNotFound(caseQuery.error)) {
    return (
      <Card>
        <CardContent className="p-[var(--cds-spacing-05)]">
          <div className="py-10 text-center">
            <div className="type-body-compact-01 text-[var(--cds-support-error)]">
              Unable to load run detail.
            </div>
            <div className="mt-2 type-label-01 text-[var(--cds-text-helper)]">
              {apiErrorMessage(caseQuery.error, 'Run detail request failed.')}
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!casePayload) {
    return (
      <Card>
        <CardContent className="p-[var(--cds-spacing-05)]">
          <div className="py-10 text-center type-body-compact-01 text-[var(--cds-text-helper)]">
            Case `{caseId}` was not found in this experiment.
          </div>
        </CardContent>
      </Card>
    )
  }

  const metrics: MetricsSnapshot = casePayload.metrics_snapshot

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-4">
        <Card>
          <div className="p-[var(--cds-spacing-05)]">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-[var(--cds-radius-md)] bg-[var(--cds-interactive)]/10">
                <FileSearch className="h-3.5 w-3.5 text-[var(--cds-interactive)]" strokeWidth={2.2} />
              </div>
              <span className="type-label-01 text-[var(--cds-text-helper)]">Case</span>
            </div>
            <div className="mt-2 type-body-compact-01 font-medium text-[var(--cds-text-primary)] truncate">{casePayload.case_id}</div>
          </div>
        </Card>
        <KpiCard title="Recall" value={formatMetric(metrics.file_recall)} icon={Target} />
        <KpiCard title="Turns" value={formatMetric(metrics.turns_used)} icon={RotateCcw} />
        <KpiCard title="Latency" value={formatMetric(metrics.latency_s)} icon={Clock} />
      </div>

      <Card>
        <CardHeader><CardTitle>Query</CardTitle></CardHeader>
        <CardContent className="px-[var(--cds-spacing-05)] pb-[var(--cds-spacing-05)] type-body-compact-01 text-[var(--cds-text-secondary)]">
          {casePayload.query}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Journey Graph</CardTitle></CardHeader>
        <CardContent className="p-[var(--cds-spacing-05)]">
          {casePayload.journey_graph ? (
            <SingleCaseJourneyGraph graph={casePayload.journey_graph} caseData={casePayload} />
          ) : (
            <GraphDiagnostics
              message="Journey graph payload is missing from this run detail response."
              availableKeys={Object.keys(casePayload)}
              stats={[
                { label: 'Events', value: casePayload.events.length },
                { label: 'Turns', value: casePayload.turn_summaries.length },
                {
                  label: 'Exploration Tree',
                  value: casePayload.exploration_tree ? 'present' : 'missing',
                },
              ]}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
