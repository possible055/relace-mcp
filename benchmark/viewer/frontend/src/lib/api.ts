import axios from 'axios'
import type { ExperimentSummary } from './types'

const api = axios.create({
  baseURL: '/api',
})

export async function fetchExperiments(): Promise<ExperimentSummary[]> {
  const { data } = await api.get<ExperimentSummary[]>('/experiments')
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
