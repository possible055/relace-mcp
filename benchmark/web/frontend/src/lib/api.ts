import axios from 'axios'
import type {
  CaseAnalysis,
  CaseDetail,
  CaseSummary,
  CaseTrace,
  ExperimentDetail,
  ExperimentSummary,
  MetricsSummary,
  PaginatedResponse,
} from './types'

const api = axios.create({
  baseURL: '/api',
})

export async function fetchExperiments(params?: {
  status?: string
  dataset?: string
  kind?: string
  limit?: number
  offset?: number
}): Promise<PaginatedResponse<ExperimentSummary>> {
  const { data } = await api.get<PaginatedResponse<ExperimentSummary>>('/experiments', { params })
  return data
}

export async function fetchExperiment(experimentId: string): Promise<ExperimentDetail> {
  const { data } = await api.get<ExperimentDetail>(`/experiments/${experimentId}`)
  return data
}

export async function fetchCases(
  experimentId: string,
  params?: {
    completed?: boolean
    limit?: number
    offset?: number
  }
): Promise<PaginatedResponse<CaseSummary>> {
  const { data } = await api.get<PaginatedResponse<CaseSummary>>(
    `/experiments/${experimentId}/cases`,
    { params }
  )
  return data
}

export async function fetchCase(experimentId: string, caseId: string): Promise<CaseDetail> {
  const { data } = await api.get<CaseDetail>(`/experiments/${experimentId}/cases/${caseId}`)
  return data
}

export async function fetchCaseTrace(
  experimentId: string,
  caseId: string
): Promise<CaseTrace> {
  const { data } = await api.get<CaseTrace>(`/experiments/${experimentId}/cases/${caseId}/trace`)
  return data
}

export async function fetchCaseAnalysis(
  experimentId: string,
  caseId: string
): Promise<CaseAnalysis> {
  const { data } = await api.get<CaseAnalysis>(`/experiments/${experimentId}/cases/${caseId}/analysis`)
  return data
}

export async function fetchMetricsSummary(experimentId: string): Promise<MetricsSummary> {
  const { data } = await api.get<MetricsSummary>(`/experiments/${experimentId}/metrics`)
  return data
}

export function apiErrorMessage(
  error: unknown,
  fallback = 'Request failed.'
): string {
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
