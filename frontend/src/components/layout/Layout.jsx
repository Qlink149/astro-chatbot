import { useLocation } from 'react-router-dom'
import { SidebarProvider, useSidebar } from '@/components/ui/sidebar'
import { AppSidebar } from './AppSidebar'
import { Menu } from 'lucide-react'
import { cn } from '@/lib/utils'

function MobileHeader() {
  const { toggleSidebar, isMobile } = useSidebar()
  if (!isMobile) return null
  return (
    <div
      className="relative shrink-0"
      style={{
        background: 'rgba(255,255,255,0.95)',
        borderBottom: '1px solid rgba(12,8,40,0.09)',
        boxShadow: '0 1px 2px rgba(12,8,40,0.04), 0 3px 16px rgba(12,8,40,0.04)',
        backdropFilter: 'blur(20px)',
      }}
    >
      <div
        className="absolute left-0 right-0 top-0 h-[2px]"
        style={{
          background:
            'linear-gradient(90deg, rgba(41,33,115,0.88) 0%, rgba(194,155,60,0.55) 52%, transparent 100%)',
        }}
      />
      <div className="flex items-center gap-3 px-4 h-14">
        <button
          type="button"
          className="brand-button-ghost flex h-8 w-8 items-center justify-center p-0"
          onClick={toggleSidebar}
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="text-sm font-bold" style={{ color: 'var(--text)' }}>Samara</span>
      </div>
    </div>
  )
}

export function Layout({ children }) {
  const isUsersRoute = useLocation().pathname.startsWith('/users')

  return (
    <div className="executive-shell min-h-screen">
      <div className="exec-blob-mid" />
      <SidebarProvider
        className="relative z-10 h-svh max-h-svh overflow-hidden"
        style={{ '--sidebar-width-icon': '4.5rem' }}
      >
        <AppSidebar />
        <main className="flex flex-1 flex-col min-w-0 min-h-0 overflow-hidden">
          <MobileHeader />
          <div className={cn(
            'flex flex-1 flex-col min-h-0 min-w-0 basis-0',
            isUsersRoute ? 'overflow-hidden p-0' : 'overflow-y-auto p-4 md:p-8'
          )}>
            {children}
          </div>
        </main>
      </SidebarProvider>
    </div>
  )
}
