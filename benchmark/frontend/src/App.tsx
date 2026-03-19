import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/layout/Layout'
import CaseCompare from './pages/CaseCompare'
import Experiments from './pages/Experiments'
import RunDetail from './pages/RunDetail'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/experiments" element={<Experiments />} />
        <Route path="/compare" element={<CaseCompare />} />
        <Route path="/runs/:encodedRoot/cases/:caseId" element={<RunDetail />} />
      </Route>
      <Route path="/" element={<Navigate to="/experiments" replace />} />
    </Routes>
  )
}
