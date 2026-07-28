import { NavLink, useLocation } from 'react-router-dom'
import { logout } from '@/lib/api'
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarFooter,
  useSidebar,
} from '@/components/ui/sidebar'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  Users,
  PanelLeftClose,
  PanelLeftOpen,
  MoonStar,
  ShieldCheck,
  LogOut,
} from 'lucide-react'

const navGroups = [
  {
    label: 'Main',
    items: [
      { to: '/', label: 'Overview', icon: LayoutDashboard, exact: true },
      { to: '/users', label: 'Users', icon: Users },
    ],
  },
]

function NavItem({ to, label, icon: Icon, exact }) {
  const location = useLocation()
  const { state } = useSidebar()
  const collapsed = state === 'collapsed'

  const isActive = exact
    ? location.pathname === to
    : location.pathname.startsWith(to)

  return (
    <NavLink
      to={to}
      title={collapsed ? label : undefined}
      className={cn(
        'group flex items-center gap-3 rounded-lg text-sm font-medium transition-all duration-150',
        collapsed
          ? 'justify-center px-0 py-1 bg-transparent hover:bg-transparent border-transparent'
          : cn(
              'px-3 py-2.5',
              isActive ? 'nav-link-active' : 'nav-link-idle'
            )
      )}
    >
      {collapsed ? (
        <span className={cn(
          'flex h-10 w-10 items-center justify-center rounded-xl transition-colors',
          isActive
            ? 'nav-link-active'
            : 'nav-link-idle hover:bg-[rgba(12,8,40,0.055)]'
        )}>
          <Icon className={cn('nav-icon h-5 w-5 shrink-0', isActive ? '' : '')} />
        </span>
      ) : (
        <>
          <Icon className="nav-icon h-4 w-4 shrink-0" />
          <span>{label}</span>
        </>
      )}
    </NavLink>
  )
}

export function AppSidebar() {
  const { toggleSidebar, state } = useSidebar()
  const collapsed = state === 'collapsed'

  async function handleLogout() {
    try { await logout() } catch {}
    window.location.href = '/login'
  }

  return (
    <Sidebar collapsible="icon" className="border-r-0 relative">
      <div
        className="absolute left-0 right-0 top-0 h-[2px] z-10"
        style={{
          background:
            'linear-gradient(90deg, rgba(41,33,115,0.88) 0%, rgba(194,155,60,0.55) 52%, transparent 100%)',
        }}
      />

      {/* Brand */}
      <SidebarHeader className={cn('pt-5 pb-5 relative', collapsed ? 'px-0 flex items-center justify-center' : 'px-4')}>
        <div className={cn('flex items-center gap-3', collapsed && 'justify-center')}>
          <div
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-lg"
            style={{
              background: 'linear-gradient(135deg, #d9bc72 0%, #c29b3c 40%, #292173 100%)',
              boxShadow: '0 8px 24px rgba(194,155,60,0.28)',
            }}
          >
            <MoonStar className="h-4 w-4 text-white" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <p className="text-sm font-bold leading-none" style={{ color: 'var(--text)' }}>Samara</p>
              <p className="text-[11px] mt-1 leading-none text-muted-foreground">by Clara</p>
            </div>
          )}
        </div>
      </SidebarHeader>

      {/* Nav */}
      <SidebarContent className={cn('', collapsed ? 'px-2' : 'px-3')}>
        <div className="space-y-6">
          {navGroups.map(({ label, items }) => (
            <div key={label}>
              {!collapsed && (
                <p
                  className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground"
                >
                  {label}
                </p>
              )}
              {collapsed && <div className="mb-2 h-px mx-1" style={{ background: 'rgba(12,8,40,0.08)' }} />}
              <div className="space-y-0.5">
                {items.map((item) => (
                  <NavItem key={item.to} {...item} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </SidebarContent>

      {/* Footer */}
      <SidebarFooter className={cn('py-4 space-y-3', collapsed ? 'px-2' : 'px-4')}>
        {/* Admin badge */}
        {!collapsed ? (
          <div
            className="flex items-center gap-3 rounded-lg px-3 py-2.5"
            style={{
              background: 'rgb(var(--royal-rgb) / 0.06)',
              border: '1px solid rgb(var(--royal-rgb) / 0.12)',
            }}
          >
            <div
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
              style={{ background: 'rgb(var(--violet-rgb) / 0.12)' }}
            >
              <ShieldCheck className="h-3.5 w-3.5" style={{ color: 'var(--violet)' }} />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium leading-none" style={{ color: 'var(--text)' }}>Admin</p>
              <p className="text-[11px] mt-1 leading-none text-muted-foreground">Internal access</p>
            </div>
          </div>
        ) : (
          <div className="flex justify-center">
            <div
              className="flex h-8 w-8 items-center justify-center rounded-full"
              style={{ background: 'rgb(var(--violet-rgb) / 0.12)' }}
              title="Admin"
            >
              <ShieldCheck className="h-3.5 w-3.5" style={{ color: 'var(--violet)' }} />
            </div>
          </div>
        )}

        <div className="space-y-1">
          {/* Logout button */}
          <button
            onClick={handleLogout}
            title={collapsed ? 'Log out' : undefined}
            className={cn(
              'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
              'text-[#d25f86] hover:bg-[rgba(210,95,134,0.08)] hover:text-[#d25f86]',
              collapsed && 'justify-center px-2'
            )}
          >
            <LogOut className="h-4 w-4" />
            {!collapsed && <span>Log out</span>}
          </button>

          {/* Collapse toggle */}
          <button
            onClick={toggleSidebar}
            title={collapsed ? 'Expand' : 'Collapse'}
            className={cn(
              'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors nav-link-idle',
              collapsed && 'justify-center px-2'
            )}
          >
            {collapsed
              ? <PanelLeftOpen className="nav-icon h-4 w-4" />
              : <><PanelLeftClose className="nav-icon h-4 w-4" /><span>Collapse</span></>
            }
          </button>
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}
