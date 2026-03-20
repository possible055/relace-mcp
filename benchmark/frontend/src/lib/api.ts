import axios from 'axios'
import type {
  CaseIntersectionResponse,
  CaseMapCompare,
  ExperimentSummary,
  SearchMapCase,
} from './types'

const api = axios.create({
  baseURL: '/api',
})

export async function fetchExperiments(): Promise<ExperimentSummary[]> {
  const { data } = await api.get<ExperimentSummary[]>('/experiments')
  return data
}

export async function fetchCaseIntersection(
  experimentRoots: string[],
): Promise<CaseIntersectionResponse> {
  const { data } = await api.post<CaseIntersectionResponse>('/cases/intersection', {
    experiment_roots: experimentRoots,
  })
  return data
}

export async function fetchRunCaseDetail(
  experimentRoot: string,
  caseId: string,
): Promise<SearchMapCase> {
  const { data } = await api.post<SearchMapCase>('/run-case/detail', {
    experiment_root: experimentRoot,
    case_id: caseId,
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

export function apiErrorMessage(error: unknown, fallback = 'Request failed.'): string {
  if (axios.isAxiosError<{ detail?: unknown }>(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string' && detail) {
      return detail
    }
    if (typeof error.message === 'string' && error.message) {
      return error.message
    }
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

export function isApiNotFound(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 404
}
