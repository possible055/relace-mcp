import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Link, useSearchParams } from 'react-router-dom'
import { apiErrorMessage, compareCase, fetchCaseIntersection } from '../lib/api'
import { encodeExperimentRoot } from '../lib/experimentRoots'
import type {
  CaseMapCompare,
  FunctionBlock,
  FunctionMatrixStatus,
  MetricsSnapshot,
  PathMatrixStatus,
} from '../lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card'
import { Skeleton } from '../components/ui/Skeleton'

const RUN_COLORS = [
  'var(--cds-chart-1)',
  'var(--cds-chart-2)',
  'var(--cds-chart-3)',
  'var(--cds-chart-4)',
  'var(--cds-chart-5)',
  'var(--cds-chart-6)',
  'var(--cds-chart-7)',
  'var(--cds-chart-8)',
]

function statusString(status: PathMatrixStatus): string {
  if (status.status === 'missing_case') {
    return 'missing'
  }
  const tokens: string[] = []
  if (status.hinted) tokens.push('H')
  if (status.discovered) tokens.push('D')
  if (status.read) tokens.push('R')
  if (status.grep_hit) tokens.push('G')
  if (status.lsp_touched) tokens.push('L')
  if (status.selected) tokens.push('S')
  return tokens.join('') || '-'
}

function buildCurveRows(
  compare: CaseMapCompare | undefined,
  keyName:
    | 'cumulative_unique_files'
    | 'cumulative_unique_functions'
    | 'ground_truth_file_recall'
    | 'ground_truth_function_recall',
) {
  if (!compare) {
    return []
  }
  const byTurn = new Map<number, Record<string, number | string>>()
  for (const [runId, curves] of Object.entries(compare.comparisons.turn_curves)) {
    for (const point of curves[keyName] ?? []) {
      const turn = Number(point[0] ?? 0)
      const value = Number(point[1] ?? 0)
      const row = byTurn.get(turn) ?? { turn }
      row[runId] = value
      byTurn.set(turn, row)
    }
  }
  return Array.from(byTurn.values()).sort((a, b) => Number(a.turn) - Number(b.turn))
}

function formatFunctionLabel(functionBlock: FunctionBlock): string {
  return functionBlock.class
    ? `${functionBlock.path}:${functionBlock.class}.${functionBlock.function}`
    : `${functionBlock.path}:${functionBlock.function}`
}

function formatMetric(value: number | null | undefined): string {
  return typeof value === 'number' ? String(value) : '-'
}

function formatStatusTurns(status: PathMatrixStatus): string {
  const firstTurn = typeof status.first_turn === 'number' ? String(status.first_turn) : '-'
  const lastTurn = typeof status.last_turn === 'number' ? String(status.last_turn) : '-'
  return `T${firstTurn} - T${lastTurn}`
}

function formatFunctionStatus(status: FunctionMatrixStatus): string {
  if (Array.isArray(status.access_kinds) && status.access_kinds.length > 0) {
    return status.access_kinds.join(', ')
  }
  return status.status ?? '-'
}

export default function CaseCompare() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedRoots = searchParams.getAll('root')
  const [caseIdInput, setCaseIdInput] = useState(searchParams.get('case') ?? '')

  const intersectionQuery = useQuery({
    queryKey: ['case-intersection', selectedRoots],
    queryFn: () => fetchCaseIntersection(selectedRoots),
    enabled: selectedRoots.length > 0,
  })

  const commonCaseIds = useMemo(
    () => intersectionQuery.data?.case_ids ?? [],
    [intersectionQuery.data],
  )
  const activeCaseId = caseIdInput.trim() || commonCaseIds[0] || ''

  const commitCaseId = (nextCaseId: string) => {
    const next = new URLSearchParams(searchParams)
    if (nextCaseId) {
      next.set('case', nextCaseId)
    } else {
      next.delete('case')
    }
    setSearchParams(next, { replace: true })
  }

  const compareQuery = useQuery({
    queryKey: ['compare', selectedRoots, activeCaseId],
    queryFn: () => compareCase(activeCaseId, selectedRoots),
    enabled: selectedRoots.length > 0 && activeCaseId.length > 0,
  })

  const compare = compareQuery.data
  const uniqueFilesCurve = buildCurveRows(compare, 'cumulative_unique_files')
  const recallCurve = buildCurveRows(compare, 'ground_truth_file_recall')

  if (selectedRoots.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Case Compare</CardTitle>
        </CardHeader>
        <CardContent className="px-[var(--cds-spacing-05)] pb-[var(--cds-spacing-05)]">
          <p className="type-body-compact-01 text-[var(--cds-text-helper)]">
            No experiments selected. Start from <Link to="/experiments" className="text-[var(--cds-link-primary)] hover:text-[var(--cds-link-primary-hover)]">Experiments</Link>.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Case Compare</CardTitle>
        </CardHeader>
        <CardContent className="p-[var(--cds-spacing-05)] space-y-4">
          <div className="grid gap-4 md:grid-cols-[2fr_1fr]">
            <label className="type-label-01 text-[var(--cds-text-secondary)]">
              Case ID
              <input
                value={caseIdInput}
                onChange={(event) => setCaseIdInput(event.target.value)}
                onBlur={() => commitCaseId(caseIdInput || commonCaseIds[0] || '')}
                className="mt-1 block w-full rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] px-3 py-2 type-body-compact-01 hover:bg-[var(--cds-layer-hover-01)] transition"
                placeholder="Enter case_id"
              />
            </label>
            <label className="type-label-01 text-[var(--cds-text-secondary)]">
              Common Cases
              <select
                value={commonCaseIds.includes(activeCaseId) ? activeCaseId : ''}
                onChange={(event) => {
                  setCaseIdInput(event.target.value)
                  commitCaseId(event.target.value)
                }}
                className="mt-1 block w-full rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] px-3 pr-8 py-2 type-body-compact-01 hover:bg-[var(--cds-layer-hover-01)] transition"
              >
                <option value="">Choose a shared case</option>
                {commonCaseIds.map((caseId) => (
                  <option key={caseId} value={caseId}>
                    {caseId}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            {selectedRoots.map((root) => (
              <span
                key={root}
                className="rounded-full bg-[var(--cds-layer-selected-01)] px-3 py-1 type-label-01 text-[var(--cds-text-primary)]"
              >
                {root}
              </span>
            ))}
          </div>
        </CardContent>
      </Card>

      {intersectionQuery.isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-3/4" />
        </div>
      ) : intersectionQuery.isError ? (
        <Card>
          <CardContent className="p-[var(--cds-spacing-05)]">
            <div className="py-10 text-center">
              <div className="type-body-compact-01 text-[var(--cds-support-error)]">
                Unable to load shared cases.
              </div>
              <div className="mt-2 type-label-01 text-[var(--cds-text-helper)]">
                {apiErrorMessage(intersectionQuery.error, 'Shared case lookup failed.')}
              </div>
            </div>
          </CardContent>
        </Card>
      ) : commonCaseIds.length === 0 ? (
        <Card>
          <CardContent className="p-[var(--cds-spacing-05)]">
            <div className="py-10 text-center type-body-compact-01 text-[var(--cds-text-helper)]">
              No shared cases were found across the selected runs.
            </div>
          </CardContent>
        </Card>
      ) : compareQuery.isLoading ? (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-4">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
          <Skeleton className="h-60" />
          <div className="grid gap-4 lg:grid-cols-2">
            <Skeleton className="h-80" />
            <Skeleton className="h-80" />
          </div>
        </div>
      ) : compareQuery.isError ? (
        <Card>
          <CardContent className="p-[var(--cds-spacing-05)]">
            <div className="py-10 text-center">
              <div className="type-body-compact-01 text-[var(--cds-support-error)]">
                Unable to build comparison.
              </div>
              <div className="mt-2 type-label-01 text-[var(--cds-text-helper)]">
                {apiErrorMessage(compareQuery.error, 'Case comparison request failed.')}
              </div>
            </div>
          </CardContent>
        </Card>
      ) : compare ? (
        <>
          <div className="grid gap-4 lg:grid-cols-4">
            <Card>
              <CardHeader><CardTitle>Query</CardTitle></CardHeader>
              <CardContent className="px-[var(--cds-spacing-05)] pb-[var(--cds-spacing-05)] type-body-compact-01 text-[var(--cds-text-secondary)]">{compare.query}</CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Shared Files</CardTitle></CardHeader>
              <CardContent className="px-[var(--cds-spacing-05)] pb-[var(--cds-spacing-05)] type-kpi-sm tabular-nums">{compare.comparisons.shared_files.length}</CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Selected Overlap</CardTitle></CardHeader>
              <CardContent className="px-[var(--cds-spacing-05)] pb-[var(--cds-spacing-05)] type-kpi-sm tabular-nums">{compare.comparisons.selected_overlap.length}</CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Hint Overlap</CardTitle></CardHeader>
              <CardContent className="px-[var(--cds-spacing-05)] pb-[var(--cds-spacing-05)] type-kpi-sm tabular-nums">{compare.comparisons.hint_overlap.length}</CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader><CardTitle>Run Metrics</CardTitle></CardHeader>
            <CardContent className="overflow-x-auto p-[var(--cds-spacing-05)]">
              <table className="min-w-full">
                <thead className="bg-[var(--cds-layer-02)] text-left">
                  <tr className="type-label-01 text-[var(--cds-text-helper)]">
                    <th className="p-3">Run</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Recall</th>
                    <th className="p-3">Precision</th>
                    <th className="p-3">Turns</th>
                    <th className="p-3">Latency</th>
                    <th className="p-3">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {compare.runs.map((run, index) => {
                    const metrics: MetricsSnapshot = run.case_map?.metrics_snapshot ?? {}
                    const experimentRoot = run.experiment.root ?? ''
                    return (
                      <tr key={run.run_id} className="border-t border-[var(--cds-border-subtle-01)] transition-colors hover:bg-[var(--cds-layer-hover-01)]">
                        <td className="p-3">
                          <div className="flex items-start gap-2">
                            <span
                              className="mt-1 inline-block h-3 w-3 rounded-full"
                              style={{ backgroundColor: RUN_COLORS[index % RUN_COLORS.length] }}
                            />
                            <span className="type-body-compact-01 text-[var(--cds-text-primary)]">{run.run_label}</span>
                          </div>
                        </td>
                        <td className="p-3 type-body-compact-01">{run.result_status}</td>
                        <td className="p-3 type-body-compact-01 tabular-nums">{formatMetric(metrics.file_recall)}</td>
                        <td className="p-3 type-body-compact-01 tabular-nums">{formatMetric(metrics.file_precision)}</td>
                        <td className="p-3 type-body-compact-01 tabular-nums">{formatMetric(metrics.turns_used)}</td>
                        <td className="p-3 type-body-compact-01 tabular-nums">{formatMetric(metrics.latency_s)}</td>
                        <td className="p-3 type-body-compact-01">
                          {experimentRoot ? (
                            <Link
                              className="text-[var(--cds-link-primary)] hover:text-[var(--cds-link-primary-hover)]"
                              to={`/runs/${encodeExperimentRoot(experimentRoot)}/cases/${compare.case_id}`}
                            >
                              Open
                            </Link>
                          ) : (
                            '-'
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>Cumulative Unique Files</CardTitle></CardHeader>
              <CardContent className="h-80 p-[var(--cds-spacing-05)]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={uniqueFilesCurve}>
                    <CartesianGrid stroke="var(--cds-border-subtle-01)" strokeDasharray="3 3" />
                    <XAxis dataKey="turn" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    {compare.runs.map((run, index) => (
                      <Line
                        key={run.run_id}
                        type="monotone"
                        dataKey={run.run_id}
                        name={run.run_label}
                        stroke={RUN_COLORS[index % RUN_COLORS.length]}
                        strokeWidth={2}
                        dot={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Ground Truth File Recall</CardTitle></CardHeader>
              <CardContent className="h-80 p-[var(--cds-spacing-05)]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={recallCurve}>
                    <CartesianGrid stroke="var(--cds-border-subtle-01)" strokeDasharray="3 3" />
                    <XAxis dataKey="turn" />
                    <YAxis domain={[0, 1]} />
                    <Tooltip />
                    <Legend />
                    {compare.runs.map((run, index) => (
                      <Line
                        key={run.run_id}
                        type="monotone"
                        dataKey={run.run_id}
                        name={run.run_label}
                        stroke={RUN_COLORS[index % RUN_COLORS.length]}
                        strokeWidth={2}
                        dot={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader><CardTitle>Path Matrix</CardTitle></CardHeader>
            <CardContent className="overflow-x-auto p-[var(--cds-spacing-05)]">
              <table className="min-w-full">
                <thead className="bg-[var(--cds-layer-02)] text-left">
                  <tr className="type-label-01 text-[var(--cds-text-helper)]">
                    <th className="p-3">Path</th>
                    {compare.runs.map((run) => (
                      <th key={run.run_id} className="p-3">{run.run_label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {compare.comparisons.path_matrix.map((row) => (
                    <tr
                      key={row.path}
                      className={`border-t border-[var(--cds-border-subtle-01)] transition-colors hover:bg-[var(--cds-layer-hover-01)] ${row.ground_truth ? 'bg-[var(--cds-layer-selected-01)]/40' : ''}`}
                    >
                      <td className="p-3">
                        <div className="type-body-compact-01 font-medium">{row.path}</div>
                        {row.ground_truth ? (
                          <div className="type-label-01 text-[var(--cds-support-success)]">ground truth</div>
                        ) : null}
                      </td>
                      {compare.runs.map((run) => {
                        const status = row.runs[run.run_id] ?? {}
                        return (
                          <td key={run.run_id} className="p-3">
                            <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                              {statusString(status)}
                            </div>
                            <div className="type-label-01 text-[var(--cds-text-helper)]">
                              {formatStatusTurns(status)}
                            </div>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Function Matrix</CardTitle></CardHeader>
            <CardContent className="overflow-x-auto p-[var(--cds-spacing-05)]">
              {compare.comparisons.function_matrix.length === 0 ? (
                <div className="py-8 text-center type-body-compact-01 text-[var(--cds-text-helper)]">
                  No function-level data available.
                </div>
              ) : (
                <table className="min-w-full">
                  <thead className="bg-[var(--cds-layer-02)] text-left">
                    <tr className="type-label-01 text-[var(--cds-text-helper)]">
                      <th className="p-3">Function</th>
                      {compare.runs.map((run) => (
                        <th key={run.run_id} className="p-3">{run.run_label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {compare.comparisons.function_matrix.map((row) => (
                      <tr key={`${row.path}:${row.function}:${row.range.join('-')}`} className="border-t border-[var(--cds-border-subtle-01)] transition-colors hover:bg-[var(--cds-layer-hover-01)]">
                        <td className="p-3">
                          <div className="type-body-compact-01 font-medium">
                            {row.class ? `${row.class}.${row.function}` : row.function}
                          </div>
                          <div className="type-label-01 text-[var(--cds-text-helper)]">
                            {row.path}:{row.range.join('-')}
                          </div>
                        </td>
                        {compare.runs.map((run) => {
                          const status = row.runs[run.run_id] ?? {}
                          return (
                            <td key={run.run_id} className="p-3 type-body-compact-01">
                              {formatFunctionStatus(status)}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>Unique Files By Run</CardTitle></CardHeader>
              <CardContent className="p-[var(--cds-spacing-05)] space-y-3">
                {compare.runs.map((run) => {
                  const files = compare.comparisons.unique_files_by_run[run.run_id] ?? []
                  return (
                    <div key={run.run_id}>
                      <div className="type-label-02 text-[var(--cds-text-primary)]">
                        {run.run_label}
                      </div>
                      <div className="type-body-compact-01 text-[var(--cds-text-secondary)]">
                        {files.length > 0 ? files.join(', ') : '(none)'}
                      </div>
                    </div>
                  )
                })}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Unique Functions By Run</CardTitle></CardHeader>
              <CardContent className="p-[var(--cds-spacing-05)] space-y-3">
                {compare.runs.map((run) => {
                  const functions = compare.comparisons.unique_functions_by_run[run.run_id] ?? []
                  return (
                    <div key={run.run_id}>
                      <div className="type-label-02 text-[var(--cds-text-primary)]">
                        {run.run_label}
                      </div>
                      <div className="type-body-compact-01 text-[var(--cds-text-secondary)]">
                        {functions.length > 0 ? functions.map(formatFunctionLabel).join(', ') : '(none)'}
                      </div>
                    </div>
                  )
                })}
              </CardContent>
            </Card>
          </div>
        </>
      ) : (
        <Card>
          <CardContent className="p-[var(--cds-spacing-05)]">
            <div className="py-10 text-center type-body-compact-01 text-[var(--cds-text-helper)]">
              Select a case to begin comparison.
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
