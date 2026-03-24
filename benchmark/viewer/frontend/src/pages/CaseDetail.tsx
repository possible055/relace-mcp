import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, FileCode, Clock, Target } from 'lucide-react'
import { fetchCase, fetchCaseTrace, apiErrorMessage } from '../lib/api'
import { Card } from '../components/ui/Card'
import { Skeleton } from '../components/ui/Skeleton'

export default function CaseDetail() {
  const { experimentId, caseId } = useParams<{
    experimentId: string
    caseId: string
  }>()

  const caseQuery = useQuery({
    queryKey: ['case', experimentId, caseId],
    queryFn: () => fetchCase(experimentId!, caseId!),
    enabled: !!experimentId && !!caseId,
  })

  const traceQuery = useQuery({
    queryKey: ['trace', experimentId, caseId],
    queryFn: () => fetchCaseTrace(experimentId!, caseId!),
    enabled: !!experimentId && !!caseId,
  })

  if (caseQuery.isLoading) {
    return (
      <div className="p-6 space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    )
  }

  if (caseQuery.error) {
    return (
      <div className="p-6">
        <div className="text-[var(--cds-text-error)]">
          {apiErrorMessage(caseQuery.error)}
        </div>
      </div>
    )
  }

  const caseData = caseQuery.data!
  const trace = traceQuery.data

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          to={`/experiments/${experimentId}/cases`}
          className="p-2 rounded-lg hover:bg-[var(--cds-layer-hover-01)] transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <div>
          <h1 className="type-heading-04 text-[var(--cds-text-primary)]">
            {caseData.case_id}
          </h1>
          <div className="type-body-compact-01 text-[var(--cds-text-helper)]">
            {caseData.repo}
          </div>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <Target className="w-5 h-5 text-[var(--cds-icon-secondary)]" />
            <div>
              <div className="type-label-01 text-[var(--cds-text-helper)]">
                File Recall
              </div>
              <div className="type-heading-compact-02">
                {(caseData.file_recall * 100).toFixed(1)}%
              </div>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <Target className="w-5 h-5 text-[var(--cds-icon-secondary)]" />
            <div>
              <div className="type-label-01 text-[var(--cds-text-helper)]">
                File Precision
              </div>
              <div className="type-heading-compact-02">
                {(caseData.file_precision * 100).toFixed(1)}%
              </div>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <FileCode className="w-5 h-5 text-[var(--cds-icon-secondary)]" />
            <div>
              <div className="type-label-01 text-[var(--cds-text-helper)]">
                Turns Used
              </div>
              <div className="type-heading-compact-02">{caseData.turns_used}</div>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <Clock className="w-5 h-5 text-[var(--cds-icon-secondary)]" />
            <div>
              <div className="type-label-01 text-[var(--cds-text-helper)]">
                Latency
              </div>
              <div className="type-heading-compact-02">
                {caseData.latency_s.toFixed(2)}s
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Returned Files */}
      <Card className="p-4">
        <h2 className="type-heading-compact-01 text-[var(--cds-text-primary)] mb-4">
          Returned Files ({Object.keys(caseData.returned_files).length})
        </h2>
        <div className="space-y-2 max-h-64 overflow-auto">
          {Object.entries(caseData.returned_files).map(([path, ranges]) => (
            <div
              key={path}
              className="flex items-center justify-between p-2 rounded bg-[var(--cds-layer-02)]"
            >
              <span className="type-code-01 text-[var(--cds-text-primary)]">
                {path}
              </span>
              <span className="type-label-01 text-[var(--cds-text-helper)]">
                {ranges.length} ranges
              </span>
            </div>
          ))}
        </div>
      </Card>

      {/* Trace Events */}
      {trace && trace.events.length > 0 && (
        <Card className="p-4">
          <h2 className="type-heading-compact-01 text-[var(--cds-text-primary)] mb-4">
            Trace Events ({trace.events.length})
          </h2>
          <div className="space-y-2 max-h-96 overflow-auto">
            {trace.events.map((event, idx) => (
              <div
                key={idx}
                className="p-3 rounded bg-[var(--cds-layer-02)] space-y-1"
              >
                <div className="flex items-center justify-between">
                  <span className="type-label-01 font-medium text-[var(--cds-text-primary)]">
                    {event.event}
                  </span>
                  {event.timestamp && (
                    <span className="type-label-01 text-[var(--cds-text-helper)]">
                      {event.timestamp}
                    </span>
                  )}
                </div>
                {Object.keys(event.data).length > 0 && (
                  <pre className="type-code-01 text-[var(--cds-text-secondary)] text-xs overflow-auto">
                    {JSON.stringify(event.data, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Error */}
      {caseData.error && (
        <Card className="p-4 border-l-4 border-[var(--cds-support-error)]">
          <h2 className="type-heading-compact-01 text-[var(--cds-support-error)] mb-2">
            Error
          </h2>
          <pre className="type-code-01 text-[var(--cds-text-secondary)] whitespace-pre-wrap">
            {caseData.error}
          </pre>
        </Card>
      )}
    </div>
  )
}
