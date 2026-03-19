import axios from 'axios'
import type { CaseMapCompare, ExperimentSummary, SearchMapBundle } from './types'

const api = axios.create({
  baseURL: '/api',
})

export async function fetchExperiments(): Promise<ExperimentSummary[]> {
  const { data } = await api.get<ExperimentSummary[]>('/experiments')
  return data
}

export async function fetchBundle(experimentRoot: string): Promise<SearchMapBundle> {
  const { data } = await api.post<SearchMapBundle>('/search-map/bundle', {
    experiment_root: experimentRoot,
  })
  return data
}

export async function compareCase(
  caseId: string,
  experimentRoots: string[],
): Promise<CaseMapCompare> {
  const { data } = await api.post<CaseMapCompare>('/case-map/compare', {
    case_id: caseId,
    experiment_roots: experimentRoots,
  })
  return data
}
