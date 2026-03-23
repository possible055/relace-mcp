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
