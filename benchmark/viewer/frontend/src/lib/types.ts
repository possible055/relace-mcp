export type ExperimentSummary = {
  experiment_id: string
  name: string
  status: string
  dataset_name: string
  case_count: number
  created_at: string
  file_recall: number
  file_precision: number
  // Legacy fields for backward compatibility
  root?: string
  type?: string
  provider?: string | null
  model?: string | null
  search_mode?: string | null
  max_turns?: number | null
  temperature?: number | null
  has_bundle?: boolean
}

export type ExperimentDetail = {
  experiment_id: string
  name: string
  status: string
  metadata: Record<string, unknown>
  stats: Record<string, number>
  case_count: number
}

export type CaseSummary = {
  case_id: string
  repo: string
  completed: boolean
  file_recall: number
  file_precision: number
  turns_used: number
  latency_s: number
}

export type CaseDetail = {
  case_id: string
  repo: string
  completed: boolean
  file_recall: number
  file_precision: number
  line_coverage: number
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

export type MetricsSummary = {
  total_cases: number
  completed_cases: number
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
