import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, FileCode, Clock, Target } from 'lucide-react'
import { fetchCase, fetchCaseAnalysis, fetchCaseTrace, apiErrorMessage } from '../lib/api'
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

  const analysisQuery = useQuery({
    queryKey: ['analysis', experimentId, caseId],
    queryFn: () => fetchCaseAnalysis(experimentId!, caseId!),
    enabled: !!experimentId && !!caseId,
  })

  if (caseQuery.isLoading) {
    return (
      <div className="space-y-6 p-6">
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
        <div className="text-[var(--cds-text-error)]">{apiErrorMessage(caseQuery.error)}</div>
      </div>
    )
  }

  const caseData = caseQuery.data!
  const trace = traceQuery.data
  const analysis = analysisQuery.data

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center gap-4">
        <Link
          to={`/experiments/${experimentId}/cases`}
          className="rounded-lg p-2 transition-colors hover:bg-[var(--cds-layer-hover-01)]"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div>
          <h1 className="type-heading-04 text-[var(--cds-text-primary)]">{caseData.case_id}</h1>
          <div className="type-body-compact-01 text-[var(--cds-text-helper)]">{caseData.repo}</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <Target className="h-5 w-5 text-[var(--cds-icon-secondary)]" />
            <div>
              <div className="type-label-01 text-[var(--cds-text-helper)]">File Recall</div>
              <div className="type-heading-compact-02">{(caseData.file_recall * 100).toFixed(1)}%</div>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <Target className="h-5 w-5 text-[var(--cds-icon-secondary)]" />
            <div>
              <div className="type-label-01 text-[var(--cds-text-helper)]">File Precision</div>
              <div className="type-heading-compact-02">{(caseData.file_precision * 100).toFixed(1)}%</div>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <FileCode className="h-5 w-5 text-[var(--cds-icon-secondary)]" />
            <div>
              <div className="type-label-01 text-[var(--cds-text-helper)]">Turns Used</div>
              <div className="type-heading-compact-02">{caseData.turns_used}</div>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <Clock className="h-5 w-5 text-[var(--cds-icon-secondary)]" />
            <div>
              <div className="type-label-01 text-[var(--cds-text-helper)]">Latency</div>
              <div className="type-heading-compact-02">{caseData.latency_s.toFixed(2)}s</div>
            </div>
          </div>
        </Card>
      </div>

      <Card className="p-4">
        <h2 className="mb-4 type-heading-compact-01 text-[var(--cds-text-primary)]">
          Returned Files ({Object.keys(caseData.returned_files).length})
        </h2>
        <div className="max-h-64 space-y-2 overflow-auto">
          {Object.entries(caseData.returned_files).map(([path, ranges]) => (
            <div
              key={path}
              className="flex items-center justify-between rounded bg-[var(--cds-layer-02)] p-2"
            >
              <span className="type-code-01 text-[var(--cds-text-primary)]">{path}</span>
              <span className="type-label-01 text-[var(--cds-text-helper)]">{ranges.length} ranges</span>
            </div>
          ))}
        </div>
      </Card>

      {analysis && (
        <Card className="p-4">
          <h2 className="mb-4 type-heading-compact-01 text-[var(--cds-text-primary)]">Analysis</h2>
          <div className="space-y-4">
            <pre className="max-h-64 overflow-auto rounded bg-[var(--cds-layer-02)] p-3 type-code-01 text-[var(--cds-text-secondary)]">
              {JSON.stringify(analysis.layered_metrics, null, 2)}
            </pre>
            <pre className="max-h-64 overflow-auto rounded bg-[var(--cds-layer-02)] p-3 type-code-01 text-[var(--cds-text-secondary)]">
              {JSON.stringify(analysis.explanations, null, 2)}
            </pre>
          </div>
        </Card>
      )}

      {trace && trace.events.length > 0 && (
        <Card className="p-4">
          <h2 className="mb-4 type-heading-compact-01 text-[var(--cds-text-primary)]">Trace Events ({trace.events.length})</h2>
          <div className="max-h-96 space-y-2 overflow-auto">
            {trace.events.map((event, idx) => (
              <div key={idx} className="space-y-1 rounded bg-[var(--cds-layer-02)] p-3">
                <div className="flex items-center justify-between">
                  <span className="type-label-01 font-medium text-[var(--cds-text-primary)]">{event.event}</span>
                  {event.timestamp && (
                    <span className="type-label-01 text-[var(--cds-text-helper)]">{event.timestamp}</span>
                  )}
                </div>
                {Object.keys(event.data).length > 0 && (
                  <pre className="overflow-auto type-code-01 text-xs text-[var(--cds-text-secondary)]">
                    {JSON.stringify(event.data, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {caseData.error && (
        <Card className="border-l-4 border-[var(--cds-support-error)] p-4">
          <h2 className="mb-2 type-heading-compact-01 text-[var(--cds-support-error)]">Error</h2>
          <pre className="whitespace-pre-wrap type-code-01 text-[var(--cds-text-secondary)]">{caseData.error}</pre>
        </Card>
      )}
    </div>
  )
}
