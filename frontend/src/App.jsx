import { BrowserRouter, Routes, Route, Outlet } from 'react-router-dom'
import { Toaster } from 'sonner'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Layout } from '@/components/layout/Layout'
import ProtectedRoute from '@/components/ProtectedRoute'
import Overview from '@/pages/Overview'
import UsersPage from '@/pages/users/UsersPage'
import LoginPage from '@/pages/auth/LoginPage'
import NotFoundPage from '@/pages/NotFoundPage'

const queryClient = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <TooltipProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />

            <Route element={
              <ProtectedRoute>
                <Layout><Outlet /></Layout>
              </ProtectedRoute>
            }>
              <Route path="/" element={<Overview />} />
              <Route path="/users" element={<UsersPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Routes>
      </TooltipProvider>
      <Toaster position="top-right" richColors closeButton />
    </BrowserRouter>
    </QueryClientProvider>
  )
}
