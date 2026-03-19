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
  metrics_snapshot: Record<string, unknown>
  result_status: string
}

export type SearchMapBundle = {
  schema_version: string
  kind: 'search_map_bundle'
  experiment: {
    name: string
    root: string
    type: string
    search?: {
      provider?: string | null
      model?: string | null
      max_turns?: number | null
      temperature?: number | null
      prompt_file?: string | null
    }
    run?: {
      search_mode?: string | null
    }
  }
  summary: Record<string, unknown>
  cases: SearchMapCase[]
}

export type CaseCompareRun = {
  run_label: string
  experiment: Record<string, unknown>
  search_config: Record<string, unknown>
  result_status: string
  case_map: SearchMapCase | null
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
      runs: Record<string, Record<string, unknown>>
    }>
    function_matrix: Array<{
      path: string
      function: string
      class?: string | null
      range: [number, number] | number[]
      ground_truth: boolean
      runs: Record<string, Record<string, unknown>>
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
