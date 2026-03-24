import { Suspense, lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/layout/Layout'

const Experiments = lazy(() => import('./pages/Experiments'))
const ExperimentDetail = lazy(() => import('./pages/ExperimentDetail'))
const Cases = lazy(() => import('./pages/Cases'))
const CaseDetail = lazy(() => import('./pages/CaseDetail'))

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
          <Route path="/experiments/:experimentId" element={<ExperimentDetail />} />
          <Route path="/experiments/:experimentId/cases" element={<Cases />} />
          <Route path="/experiments/:experimentId/cases/:caseId" element={<CaseDetail />} />
        </Route>
        <Route path="/" element={<Navigate to="/experiments" replace />} />
        <Route path="*" element={<Navigate to="/experiments" replace />} />
      </Routes>
    </Suspense>
  )
}
