import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { fetchBundle } from '../lib/api'
import { decodeExperimentRoot } from '../lib/experimentRoots'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card'

function rangeLabel(range?: [number, number] | number[]) {
  if (!range || range.length < 2) {
    return '-'
  }
  return `${range[0]}-${range[1]}`
}

export default function RunDetail() {
  const params = useParams()
  const experimentRoot = useMemo(
    () => (params.encodedRoot ? decodeExperimentRoot(params.encodedRoot) : ''),
    [params.encodedRoot],
  )
  const caseId = params.caseId ?? ''

  const bundleQuery = useQuery({
    queryKey: ['bundle-detail', experimentRoot],
    queryFn: () => fetchBundle(experimentRoot),
    enabled: experimentRoot.length > 0,
  })

  const casePayload = useMemo(
    () => bundleQuery.data?.cases.find((item) => item.case_id === caseId) ?? null,
    [bundleQuery.data, caseId],
  )

  if (!experimentRoot) {
    return (
      <Card>
        <CardContent>
          <div className="py-10 text-center type-body-compact-01 text-[var(--cds-text-helper)]">
            Missing experiment root.
          </div>
        </CardContent>
      </Card>
    )
  }

  if (bundleQuery.isLoading) {
    return (
      <Card>
        <CardContent>
          <div className="py-10 text-center type-body-compact-01 text-[var(--cds-text-helper)]">
            Loading run detail...
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!casePayload) {
    return (
      <Card>
        <CardContent>
          <div className="py-10 text-center type-body-compact-01 text-[var(--cds-text-helper)]">
            Case `{caseId}` was not found in this experiment.
          </div>
        </CardContent>
      </Card>
    )
  }

  const metrics = casePayload.metrics_snapshot

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-4">
        <Card>
          <CardHeader><CardTitle>Case</CardTitle></CardHeader>
          <CardContent className="type-body-compact-01 text-[var(--cds-text-secondary)]">{casePayload.case_id}</CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Recall</CardTitle></CardHeader>
          <CardContent className="type-kpi-sm">{String(metrics.file_recall ?? '-')}</CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Turns</CardTitle></CardHeader>
          <CardContent className="type-kpi-sm">{String(metrics.turns_used ?? '-')}</CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Latency</CardTitle></CardHeader>
          <CardContent className="type-kpi-sm">{String(metrics.latency_s ?? '-')}</CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Query</CardTitle></CardHeader>
        <CardContent className="type-body-compact-01 text-[var(--cds-text-secondary)]">
          {casePayload.query}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Turn Summaries</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
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
                <tr key={summary.turn} className="border-t border-[var(--cds-border-subtle-01)]">
                  <td className="p-3 type-body-compact-01">{summary.turn}</td>
                  <td className="p-3 type-body-compact-01">{summary.tool_names.join(', ')}</td>
                  <td className="p-3 type-body-compact-01">{summary.new_files.join(', ') || '(none)'}</td>
                  <td className="p-3 type-body-compact-01">{String(summary.llm_latency_ms ?? '-')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Ordered Events</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
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
                <tr key={`${event.turn}-${event.tool_name}-${event.path}-${index}`} className="border-t border-[var(--cds-border-subtle-01)]">
                  <td className="p-3 type-body-compact-01">{event.turn}</td>
                  <td className="p-3 type-body-compact-01">{event.tool_name}</td>
                  <td className="p-3 type-body-compact-01">{event.access_type}</td>
                  <td className="p-3 type-body-compact-01">{event.path}</td>
                  <td className="p-3 type-body-compact-01">{rangeLabel(event.lines)}</td>
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
          <CardContent className="space-y-3">
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
          <CardContent className="space-y-3">
            {casePayload.function_blocks.length === 0 ? (
              <div className="type-body-compact-01 text-[var(--cds-text-helper)]">
                No function overlays are available for this case.
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
