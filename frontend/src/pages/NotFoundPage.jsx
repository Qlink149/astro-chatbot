import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Home } from 'lucide-react'

export default function NotFoundPage() {
  const navigate = useNavigate()

  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] text-center px-4 space-y-6">
      <div className="flex justify-center mb-4">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-zinc-100 text-zinc-900 shadow-sm border">
          <span className="text-2xl font-bold tracking-widest">404</span>
        </div>
      </div>
      
      <div className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Page not found</h1>
        <p className="text-zinc-500 max-w-sm mx-auto">
          We couldn't locate the page you're looking for. It might have been moved or permanently deleted.
        </p>
      </div>

      <div className="pt-4">
        <Button onClick={() => navigate('/')} className="gap-2">
          <Home className="h-4 w-4" />
          Back to Dashboard
        </Button>
      </div>
    </div>
  )
}
