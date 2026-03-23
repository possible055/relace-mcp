import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/layout/Layout'

const Experiments = lazy(() => import('./pages/Experiments'))
const CaseCompare = lazy(() => import('./pages/CaseCompare'))
const RunDetail = lazy(() => import('./pages/RunDetail'))

function RouteFallback() {
  return (
    <div className="p-6 type-body-compact-01 text-[var(--cds-text-helper)]">
      Loading page...
    </div>
  )
}

export default function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/experiments" element={<Experiments />} />
          <Route path="/compare" element={<CaseCompare />} />
          <Route path="/runs/:encodedRoot/cases/:caseId" element={<RunDetail />} />
        </Route>
        <Route path="/" element={<Navigate to="/experiments" replace />} />
      </Routes>
    </Suspense>
  )
}
