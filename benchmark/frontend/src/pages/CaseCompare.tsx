import { useEffect, useMemo, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
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
import { compareCase, fetchBundle } from '../lib/api'
import { encodeExperimentRoot } from '../lib/experimentRoots'
import type { CaseMapCompare, FunctionBlock, SearchMapBundle } from '../lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card'

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

function statusString(status: Record<string, unknown>): string {
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

export default function CaseCompare() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedRoots = searchParams.getAll('root')
  const [caseIdInput, setCaseIdInput] = useState(searchParams.get('case') ?? '')

  const bundleQueries = useQueries({
    queries: selectedRoots.map((root) => ({
      queryKey: ['bundle', root],
      queryFn: () => fetchBundle(root),
      enabled: root.length > 0,
    })),
  })

  const bundles = bundleQueries
    .map((query) => query.data)
    .filter(Boolean) as SearchMapBundle[]

  const commonCaseIds = useMemo(() => {
    if (bundles.length === 0) {
      return []
    }
    const intersections = bundles.map((bundle) => new Set(bundle.cases.map((item) => item.case_id)))
    const [first, ...rest] = intersections
    const shared = Array.from(first).filter((caseId) => rest.every((set) => set.has(caseId)))
    return shared.sort()
  }, [bundles])

  useEffect(() => {
    if (!caseIdInput && commonCaseIds.length > 0) {
      setCaseIdInput(commonCaseIds[0])
      const next = new URLSearchParams(searchParams)
      next.set('case', commonCaseIds[0])
      setSearchParams(next, { replace: true })
    }
  }, [caseIdInput, commonCaseIds, searchParams, setSearchParams])

  const compareQuery = useQuery({
    queryKey: ['compare', selectedRoots, caseIdInput],
    queryFn: () => compareCase(caseIdInput, selectedRoots),
    enabled: selectedRoots.length > 0 && caseIdInput.length > 0,
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
        <CardContent>
          <p className="type-body-compact-01 text-[var(--cds-text-helper)]">
            No experiments selected. Start from <Link to="/experiments" className="text-[var(--cds-link-primary)]">Experiments</Link>.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Case Compare</CardTitle>
            <p className="type-label-01 text-[var(--cds-text-helper)]">
              Compare code-space exploration blocks across selected runs.
            </p>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-[2fr_1fr]">
            <label className="type-label-01 text-[var(--cds-text-secondary)]">
              Case ID
              <input
                value={caseIdInput}
                onChange={(event) => setCaseIdInput(event.target.value)}
                onBlur={() => {
                  const next = new URLSearchParams(searchParams)
                  if (caseIdInput) {
                    next.set('case', caseIdInput)
                  } else {
                    next.delete('case')
                  }
                  setSearchParams(next, { replace: true })
                }}
                className="mt-1 block w-full rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] px-3 py-2 type-body-compact-01"
                placeholder="Enter case_id"
              />
            </label>
            <label className="type-label-01 text-[var(--cds-text-secondary)]">
              Common Cases
              <select
                value={commonCaseIds.includes(caseIdInput) ? caseIdInput : ''}
                onChange={(event) => {
                  setCaseIdInput(event.target.value)
                  const next = new URLSearchParams(searchParams)
                  next.set('case', event.target.value)
                  setSearchParams(next, { replace: true })
                }}
                className="mt-1 block w-full rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] px-3 py-2 type-body-compact-01"
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

      {compareQuery.isLoading ? (
        <Card>
          <CardContent>
            <div className="py-10 text-center type-body-compact-01 text-[var(--cds-text-helper)]">
              Building comparison...
            </div>
          </CardContent>
        </Card>
      ) : compare ? (
        <>
          <div className="grid gap-4 lg:grid-cols-4">
            <Card>
              <CardHeader><CardTitle>Query</CardTitle></CardHeader>
              <CardContent className="type-body-compact-01 text-[var(--cds-text-secondary)]">{compare.query}</CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Shared Files</CardTitle></CardHeader>
              <CardContent className="type-kpi-sm">{compare.comparisons.shared_files.length}</CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Selected Overlap</CardTitle></CardHeader>
              <CardContent className="type-kpi-sm">{compare.comparisons.selected_overlap.length}</CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Hint Overlap</CardTitle></CardHeader>
              <CardContent className="type-kpi-sm">{compare.comparisons.hint_overlap.length}</CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader><CardTitle>Run Metrics</CardTitle></CardHeader>
            <CardContent className="overflow-x-auto">
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
                    const metrics = run.case_map?.metrics_snapshot ?? {}
                    return (
                      <tr key={run.run_id} className="border-t border-[var(--cds-border-subtle-01)]">
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
                        <td className="p-3 type-body-compact-01">{String(metrics.file_recall ?? '-')}</td>
                        <td className="p-3 type-body-compact-01">{String(metrics.file_precision ?? '-')}</td>
                        <td className="p-3 type-body-compact-01">{String(metrics.turns_used ?? '-')}</td>
                        <td className="p-3 type-body-compact-01">{String(metrics.latency_s ?? '-')}</td>
                        <td className="p-3 type-body-compact-01">
                          <Link
                            className="text-[var(--cds-link-primary)]"
                            to={`/runs/${encodeExperimentRoot(String(run.experiment.root ?? ''))}/cases/${compare.case_id}`}
                          >
                            Open
                          </Link>
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
              <CardContent className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={uniqueFilesCurve}>
                    <CartesianGrid stroke="#e0e0e0" strokeDasharray="3 3" />
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
              <CardContent className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={recallCurve}>
                    <CartesianGrid stroke="#e0e0e0" strokeDasharray="3 3" />
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
            <CardContent className="overflow-x-auto">
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
                      className={`border-t border-[var(--cds-border-subtle-01)] ${row.ground_truth ? 'bg-[var(--cds-layer-selected-01)]/40' : ''}`}
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
                              T{String(status.first_turn ?? '-')} - T{String(status.last_turn ?? '-')}
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
            <CardContent className="overflow-x-auto">
              {compare.comparisons.function_matrix.length === 0 ? (
                <div className="type-body-compact-01 text-[var(--cds-text-helper)]">
                  No function-level data is available for this case. Python runs expose function overlays; other languages stay file-first.
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
                      <tr key={`${row.path}:${row.function}:${row.range.join('-')}`} className="border-t border-[var(--cds-border-subtle-01)]">
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
                              {Array.isArray(status.access_kinds) ? status.access_kinds.join(', ') : String(status.status ?? '-')}
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
              <CardContent className="space-y-3">
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
              <CardContent className="space-y-3">
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
          <CardContent>
            <div className="py-10 text-center type-body-compact-01 text-[var(--cds-text-helper)]">
              Select a case to begin comparison.
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
