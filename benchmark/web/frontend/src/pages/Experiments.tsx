import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FolderSearch } from 'lucide-react'
import { Link } from 'react-router-dom'
import { apiErrorMessage, fetchExperiments } from '../lib/api'
import type { ExperimentSummary, PaginatedResponse } from '../lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card'
import { Skeleton } from '../components/ui/Skeleton'

const EMPTY_EXPERIMENTS: ExperimentSummary[] = []

function ExperimentRow({ experiment }: { experiment: ExperimentSummary }) {
  return (
    <tr className="border-t border-[var(--cds-border-subtle-01)] align-top transition-colors hover:bg-[var(--cds-layer-hover-01)]">
      <td className="p-3">
        <Link
          to={`/experiments/${experiment.experiment_id}`}
          className="type-body-compact-01 font-semibold text-[var(--cds-link-primary)] hover:underline"
        >
          {experiment.name}
        </Link>
        <div className="type-label-01 text-[var(--cds-text-helper)]">{experiment.experiment_id}</div>
      </td>
      <td className="p-3 type-body-compact-01 text-[var(--cds-text-secondary)]">{experiment.kind}</td>
      <td className="p-3 type-body-compact-01 text-[var(--cds-text-secondary)]">{experiment.status}</td>
      <td className="p-3 type-body-compact-01 text-[var(--cds-text-secondary)]">{experiment.dataset_name}</td>
      <td className="p-3 type-body-compact-01 tabular-nums text-[var(--cds-text-secondary)]">{experiment.case_count}</td>
      <td className="p-3 type-body-compact-01 tabular-nums text-[var(--cds-text-secondary)]">{(experiment.completion_rate * 100).toFixed(1)}%</td>
      <td className="p-3 type-body-compact-01 tabular-nums text-[var(--cds-text-secondary)]">{(experiment.avg_file_recall * 100).toFixed(1)}%</td>
      <td className="p-3 type-body-compact-01 tabular-nums text-[var(--cds-text-secondary)]">{(experiment.avg_file_precision * 100).toFixed(1)}%</td>
    </tr>
  )
}

export default function Experiments() {
  const [kindFilter, setKindFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const experimentsQuery = useQuery<PaginatedResponse<ExperimentSummary>>({
    queryKey: ['experiments'],
    queryFn: () => fetchExperiments(),
  })

  const experiments = experimentsQuery.data?.items ?? EMPTY_EXPERIMENTS
  const kindOptions = useMemo(
    () => Array.from(new Set(experiments.map((item) => item.kind))).sort(),
    [experiments]
  )
  const statusOptions = useMemo(
    () => Array.from(new Set(experiments.map((item) => item.status))).sort(),
    [experiments]
  )

  const filtered = experiments.filter((experiment) => {
    if (kindFilter && experiment.kind !== kindFilter) {
      return false
    }
    if (statusFilter && experiment.status !== statusFilter) {
      return false
    }
    return true
  })

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Experiments</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 p-[var(--cds-spacing-05)]">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="type-label-01 text-[var(--cds-text-secondary)]">
              Kind
              <select
                value={kindFilter}
                onChange={(event) => setKindFilter(event.target.value)}
                className="mt-1 block w-full rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] px-3 py-2 pr-8 type-body-compact-01 transition hover:bg-[var(--cds-layer-hover-01)]"
              >
                <option value="">All</option>
                {kindOptions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label className="type-label-01 text-[var(--cds-text-secondary)]">
              Status
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
                className="mt-1 block w-full rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] px-3 py-2 pr-8 type-body-compact-01 transition hover:bg-[var(--cds-layer-hover-01)]"
              >
                <option value="">All</option>
                {statusOptions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {experimentsQuery.isLoading ? (
            <div className="space-y-3 py-4">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-3/4" />
            </div>
          ) : experimentsQuery.isError ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <div className="type-body-compact-01 text-[var(--cds-support-error)]">
                Unable to load experiments.
              </div>
              <div className="type-label-01 text-[var(--cds-text-helper)]">
                {apiErrorMessage(experimentsQuery.error, 'Experiments request failed.')}
              </div>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <FolderSearch className="h-8 w-8 text-[var(--cds-text-helper)]" />
              <div className="type-body-compact-01 text-[var(--cds-text-helper)]">
                No experiments matched the current filters.
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead className="bg-[var(--cds-layer-02)] text-left">
                  <tr className="type-label-01 text-[var(--cds-text-helper)]">
                    <th className="p-3">Experiment</th>
                    <th className="p-3">Kind</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Dataset</th>
                    <th className="p-3">Cases</th>
                    <th className="p-3">Completion</th>
                    <th className="p-3">Recall</th>
                    <th className="p-3">Precision</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((experiment) => (
                    <ExperimentRow key={experiment.experiment_id} experiment={experiment} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
