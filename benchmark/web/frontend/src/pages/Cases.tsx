import { useQuery } from '@tanstack/react-query'
import { useParams, Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Check, TriangleAlert, X } from 'lucide-react'
import { fetchCases, apiErrorMessage } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Skeleton } from '../components/ui/Skeleton'

export default function Cases() {
  const { experimentId } = useParams<{ experimentId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()

  const page = parseInt(searchParams.get('page') || '1', 10)
  const limit = 20
  const offset = (page - 1) * limit

  const casesQuery = useQuery({
    queryKey: ['cases', experimentId, page],
    queryFn: () => fetchCases(experimentId!, { limit, offset }),
    enabled: !!experimentId,
  })

  if (casesQuery.isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-64" />
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
    )
  }

  if (casesQuery.error) {
    return (
      <div className="p-6">
        <div className="text-[var(--cds-text-error)]">{apiErrorMessage(casesQuery.error)}</div>
      </div>
    )
  }

  const data = casesQuery.data!
  const totalPages = Math.max(Math.ceil(data.total / limit), 1)

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center gap-4">
        <Link
          to={`/experiments/${experimentId}`}
          className="rounded-lg p-2 transition-colors hover:bg-[var(--cds-layer-hover-01)]"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div>
          <h1 className="type-heading-04 text-[var(--cds-text-primary)]">Cases</h1>
          <div className="type-body-compact-01 text-[var(--cds-text-helper)]">{data.total} total cases</div>
        </div>
      </div>

      <Card className="overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[var(--cds-border-subtle-01)]">
              <th className="p-4 text-left type-label-01 text-[var(--cds-text-helper)]">Case ID</th>
              <th className="p-4 text-left type-label-01 text-[var(--cds-text-helper)]">Repo</th>
              <th className="p-4 text-center type-label-01 text-[var(--cds-text-helper)]">Status</th>
              <th className="p-4 text-right type-label-01 text-[var(--cds-text-helper)]">Recall</th>
              <th className="p-4 text-right type-label-01 text-[var(--cds-text-helper)]">Precision</th>
              <th className="p-4 text-right type-label-01 text-[var(--cds-text-helper)]">Turns</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((c) => (
              <tr
                key={c.case_id}
                className="border-b border-[var(--cds-border-subtle-01)] hover:bg-[var(--cds-layer-hover-01)]"
              >
                <td className="p-4">
                  <Link
                    to={`/experiments/${experimentId}/cases/${c.case_id}`}
                    className="type-body-compact-01 text-[var(--cds-link-primary)] hover:underline"
                  >
                    {c.case_id}
                  </Link>
                </td>
                <td className="p-4 type-body-compact-01 text-[var(--cds-text-secondary)]">{c.repo}</td>
                <td className="p-4 text-center">
                  {c.partial ? (
                    <TriangleAlert className="inline h-4 w-4 text-[var(--cds-support-warning)]" />
                  ) : c.completed ? (
                    <Check className="inline h-4 w-4 text-[var(--cds-support-success)]" />
                  ) : (
                    <X className="inline h-4 w-4 text-[var(--cds-support-error)]" />
                  )}
                </td>
                <td className="p-4 text-right type-body-compact-01 text-[var(--cds-text-primary)]">{(c.file_recall * 100).toFixed(1)}%</td>
                <td className="p-4 text-right type-body-compact-01 text-[var(--cds-text-primary)]">{(c.file_precision * 100).toFixed(1)}%</td>
                <td className="p-4 text-right type-body-compact-01 text-[var(--cds-text-secondary)]">{c.turns_used}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          <button
            onClick={() => setSearchParams({ page: String(page - 1) })}
            disabled={page <= 1}
            className="rounded-lg bg-[var(--cds-layer-01)] px-4 py-2 type-body-compact-01 hover:bg-[var(--cds-layer-hover-01)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Previous
          </button>
          <span className="px-4 py-2 type-body-compact-01 text-[var(--cds-text-secondary)]">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setSearchParams({ page: String(page + 1) })}
            disabled={page >= totalPages}
            className="rounded-lg bg-[var(--cds-layer-01)] px-4 py-2 type-body-compact-01 hover:bg-[var(--cds-layer-hover-01)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
