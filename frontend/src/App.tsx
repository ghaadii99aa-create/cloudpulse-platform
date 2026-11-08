import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Shell } from './components/Shell';
import { Loading } from './components/ui';
import { useAuth } from './lib/auth';
import Login from './pages/Login';

const Overview = lazy(() => import('./pages/Overview'));
const Infrastructure = lazy(() => import('./pages/Infrastructure'));
const ResourceDetail = lazy(() => import('./pages/ResourceDetail'));
const Costs = lazy(() => import('./pages/Costs'));
const Forecasts = lazy(() => import('./pages/Forecasts'));
const Kubernetes = lazy(() => import('./pages/Kubernetes'));
const ServiceMap = lazy(() => import('./pages/ServiceMap'));
const Alerts = lazy(() => import('./pages/Alerts'));
const Advisor = lazy(() => import('./pages/Advisor'));
const Reports = lazy(() => import('./pages/Reports'));
const System = lazy(() => import('./pages/System'));
const NotFound = lazy(() => import('./pages/NotFound'));

function Protected() {
  const { user, restoring } = useAuth();
  const location = useLocation();
  if (restoring) return <div className="p-8"><Loading /></div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Shell />;
}

export default function App() {
  return (
    <Suspense fallback={<div className="p-8"><Loading /></div>}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Protected />}>
          <Route index element={<Overview />} />
          <Route path="infrastructure" element={<Infrastructure />} />
          <Route path="infrastructure/:name" element={<ResourceDetail />} />
          <Route path="costs" element={<Costs />} />
          <Route path="forecasts" element={<Forecasts />} />
          <Route path="kubernetes" element={<Kubernetes />} />
          <Route path="map" element={<ServiceMap />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="advisor" element={<Advisor />} />
          <Route path="reports" element={<Reports />} />
          <Route path="system" element={<System />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
