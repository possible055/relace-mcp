import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { Clock, FileSearch, RotateCcw, Target } from 'lucide-react'
import { apiErrorMessage, fetchRunCaseDetail, isApiNotFound } from '../lib/api'
import ExplorationTree from '../components/search/ExplorationTree'
import { decodeExperimentRoot } from '../lib/experimentRoots'
import type { MetricsSnapshot } from '../lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card'
import { Skeleton } from '../components/ui/Skeleton'

function rangeLabel(range?: [number, number] | number[]) {
  if (!range || range.length < 2) {
    return '-'
  }
  return `${range[0]}-${range[1]}`
}

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
        <CardHeader><CardTitle>Exploration Tree</CardTitle></CardHeader>
        <CardContent className="p-[var(--cds-spacing-05)]">
          {casePayload.exploration_tree ? (
            <ExplorationTree root={casePayload.exploration_tree} />
          ) : (
            <div className="py-6 text-center type-body-compact-01 text-[var(--cds-text-helper)]">
              No exploration data.
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Turn Summaries</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto p-[var(--cds-spacing-05)]">
          <table className="min-w-full">
            <thead className="bg-[var(--cds-layer-02)] text-left">
              <tr className="type-label-01 text-[var(--cds-text-helper)]">
                <th className="p-3">Turn</th>
                <th className="p-3">Tools</th>
                <th className="p-3">New Files</th>
                <th className="p-3">LLM Latency</th>
              </tr>
            </thead>
            <tbody>
              {casePayload.turn_summaries.map((summary) => (
                <tr key={summary.turn} className="border-t border-[var(--cds-border-subtle-01)] transition-colors hover:bg-[var(--cds-layer-hover-01)]">
                  <td className="p-3 type-body-compact-01 tabular-nums">{summary.turn}</td>
                  <td className="p-3 type-body-compact-01">{summary.tool_names.join(', ')}</td>
                  <td className="p-3 type-body-compact-01">{summary.new_files.join(', ') || '(none)'}</td>
                  <td className="p-3 type-body-compact-01 tabular-nums">{String(summary.llm_latency_ms ?? '-')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Ordered Events</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto p-[var(--cds-spacing-05)]">
          <table className="min-w-full">
            <thead className="bg-[var(--cds-layer-02)] text-left">
              <tr className="type-label-01 text-[var(--cds-text-helper)]">
                <th className="p-3">Turn</th>
                <th className="p-3">Tool</th>
                <th className="p-3">Access</th>
                <th className="p-3">Path</th>
                <th className="p-3">Range</th>
                <th className="p-3">Intent</th>
              </tr>
            </thead>
            <tbody>
              {casePayload.events.map((event, index) => (
                <tr key={`${event.turn}-${event.tool_name}-${event.path}-${index}`} className="border-t border-[var(--cds-border-subtle-01)] transition-colors hover:bg-[var(--cds-layer-hover-01)]">
                  <td className="p-3 type-body-compact-01 tabular-nums">{event.turn}</td>
                  <td className="p-3 type-body-compact-01">{event.tool_name}</td>
                  <td className="p-3 type-body-compact-01">{event.access_type}</td>
                  <td className="p-3 type-body-compact-01">{event.path}</td>
                  <td className="p-3 type-body-compact-01 tabular-nums">{rangeLabel(event.lines)}</td>
                  <td className="p-3 type-body-compact-01">
                    {event.tool_query ?? event.symbol_name ?? event.tool_command ?? '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>File Blocks</CardTitle></CardHeader>
          <CardContent className="p-[var(--cds-spacing-05)] space-y-3">
            {casePayload.file_blocks.map((block) => (
              <div key={`${block.path}:${block.block_kind}:${block.first_turn}`} className="rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] p-3">
                <div className="type-body-compact-01 font-medium">{block.path}</div>
                <div className="type-label-01 text-[var(--cds-text-helper)]">
                  {block.block_kind} | turns {String(block.first_turn ?? '-')} - {String(block.last_turn ?? '-')}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Function Blocks</CardTitle></CardHeader>
          <CardContent className="p-[var(--cds-spacing-05)] space-y-3">
            {casePayload.function_blocks.length === 0 ? (
              <div className="py-6 text-center type-body-compact-01 text-[var(--cds-text-helper)]">
                No function data available.
              </div>
            ) : (
              casePayload.function_blocks.map((block) => (
                <div key={`${block.path}:${block.function}:${rangeLabel(block.range)}`} className="rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] p-3">
                  <div className="type-body-compact-01 font-medium">
                    {block.class ? `${block.class}.${block.function}` : block.function}
                  </div>
                  <div className="type-label-01 text-[var(--cds-text-helper)]">
                    {block.path}:{rangeLabel(block.range)}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
