import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, FolderSearch } from 'lucide-react'
import { fetchExperiments } from '../lib/api'
import type { ExperimentSummary } from '../lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card'

function ExperimentRow({
  experiment,
  checked,
  onToggle,
}: {
  experiment: ExperimentSummary
  checked: boolean
  onToggle: (root: string) => void
}) {
  return (
    <tr className="border-t border-[var(--cds-border-subtle-01)] align-top">
      <td className="p-3">
        <input
          type="checkbox"
          checked={checked}
          onChange={() => onToggle(experiment.root)}
          aria-label={`Select ${experiment.name}`}
        />
      </td>
      <td className="p-3">
        <div className="type-body-compact-01 font-semibold text-[var(--cds-text-primary)]">
          {experiment.name}
        </div>
        <div className="type-label-01 text-[var(--cds-text-helper)]">{experiment.root}</div>
      </td>
      <td className="p-3 type-body-compact-01 text-[var(--cds-text-secondary)]">{experiment.type}</td>
      <td className="p-3 type-body-compact-01 text-[var(--cds-text-secondary)]">
        {experiment.provider ?? '-'} / {experiment.model ?? '-'}
      </td>
      <td className="p-3 type-body-compact-01 text-[var(--cds-text-secondary)]">
        {experiment.search_mode ?? '-'}
      </td>
      <td className="p-3 type-body-compact-01 text-[var(--cds-text-secondary)]">
        {experiment.max_turns ?? '-'}
      </td>
      <td className="p-3 type-body-compact-01 text-[var(--cds-text-secondary)]">
        {experiment.temperature ?? '-'}
      </td>
      <td className="p-3 type-body-compact-01 text-[var(--cds-text-secondary)]">
        {experiment.case_count ?? '-'}
      </td>
    </tr>
  )
}

export default function Experiments() {
  const navigate = useNavigate()
  const [selectedRoots, setSelectedRoots] = useState<string[]>([])
  const [providerFilter, setProviderFilter] = useState('')
  const [modeFilter, setModeFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')

  const experimentsQuery = useQuery({
    queryKey: ['experiments'],
    queryFn: fetchExperiments,
  })

  const experiments = experimentsQuery.data ?? []
  const providerOptions = useMemo(
    () =>
      Array.from(new Set(experiments.map((item) => item.provider).filter(Boolean))).sort() as string[],
    [experiments],
  )
  const modeOptions = useMemo(
    () =>
      Array.from(new Set(experiments.map((item) => item.search_mode).filter(Boolean))).sort() as string[],
    [experiments],
  )
  const typeOptions = useMemo(
    () => Array.from(new Set(experiments.map((item) => item.type).filter(Boolean))).sort(),
    [experiments],
  )

  const filtered = experiments.filter((experiment) => {
    if (providerFilter && experiment.provider !== providerFilter) {
      return false
    }
    if (modeFilter && experiment.search_mode !== modeFilter) {
      return false
    }
    if (typeFilter && experiment.type !== typeFilter) {
      return false
    }
    return true
  })

  const toggleRoot = (root: string) => {
    setSelectedRoots((current) =>
      current.includes(root) ? current.filter((item) => item !== root) : [...current, root],
    )
  }

  const openCompare = () => {
    const params = new URLSearchParams()
    selectedRoots.forEach((root) => params.append('root', root))
    navigate(`/compare?${params.toString()}`)
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Experiment Catalog</CardTitle>
            <p className="type-label-01 text-[var(--cds-text-helper)]">
              Select runs or grid trials, then open a same-case comparison view.
            </p>
          </div>
          <button
            type="button"
            disabled={selectedRoots.length === 0}
            onClick={openCompare}
            className="inline-flex items-center gap-2 rounded-[var(--cds-radius-md)] bg-[var(--cds-interactive)] px-4 py-2 type-body-compact-01 text-[var(--cds-text-on-color)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Compare Selected
            <ArrowRight className="h-4 w-4" />
          </button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <label className="type-label-01 text-[var(--cds-text-secondary)]">
              Provider
              <select
                value={providerFilter}
                onChange={(event) => setProviderFilter(event.target.value)}
                className="mt-1 block w-full rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] px-3 py-2 type-body-compact-01"
              >
                <option value="">All</option>
                {providerOptions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label className="type-label-01 text-[var(--cds-text-secondary)]">
              Search Mode
              <select
                value={modeFilter}
                onChange={(event) => setModeFilter(event.target.value)}
                className="mt-1 block w-full rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] px-3 py-2 type-body-compact-01"
              >
                <option value="">All</option>
                {modeOptions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label className="type-label-01 text-[var(--cds-text-secondary)]">
              Experiment Type
              <select
                value={typeFilter}
                onChange={(event) => setTypeFilter(event.target.value)}
                className="mt-1 block w-full rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] px-3 py-2 type-body-compact-01"
              >
                <option value="">All</option>
                {typeOptions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {experimentsQuery.isLoading ? (
            <div className="py-12 text-center type-body-compact-01 text-[var(--cds-text-helper)]">
              Loading experiments...
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <FolderSearch className="h-8 w-8 text-[var(--cds-text-helper)]" />
              <div className="type-body-compact-01 text-[var(--cds-text-helper)]">
                No experiments matched the current filters.
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead className="bg-[var(--cds-layer-02)] text-left">
                  <tr className="type-label-01 text-[var(--cds-text-helper)]">
                    <th className="p-3">Pick</th>
                    <th className="p-3">Experiment</th>
                    <th className="p-3">Type</th>
                    <th className="p-3">Model</th>
                    <th className="p-3">Mode</th>
                    <th className="p-3">Turns</th>
                    <th className="p-3">Temp</th>
                    <th className="p-3">Cases</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((experiment) => (
                    <ExperimentRow
                      key={experiment.root}
                      experiment={experiment}
                      checked={selectedRoots.includes(experiment.root)}
                      onToggle={toggleRoot}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
