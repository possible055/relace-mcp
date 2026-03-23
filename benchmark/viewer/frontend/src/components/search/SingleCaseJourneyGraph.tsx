import { useEffect, useMemo, useRef, useState } from 'react'
import cytoscape, { type Core, type EdgeSingular, type NodeSingular } from 'cytoscape'
import dagre from 'cytoscape-dagre'
import klay from 'cytoscape-klay'
import { ChevronLeft, ChevronRight, Search } from 'lucide-react'
import type {
  JourneyGraphEdge,
  JourneyGraphNode,
  JourneyGraphPayload,
  JourneyGraphTurn,
  SearchMapCase,
  SearchMapEvent,
} from '../../lib/types'
import { cn } from '../../lib/utils'

cytoscape.use(dagre)
cytoscape.use(klay)

type ViewMode = 'final' | 'delta' | 'cumulative'
type LayoutMode = 'klay' | 'dagre'

type SelectionState =
  | { kind: 'node'; nodeId: string }
  | { kind: 'edge'; edgeId: string }
  | { kind: 'none' }

const TURN_COLORS = [
  'var(--cds-chart-1)',
  'var(--cds-chart-2)',
  'var(--cds-chart-3)',
  'var(--cds-chart-4)',
  'var(--cds-chart-5)',
  'var(--cds-chart-6)',
  'var(--cds-chart-7)',
  'var(--cds-chart-8)',
]

function rangeLabel(range?: [number, number] | number[] | null): string | null {
  if (!range || range.length < 2) {
    return null
  }
  return `L${range[0]}-${range[1]}`
}

function eventRanges(event: SearchMapEvent): Array<[number, number] | number[]> {
  if (Array.isArray(event.ranges) && event.ranges.length > 0) {
    return event.ranges
  }
  return event.lines ? [event.lines] : []
}

function rangesLabel(ranges: Array<[number, number] | number[]>): string {
  if (ranges.length === 0) {
    return '(none)'
  }
  return ranges
    .map((range) => rangeLabel(range))
    .filter((value): value is string => Boolean(value))
    .join(', ')
}

function turnColor(turn?: number | null): string {
  if (typeof turn !== 'number' || turn <= 0) {
    return 'var(--cds-layer-hover-01)'
  }
  return TURN_COLORS[(turn - 1) % TURN_COLORS.length]
}

function kindShape(kind: JourneyGraphNode['kind']): string {
  switch (kind) {
    case 'query':
      return 'round-rectangle'
    case 'tool_call':
      return 'round-rectangle'
    case 'candidate_set':
      return 'round-rectangle'
    case 'file':
      return 'rectangle'
    case 'class':
      return 'ellipse'
    case 'function':
      return 'round-rectangle'
    case 'result':
      return 'diamond'
  }
}

function kindDimensions(kind: JourneyGraphNode['kind']): { width: number; height: number } {
  switch (kind) {
    case 'query':
      return { width: 280, height: 72 }
    case 'tool_call':
      return { width: 236, height: 72 }
    case 'candidate_set':
      return { width: 220, height: 72 }
    case 'file':
      return { width: 224, height: 72 }
    case 'class':
      return { width: 184, height: 64 }
    case 'function':
      return { width: 248, height: 76 }
    case 'result':
      return { width: 200, height: 72 }
  }
}

function compactList(values: string[], maxItems = 4): string {
  if (values.length === 0) {
    return '(none)'
  }
  if (values.length <= maxItems) {
    return values.join(', ')
  }
  return `${values.slice(0, maxItems).join(', ')} +${values.length - maxItems} more`
}

function backgroundColor(node: JourneyGraphNode): string {
  if (node.kind === 'query' || node.kind === 'result') {
    return 'var(--cds-layer-selected-01)'
  }
  if (node.kind === 'tool_call' || node.kind === 'candidate_set') {
    return 'var(--cds-layer-01)'
  }
  return 'var(--cds-layer-02)'
}

function borderColor(node: JourneyGraphNode): string {
  if (node.kind === 'query') {
    return 'var(--cds-support-info)'
  }
  if (node.kind === 'result') {
    return 'var(--cds-support-warning)'
  }
  if (node.status_flags.hit) {
    return 'var(--cds-support-warning)'
  }
  if (node.status_flags.selected) {
    return 'var(--cds-support-info)'
  }
  if (node.status_flags.inspected) {
    return 'var(--cds-border-strong-01)'
  }
  if (node.status_flags.candidate) {
    return turnColor(node.first_seen_turn)
  }
  if (node.status_flags.ground_truth || node.status_flags.ground_truth_context) {
    return 'var(--cds-support-success)'
  }
  if (node.status_flags.degraded) {
    return 'var(--cds-text-helper)'
  }
  return turnColor(node.first_seen_turn)
}

function edgeColor(edge: JourneyGraphEdge): string {
  switch (edge.kind) {
    case 'hint':
      return 'var(--cds-support-info)'
    case 'causal_exact':
      return 'var(--cds-support-warning)'
    case 'causal_temporal':
      return 'var(--cds-chart-3)'
    case 'produced_candidates':
      return 'var(--cds-chart-2)'
    case 'inspects':
      return 'var(--cds-border-strong-01)'
    case 'selects':
      return 'var(--cds-support-info)'
    case 'contains':
      return 'var(--cds-border-subtle-01)'
    case 'converges':
      return 'var(--cds-support-warning)'
    case 'next_step':
      return 'var(--cds-text-helper)'
  }
}

function edgeLineStyle(edge: JourneyGraphEdge): 'solid' | 'dashed' {
  if (
    edge.kind === 'hint' ||
    edge.kind === 'causal_temporal' ||
    edge.kind === 'contains' ||
    edge.kind === 'produced_candidates'
  ) {
    return 'dashed'
  }
  return 'solid'
}

function edgeWidth(edge: JourneyGraphEdge): number {
  if (edge.kind === 'converges') return 3.4
  if (edge.kind === 'causal_exact') return 3
  if (edge.kind === 'causal_temporal') return 2.6
  return 2
}

function edgeLabel(edge: JourneyGraphEdge): string {
  if (edge.kind === 'produced_candidates') {
    return compactList(edge.access_types, 1)
  }
  if (edge.kind === 'inspects') {
    return 'read'
  }
  if (edge.kind === 'selects') {
    return 'select'
  }
  if (edge.kind === 'causal_exact') {
    return 'exact'
  }
  if (edge.kind === 'causal_temporal') {
    return 'temporal'
  }
  if (edge.kind === 'next_step') {
    return 'next'
  }
  return edge.kind
}

function matchesSearch(node: JourneyGraphNode, term: string): boolean {
  const normalized = term.trim().toLowerCase()
  if (!normalized) {
    return false
  }
  return [
    node.label,
    node.path ?? '',
    node.class_name ?? '',
    node.function_name ?? '',
    node.tool_name ?? '',
    node.args_excerpt ?? '',
    ...(node.preview_paths ?? []),
    ...(node.candidate_paths ?? []),
  ]
    .join(' ')
    .toLowerCase()
    .includes(normalized)
}

function buildParentMap(edges: JourneyGraphEdge[]): Map<string, string[]> {
  const result = new Map<string, string[]>()
  for (const edge of edges) {
    if (edge.kind !== 'contains') {
      continue
    }
    const current = result.get(edge.target) ?? []
    current.push(edge.source)
    result.set(edge.target, current)
  }
  return result
}

function graphValidationMessage(graph: JourneyGraphPayload | null | undefined): string | null {
  if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
    return 'Journey graph payload is missing or invalid.'
  }
  if (graph.nodes.length === 0) {
    return 'Journey graph exists but contains no nodes.'
  }
  return null
}

function countFinalFiles(
  nodes: JourneyGraphNode[],
  predicate: (node: JourneyGraphNode) => boolean,
): number {
  return new Set(
    nodes
      .filter((node) => node.kind === 'file' && predicate(node))
      .map((node) => node.path)
      .filter((path): path is string => Boolean(path)),
  ).size
}

function shouldShowNodeByDefault(
  node: JourneyGraphNode,
  viewMode: ViewMode,
  activeTurnData: JourneyGraphTurn | null,
): boolean {
  if (viewMode === 'final') {
    if (node.kind === 'query' || node.kind === 'tool_call' || node.kind === 'result') {
      return true
    }
    return node.kind !== 'candidate_set' && node.status_flags.selected
  }

  if (node.kind === 'query' || node.kind === 'tool_call' || node.kind === 'candidate_set' || node.kind === 'result') {
    return true
  }
  if (node.kind === 'file') {
    return true
  }
  if ((node.kind === 'class' || node.kind === 'function') && node.status_flags.selected) {
    return true
  }
  if (activeTurnData && activeTurnData.selected_node_ids.includes(node.id)) {
    return true
  }
  return false
}

export default function SingleCaseJourneyGraph({
  graph,
  caseData,
}: {
  graph: JourneyGraphPayload
  caseData: SearchMapCase
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const cyRef = useRef<Core | null>(null)
  const [layoutMode, setLayoutMode] = useState<LayoutMode>(graph.meta.default_layout)
  const [viewMode, setViewMode] = useState<ViewMode>(graph.meta.default_view)
  const [activeTurn, setActiveTurn] = useState<number | null>(null)
  const [selection, setSelection] = useState<SelectionState>({ kind: 'none' })
  const [searchInput, setSearchInput] = useState('')
  const [searchTerm, setSearchTerm] = useState('')

  const validationMessage = graphValidationMessage(graph)
  const nodeMap = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes])
  const edgeMap = useMemo(() => new Map(graph.edges.map((edge) => [edge.id, edge])), [graph.edges])
  const parentMap = useMemo(() => buildParentMap(graph.edges), [graph.edges])
  const maxTurn = graph.meta.max_turn

  useEffect(() => {
    if (viewMode === 'final') {
      setActiveTurn(null)
      return
    }
    if (activeTurn == null) {
      setActiveTurn(Math.max(graph.meta.max_turn, 1))
    }
  }, [activeTurn, graph.meta.max_turn, viewMode])

  const activeTurnData = useMemo(() => {
    if (activeTurn == null) {
      return null
    }
    return graph.turns.find((turn) => turn.turn === activeTurn) ?? null
  }, [activeTurn, graph.turns])

  const finalCounts = useMemo(() => {
    const candidatePaths = new Set<string>()
    for (const node of graph.nodes) {
      if (node.kind === 'candidate_set' && node.candidate_access_type !== 'hint') {
        for (const path of node.candidate_paths ?? []) {
          candidatePaths.add(path)
        }
      }
    }
    return {
      candidates: candidatePaths.size,
      inspected: countFinalFiles(graph.nodes, (node) => node.status_flags.inspected),
      selected: countFinalFiles(graph.nodes, (node) => node.status_flags.selected),
    }
  }, [graph.nodes])

  const summaryCounts = activeTurnData
    ? {
        candidates: activeTurnData.summary.candidate_file_count,
        inspected: activeTurnData.summary.inspected_file_count,
        selected: activeTurnData.summary.selected_file_count,
      }
    : finalCounts

  const selectedNodeId = selection.kind === 'node' ? selection.nodeId : null
  const selectedNodePreview = selectedNodeId ? nodeMap.get(selectedNodeId) ?? null : null
  const selectedPath = selectedNodePreview?.path ?? null
  const selectedClass = selectedNodePreview?.class_name ?? null

  const visibleNodeIds = useMemo(() => {
    const result = new Set<string>()
    const activeNodeSet =
      viewMode === 'delta'
        ? new Set(activeTurnData?.delta_node_ids ?? [])
        : viewMode === 'cumulative'
          ? new Set(activeTurnData?.cumulative_node_ids ?? [])
          : null

    for (const node of graph.nodes) {
      const activeMatch = activeNodeSet == null || activeNodeSet.has(node.id)
      const searchMatch = searchTerm.trim() ? matchesSearch(node, searchTerm) : false
      const selectedMatch = selectedNodeId === node.id
      const samePathMatch =
        Boolean(selectedPath) &&
        node.path === selectedPath &&
        (node.kind === 'file' || node.kind === 'class' || node.kind === 'function')
      const sameClassMatch =
        Boolean(selectedClass) &&
        node.kind === 'function' &&
        node.path === selectedPath &&
        node.class_name === selectedClass

      if (!activeMatch && !searchMatch && !selectedMatch && !samePathMatch && !sameClassMatch) {
        continue
      }

      if (
        shouldShowNodeByDefault(node, viewMode, activeTurnData) ||
        searchMatch ||
        selectedMatch ||
        samePathMatch ||
        sameClassMatch
      ) {
        result.add(node.id)
      }
    }

    result.add('query')
    result.add('result')

    const queue = [...result]
    while (queue.length > 0) {
      const nodeId = queue.shift() as string
      for (const parentId of parentMap.get(nodeId) ?? []) {
        if (!result.has(parentId)) {
          result.add(parentId)
          queue.push(parentId)
        }
      }
    }
    return result
  }, [activeTurnData, graph.nodes, parentMap, searchTerm, selectedClass, selectedNodeId, selectedPath, viewMode])

  const visibleEdges = useMemo(() => {
    return graph.edges.filter((edge) => {
      if (!visibleNodeIds.has(edge.source) || !visibleNodeIds.has(edge.target)) {
        return false
      }
      if (viewMode === 'final' || activeTurnData == null) {
        return true
      }
      if (edge.kind === 'contains' || edge.kind === 'hint' || edge.kind === 'converges') {
        return true
      }
      return edge.turns.some((turn) =>
        viewMode === 'delta' ? turn === activeTurnData.turn : turn <= activeTurnData.turn,
      )
    })
  }, [activeTurnData, graph.edges, viewMode, visibleNodeIds])

  const selectedNode = selection.kind === 'node' ? nodeMap.get(selection.nodeId) ?? null : null
  const selectedEdge = selection.kind === 'edge' ? edgeMap.get(selection.edgeId) ?? null : null

  const selectedNodeEvents = useMemo(() => {
    if (!selectedNode) {
      return [] as SearchMapEvent[]
    }
    const sourceIds = new Set(selectedNode.source_event_ids)
    if (sourceIds.size > 0) {
      return caseData.events.filter((event, index) => {
        return (
          sourceIds.has(`event:${event.turn}:${event.tool_name}:${index}`) ||
          sourceIds.has(`degraded:${index}`)
        )
      })
    }
    if (selectedNode.path) {
      return caseData.events.filter((event) => event.path === selectedNode.path)
    }
    return [] as SearchMapEvent[]
  }, [caseData.events, selectedNode])

  useEffect(() => {
    if (!containerRef.current || validationMessage) {
      return
    }

    const elements = [
      ...graph.nodes
        .filter((node) => visibleNodeIds.has(node.id))
        .map((node) => {
          const size = kindDimensions(node.kind)
          const classes: string[] = []
          if (selection.kind === 'node' && selection.nodeId === node.id) {
            classes.push('is-selected')
          } else if (activeTurnData?.touched_node_ids.includes(node.id)) {
            classes.push('is-active-turn')
          }
          return {
            data: {
              id: node.id,
              label: node.label,
              shape: kindShape(node.kind),
              width: size.width,
              height: size.height,
              bgColor: backgroundColor(node),
              borderColor: borderColor(node),
            },
            classes: classes.join(' '),
          }
        }),
      ...visibleEdges.map((edge) => {
        const classes: string[] = []
        if (selection.kind === 'edge' && selection.edgeId === edge.id) {
          classes.push('is-selected')
        } else if (activeTurnData && edge.turns.includes(activeTurnData.turn)) {
          classes.push('is-active-turn')
        }
        return {
          data: {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            label: edgeLabel(edge),
            lineColor: edgeColor(edge),
            lineStyle: edgeLineStyle(edge),
            width: edgeWidth(edge),
          },
          classes: classes.join(' '),
        }
      }),
    ]
    const stylesheet: any = [
      {
        selector: 'node',
        style: {
          label: 'data(label)',
          shape: 'data(shape)',
          width: 'data(width)',
          height: 'data(height)',
          'background-color': 'data(bgColor)',
          'border-color': 'data(borderColor)',
          'border-width': 2,
          color: 'var(--cds-text-primary)',
          'font-size': 11,
          'text-wrap': 'wrap',
          'text-max-width': 168,
          'text-valign': 'center',
          'text-halign': 'center',
          padding: '8px',
        },
      },
      {
        selector: 'node.is-active-turn',
        style: {
          'overlay-color': 'var(--cds-support-info)',
          'overlay-opacity': 0.12,
        },
      },
      {
        selector: 'node.is-selected',
        style: {
          'border-width': 4,
          'border-color': 'var(--cds-focus)',
        },
      },
      {
        selector: 'edge',
        style: {
          label: 'data(label)',
          width: 'data(width)',
          'line-color': 'data(lineColor)',
          'target-arrow-color': 'data(lineColor)',
          'target-arrow-shape': 'triangle',
          'curve-style': 'taxi',
          'taxi-direction': 'rightward',
          'line-style': 'data(lineStyle)',
          color: 'var(--cds-text-helper)',
          'font-size': 10,
          'text-background-color': 'var(--cds-layer-01)',
          'text-background-opacity': 0.92,
          'text-background-padding': '2px',
        },
      },
      {
        selector: 'edge.is-selected',
        style: {
          width: 4.4,
          'line-color': 'var(--cds-focus)',
          'target-arrow-color': 'var(--cds-focus)',
        },
      },
      {
        selector: 'edge.is-active-turn',
        style: {
          width: 3.2,
        },
      },
    ]
    const layout: any =
      layoutMode === 'dagre'
        ? {
            name: 'dagre',
            rankDir: 'LR',
            nodeSep: 40,
            rankSep: 100,
            edgeSep: 20,
          }
        : {
            name: 'klay',
            fit: true,
            padding: 28,
            animate: false,
            klay: {
              direction: 'RIGHT',
              edgeRouting: 'ORTHOGONAL',
              spacing: 80,
              inLayerSpacingFactor: 1.6,
            },
          }

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: stylesheet,
      layout,
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
      selectionType: 'single',
    })

    cy.on('tap', 'node', (event) => {
      const node = event.target as NodeSingular
      setSelection({ kind: 'node', nodeId: node.id() })
    })
    cy.on('tap', 'edge', (event) => {
      const edge = event.target as EdgeSingular
      setSelection({ kind: 'edge', edgeId: edge.id() })
    })
    cy.on('tap', (event) => {
      if (event.target === cy) {
        setSelection({ kind: 'none' })
      }
    })

    cy.fit(undefined, 32)
    cyRef.current = cy
    return () => {
      cy.destroy()
      if (cyRef.current === cy) {
        cyRef.current = null
      }
    }
  }, [activeTurnData, graph.nodes, layoutMode, selection, validationMessage, visibleEdges, visibleNodeIds])

  const focusFirstMatch = () => {
    setSearchTerm(searchInput)
    const match = graph.nodes.find(
      (node) => visibleNodeIds.has(node.id) && matchesSearch(node, searchInput),
    )
    if (!match) {
      return
    }
    setSelection({ kind: 'node', nodeId: match.id })
    const cy = cyRef.current
    if (!cy) {
      return
    }
    const element = cy.getElementById(match.id)
    if (element.nonempty()) {
      cy.animate({ fit: { eles: element, padding: 80 } }, { duration: 220 })
    }
  }

  if (validationMessage) {
    return (
      <div className="rounded-[var(--cds-radius-md)] border border-[var(--cds-support-warning)]/30 bg-[var(--cds-support-warning)]/10 p-4 type-body-compact-01 text-[var(--cds-text-primary)]">
        {validationMessage}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[260px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--cds-icon-secondary)]" />
            <input
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  focusFirstMatch()
                }
              }}
              placeholder="Search nodes by path, symbol, or tool args"
              className="w-full rounded-[var(--cds-radius-md)] border border-[var(--cds-border-strong-01)] bg-[var(--cds-layer-01)] py-2 pl-9 pr-3 type-body-compact-01 text-[var(--cds-text-primary)]"
            />
          </div>
          <button
            type="button"
            onClick={focusFirstMatch}
            className="rounded-[var(--cds-radius-sm)] border border-[var(--cds-border-strong-01)] px-3 py-2 type-label-01 text-[var(--cds-text-primary)] hover:bg-[var(--cds-layer-hover-01)]"
          >
            Find
          </button>
          <button
            type="button"
            onClick={() => setLayoutMode('klay')}
            className={cn(
              'rounded-[var(--cds-radius-sm)] border px-2.5 py-1.5 type-label-01 transition-colors',
              layoutMode === 'klay'
                ? 'border-[var(--cds-border-interactive)] bg-[var(--cds-layer-selected-01)] text-[var(--cds-text-primary)]'
                : 'border-[var(--cds-border-subtle-01)] text-[var(--cds-text-helper)] hover:bg-[var(--cds-layer-hover-01)]',
            )}
          >
            Klay
          </button>
          <button
            type="button"
            onClick={() => setLayoutMode('dagre')}
            className={cn(
              'rounded-[var(--cds-radius-sm)] border px-2.5 py-1.5 type-label-01 transition-colors',
              layoutMode === 'dagre'
                ? 'border-[var(--cds-border-interactive)] bg-[var(--cds-layer-selected-01)] text-[var(--cds-text-primary)]'
                : 'border-[var(--cds-border-subtle-01)] text-[var(--cds-text-helper)] hover:bg-[var(--cds-layer-hover-01)]',
            )}
          >
            Dagre
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {(['final', 'delta', 'cumulative'] as ViewMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setViewMode(mode)}
              className={cn(
                'rounded-[var(--cds-radius-sm)] border px-2.5 py-1.5 type-label-01 transition-colors',
                viewMode === mode
                  ? 'border-[var(--cds-border-interactive)] bg-[var(--cds-layer-selected-01)] text-[var(--cds-text-primary)]'
                  : 'border-[var(--cds-border-subtle-01)] text-[var(--cds-text-helper)] hover:bg-[var(--cds-layer-hover-01)]',
              )}
            >
              {mode === 'final' ? 'Final' : mode === 'delta' ? 'Turn Delta' : 'Turn Cumulative'}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-[var(--cds-border-subtle-01)] pt-3">
          <span className="type-label-01 text-[var(--cds-text-helper)]">Turn</span>
          <button
            type="button"
            onClick={() => setActiveTurn(null)}
            className={cn(
              'rounded-[var(--cds-radius-sm)] border px-2.5 py-1.5 type-label-01 transition-colors',
              activeTurn == null
                ? 'border-[var(--cds-border-interactive)] bg-[var(--cds-layer-selected-01)] text-[var(--cds-text-primary)]'
                : 'border-[var(--cds-border-subtle-01)] text-[var(--cds-text-helper)] hover:bg-[var(--cds-layer-hover-01)]',
            )}
          >
            Final
          </button>
          <button
            type="button"
            onClick={() =>
              setActiveTurn((current) =>
                current == null ? Math.max(maxTurn, 1) : Math.max(current - 1, 1),
              )
            }
            disabled={maxTurn === 0}
            aria-label="Previous turn"
            className="rounded-[var(--cds-radius-sm)] border border-[var(--cds-border-subtle-01)] p-1.5 text-[var(--cds-text-primary)] disabled:opacity-40"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <input
            type="range"
            min={1}
            max={Math.max(maxTurn, 1)}
            value={activeTurn ?? Math.max(maxTurn, 1)}
            onChange={(event) => setActiveTurn(Number(event.target.value))}
            disabled={maxTurn === 0}
            className="w-56"
          />
          <button
            type="button"
            onClick={() =>
              setActiveTurn((current) =>
                current == null ? 1 : Math.min(current + 1, maxTurn),
              )
            }
            disabled={maxTurn === 0}
            aria-label="Next turn"
            className="rounded-[var(--cds-radius-sm)] border border-[var(--cds-border-subtle-01)] p-1.5 text-[var(--cds-text-primary)] disabled:opacity-40"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          <span className="type-body-compact-01 text-[var(--cds-text-secondary)]">
            {activeTurn == null ? 'Final convergence view' : `Turn ${activeTurn} / ${maxTurn}`}
          </span>
        </div>
      </div>

      {graph.meta.degraded ? (
        <div className="rounded-[var(--cds-radius-md)] border border-[var(--cds-support-warning)]/30 bg-[var(--cds-support-warning)]/10 p-4">
          <div className="type-heading-01 text-[var(--cds-text-primary)]">Degraded Graph</div>
          <div className="mt-2 type-body-compact-01 text-[var(--cds-text-primary)]">
            這份 bundle 缺少原始 trace turn 資料，因此只能顯示降級版 journey graph，無法可靠還原 tool-level 因果關係。
          </div>
          <div className="mt-1 type-label-01 text-[var(--cds-text-helper)]">
            Reasons: {compactList(graph.meta.degraded_reasons)}
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(340px,1fr)]">
        <div className="space-y-4">
          <div className="rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-02)] p-2">
            <div ref={containerRef} className="h-[720px] w-full" />
          </div>

          <div className="rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] p-4">
            <div className="type-heading-01 text-[var(--cds-text-primary)]">Turn Timeline</div>
            <div className="mt-3 space-y-2">
              {graph.turns.length > 0 ? (
                graph.turns.map((turn: JourneyGraphTurn) => (
                  <button
                    key={turn.turn}
                    type="button"
                    onClick={() => setActiveTurn(turn.turn)}
                    className={cn(
                      'w-full rounded-[var(--cds-radius-sm)] border px-3 py-2 text-left transition-colors',
                      activeTurn === turn.turn
                        ? 'border-[var(--cds-border-interactive)] bg-[var(--cds-layer-selected-01)]'
                        : 'border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-02)] hover:bg-[var(--cds-layer-hover-01)]',
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="type-label-02 text-[var(--cds-text-primary)]">
                        Turn {turn.turn}
                      </span>
                      <span className="type-label-01 text-[var(--cds-text-helper)]">
                        {compactList(turn.summary.tool_names, 3)}
                      </span>
                    </div>
                    <div className="mt-1 type-body-compact-01 text-[var(--cds-text-secondary)]">
                      C {turn.summary.candidate_file_count} · R {turn.summary.inspected_file_count} · S {turn.summary.selected_file_count}
                    </div>
                  </button>
                ))
              ) : (
                <div className="type-body-compact-01 text-[var(--cds-text-helper)]">
                  No turn data available.
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-[var(--cds-radius-md)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] p-4">
            <div className="type-heading-01 text-[var(--cds-text-primary)]">
              {selection.kind === 'node'
                ? 'Selected Node'
                : selection.kind === 'edge'
                  ? 'Selected Edge'
                  : activeTurnData
                    ? `Turn ${activeTurnData.turn}`
                    : 'Journey Summary'}
            </div>

            {selectedNode ? (
              <div className="mt-3 space-y-3">
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                    <div className="type-label-01 text-[var(--cds-text-helper)]">Kind</div>
                    <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                      {selectedNode.kind}
                    </div>
                  </div>
                  <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                    <div className="type-label-01 text-[var(--cds-text-helper)]">Turns</div>
                    <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                      T{String(selectedNode.first_seen_turn ?? '-')} - T
                      {String(selectedNode.last_seen_turn ?? '-')}
                    </div>
                  </div>
                </div>

                {selectedNode.path ? (
                  <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                    <div className="type-label-01 text-[var(--cds-text-helper)]">Path</div>
                    <code className="block break-all type-body-compact-01 text-[var(--cds-text-primary)]">
                      {selectedNode.path}
                    </code>
                  </div>
                ) : null}

                {selectedNode.tool_name ? (
                  <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                    <div className="type-label-01 text-[var(--cds-text-helper)]">Tool</div>
                    <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                      {selectedNode.tool_name}
                    </div>
                  </div>
                ) : null}

                {selectedNode.args_excerpt ? (
                  <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                    <div className="type-label-01 text-[var(--cds-text-helper)]">Arguments</div>
                    <code className="block whitespace-pre-wrap break-all type-body-compact-01 text-[var(--cds-text-primary)]">
                      {selectedNode.args_excerpt}
                    </code>
                  </div>
                ) : null}

                {selectedNode.kind === 'candidate_set' ? (
                  <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                    <div className="type-label-01 text-[var(--cds-text-helper)]">Candidate Files</div>
                    <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                      {selectedNode.candidate_count ?? selectedNode.candidate_paths.length}
                    </div>
                    <div className="mt-2 space-y-1.5">
                      {(selectedNode.candidate_paths ?? []).slice(0, 12).map((path) => (
                        <code
                          key={path}
                          className="block break-all rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-01)] px-2 py-1 type-label-01 text-[var(--cds-text-primary)]"
                        >
                          {path}
                        </code>
                      ))}
                      {(selectedNode.candidate_paths ?? []).length > 12 ? (
                        <div className="type-label-01 text-[var(--cds-text-helper)]">
                          +{(selectedNode.candidate_paths ?? []).length - 12} more
                        </div>
                      ) : null}
                    </div>
                  </div>
                ) : (
                  <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                    <div className="type-label-01 text-[var(--cds-text-helper)]">Ranges</div>
                    <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                      {rangesLabel(selectedNode.ranges)}
                    </div>
                  </div>
                )}

                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">Flags</div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {Object.entries(selectedNode.status_flags)
                      .filter(([, value]) => Boolean(value))
                      .map(([key]) => (
                        <span
                          key={key}
                          className="rounded bg-[var(--cds-layer-selected-01)] px-1.5 py-0.5 type-label-01 text-[var(--cds-text-primary)]"
                        >
                          {key}
                        </span>
                      ))}
                  </div>
                </div>

                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">Access Types</div>
                  <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                    {compactList(selectedNode.access_types)}
                  </div>
                </div>

                {selectedNodeEvents.length > 0 ? (
                  <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                    <div className="type-label-01 text-[var(--cds-text-helper)]">
                      Evidence Events
                    </div>
                    <div className="mt-2 space-y-2">
                      {selectedNodeEvents.slice(0, 8).map((event, index) => (
                        <div
                          key={`${event.turn}:${event.tool_name}:${event.path}:${index}`}
                          className="rounded-[var(--cds-radius-sm)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] px-3 py-2"
                        >
                          <div className="type-label-02 text-[var(--cds-text-primary)]">
                            Turn {event.turn} · {event.tool_name} · {event.access_type}
                          </div>
                          <div className="mt-1 type-label-01 text-[var(--cds-text-helper)]">
                            {event.path} · {rangesLabel(eventRanges(event))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : selectedEdge ? (
              <div className="mt-3 space-y-3">
                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">Kind</div>
                  <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                    {selectedEdge.kind}
                  </div>
                </div>
                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">Path</div>
                  <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                    {nodeMap.get(selectedEdge.source)?.label ?? selectedEdge.source} →{' '}
                    {nodeMap.get(selectedEdge.target)?.label ?? selectedEdge.target}
                  </div>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                    <div className="type-label-01 text-[var(--cds-text-helper)]">Turns</div>
                    <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                      {selectedEdge.turns.length > 0
                        ? `T${selectedEdge.turns.join(', T')}`
                        : '(none)'}
                    </div>
                  </div>
                  <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                    <div className="type-label-01 text-[var(--cds-text-helper)]">
                      Access Types
                    </div>
                    <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                      {compactList(selectedEdge.access_types)}
                    </div>
                  </div>
                </div>
                {selectedEdge.detail ? (
                  <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                    <div className="type-label-01 text-[var(--cds-text-helper)]">Detail</div>
                    <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                      {selectedEdge.detail}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : activeTurnData ? (
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">Tools</div>
                  <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                    {compactList(activeTurnData.summary.tool_names)}
                  </div>
                </div>
                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">LLM Latency</div>
                  <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                    {activeTurnData.summary.llm_latency_ms ?? '-'}
                  </div>
                </div>
                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">Candidates</div>
                  <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                    {String(activeTurnData.summary.candidate_file_count)}
                  </div>
                </div>
                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">Inspected</div>
                  <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                    {String(activeTurnData.summary.inspected_file_count)}
                  </div>
                </div>
                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">Selected</div>
                  <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                    {String(activeTurnData.summary.selected_file_count)}
                  </div>
                </div>
                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2 md:col-span-2">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">Candidate Groups</div>
                  <div className="mt-2 space-y-2">
                    {activeTurnData.summary.candidate_groups.length > 0 ? (
                      activeTurnData.summary.candidate_groups.map((group) => (
                        <div
                          key={group.node_id}
                          className="rounded-[var(--cds-radius-sm)] border border-[var(--cds-border-subtle-01)] bg-[var(--cds-layer-01)] px-3 py-2"
                        >
                          <div className="type-label-02 text-[var(--cds-text-primary)]">
                            {group.label} · {group.count}
                          </div>
                          <div className="mt-1 type-label-01 text-[var(--cds-text-helper)]">
                            {compactList(group.preview_paths, 4)}
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="type-body-compact-01 text-[var(--cds-text-helper)]">
                        No candidate groups in this turn.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">Candidates</div>
                  <div className="type-kpi-sm tabular-nums text-[var(--cds-text-primary)]">
                    {summaryCounts.candidates}
                  </div>
                </div>
                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">Inspected</div>
                  <div className="type-kpi-sm tabular-nums text-[var(--cds-text-primary)]">
                    {summaryCounts.inspected}
                  </div>
                </div>
                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">Selected</div>
                  <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                    {summaryCounts.selected}
                  </div>
                </div>
                <div className="rounded-[var(--cds-radius-sm)] bg-[var(--cds-layer-02)] px-3 py-2 md:col-span-3">
                  <div className="type-label-01 text-[var(--cds-text-helper)]">Current Mode</div>
                  <div className="type-body-compact-01 text-[var(--cds-text-primary)]">
                    {viewMode}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
