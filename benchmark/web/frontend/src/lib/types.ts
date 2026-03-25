export type ExperimentSummary = {
  experiment_id: string
  kind: string
  name: string
  status: string
  dataset_name: string
  case_count: number
  created_at: string
  completion_rate: number
  avg_file_recall: number
  avg_file_precision: number
}

export type ExperimentDetail = {
  experiment_id: string
  kind: string
  name: string
  manifest: Record<string, unknown>
  state: Record<string, unknown>
  summary: Record<string, unknown>
}

export type CaseSummary = {
  case_id: string
  repo: string
  completed: boolean
  partial: boolean
  file_recall: number
  file_precision: number
  turns_used: number
  latency_s: number
}

export type CaseDetail = {
  case_id: string
  repo: string
  completed: boolean
  partial: boolean
  file_recall: number
  file_precision: number
  line_coverage: number
  line_precision_matched: number
  function_hit_rate: number
  turns_used: number
  latency_s: number
  returned_files: Record<string, number[][]>
  error?: string
}

export type TraceEvent = {
  event: string
  timestamp?: string
  data: Record<string, unknown>
}

export type CaseTrace = {
  case_id: string
  events: TraceEvent[]
  metadata: Record<string, unknown>
}

export type CaseAnalysis = {
  case_id: string
  layered_metrics: Record<string, unknown>
  search_map: Record<string, unknown>
  journey_graph: Record<string, unknown>
  explanations: Record<string, string[]>
}

export type MetricsSummary = {
  total_cases: number
  completed_cases: number
  failed_cases: number
  avg_file_recall: number
  avg_file_precision: number
  avg_line_coverage: number
  avg_function_hit_rate: number
  avg_turns_used: number
  avg_latency_s: number
}

export type PaginatedResponse<T> = {
  items: T[]
  total: number
  limit: number
  offset: number
}
