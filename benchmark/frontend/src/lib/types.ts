export type ExperimentSummary = {
  name: string
  root: string
  type: string
  provider: string | null
  model: string | null
  search_mode: string | null
  max_turns: number | null
  temperature: number | null
  has_bundle: boolean
  case_count: number | null
}

export type SearchMapEvent = {
  turn: number
  tool_name: string
  tool_call_id?: string
  access_type: string
  path: string
  lines?: [number, number] | number[]
  is_success: boolean
  latency_ms: number
  tool_query?: string
  tool_command?: string
  symbol_name?: string
  symbol_kind?: string
  functions: FunctionBlock[]
}

export type FunctionBlock = {
  path: string
  function: string
  class?: string | null
  range: [number, number] | number[]
  signature?: string | null
  first_turn?: number
  last_turn?: number
  access_kinds?: string[]
  source_tools?: string[]
}

export type FileBlock = {
  path: string
  block_kind: string
  ranges: Array<[number, number] | number[]>
  first_turn: number | null
  last_turn: number | null
  event_count: number
  source_tools: string[]
  symbols: string[]
  functions: FunctionBlock[]
}

export type TurnSummary = {
  turn: number
  tool_count?: number
  tool_names: string[]
  new_files: string[]
  new_functions: FunctionBlock[]
  selected_files?: string[]
  llm_latency_ms?: number | null
  prompt_tokens?: number | null
  completion_tokens?: number | null
}

export type ExplorationTreeNode = {
  id: string
  kind: 'case' | 'turn' | 'tool' | 'file' | 'path' | 'function' | 'result' | 'note'
  status: string
  label: string
  detail?: string | null
  turn?: number
  tool_name?: string
  path?: string
  lines?: [number, number] | number[]
  latency_ms?: number | null
  is_success?: boolean | null
  children: ExplorationTreeNode[]
}

export type MetricsSnapshot = {
  file_recall?: number | null
  file_precision?: number | null
  turns_used?: number | null
  latency_s?: number | null
  [key: string]: unknown
}

export type SearchMapCase = {
  case_id: string
  query: string
  repo: string
  base_commit?: string | null
  semantic_hints: Array<{ filename: string; score: number }>
  ground_truth_files: Record<string, number[][]>
  ground_truth_context_files: Record<string, number[][]>
  ground_truth_functions: Array<{
    path: string
    name: string
    container?: string | null
    start_line?: number | null
    ranges: number[][]
  }>
  events: SearchMapEvent[]
  turn_summaries: TurnSummary[]
  file_blocks: FileBlock[]
  function_blocks: FunctionBlock[]
  selected_files: string[]
  unique_files: string[]
  unique_functions: FunctionBlock[]
  metrics_snapshot: MetricsSnapshot
  result_status: string
  exploration_tree: ExplorationTreeNode
}

export type CaseIntersectionResponse = {
  case_ids: string[]
}

export type CaseCompareRunExperiment = {
  root?: string | null
  [key: string]: unknown
}

export type CaseCompareRun = {
  run_id: string
  run_label: string
  experiment: CaseCompareRunExperiment
  search_config: Record<string, unknown>
  result_status: string
  case_map: SearchMapCase | null
}

export type PathMatrixStatus = {
  status?: string | null
  hinted?: boolean
  discovered?: boolean
  read?: boolean
  grep_hit?: boolean
  lsp_touched?: boolean
  selected?: boolean
  first_turn?: number | null
  last_turn?: number | null
  [key: string]: unknown
}

export type FunctionMatrixStatus = {
  status?: string | null
  access_kinds?: string[]
  [key: string]: unknown
}

export type CaseMapCompare = {
  schema_version: string
  kind: 'case_map_compare'
  case_id: string
  query: string
  repo: string
  ground_truth: {
    files: Record<string, number[][]>
    functions: Array<Record<string, unknown>>
    context_files: Record<string, number[][]>
  }
  runs: CaseCompareRun[]
  comparisons: {
    shared_files: string[]
    unique_files_by_run: Record<string, string[]>
    shared_functions: FunctionBlock[]
    unique_functions_by_run: Record<string, FunctionBlock[]>
    selected_overlap: string[]
    hint_overlap: string[]
    path_matrix: Array<{
      path: string
      ground_truth: boolean
      runs: Record<string, PathMatrixStatus>
    }>
    function_matrix: Array<{
      path: string
      function: string
      class?: string | null
      range: [number, number] | number[]
      ground_truth: boolean
      runs: Record<string, FunctionMatrixStatus>
    }>
    turn_curves: Record<
      string,
      {
        cumulative_unique_files: Array<[number, number] | number[]>
        cumulative_unique_functions: Array<[number, number] | number[]>
        ground_truth_file_recall: Array<[number, number] | number[]>
        ground_truth_function_recall: Array<[number, number] | number[]>
      }
    >
  }
}
