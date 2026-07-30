import { useEffect, useCallback, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Users, MessageSquare, Sparkles, HelpCircle, Star, Zap, ArrowUpRight, TrendingUp, TrendingDown, X, RefreshCw } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { getDashboardStats, getUserGrowth, getModelMix } from '@/lib/api'
import { PageHeader } from '@/components/layout/PageHeader'
import { BRAND_COLORS, statIconClasses } from '@/components/charts/brandChartTheme'

function mapGrowthPeriod(period) {
  if (period === 'year') return 'year'
  if (period === 'week' || period === 'day') return 'week'
  if (period === 'month') return 'month'
  return 'month'
}

// ─── Filter ──────────────────────────────────────────────────────────────────

function PeriodFilter({ period, onFilter }) {
  const isFiltered = period !== 'all'

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Select
        value={period}
        onValueChange={(val) => onFilter({ period: val, startDate: '', endDate: '' })}
      >
        <SelectTrigger size="sm" className="w-36">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All</SelectItem>
          <SelectItem value="day">Day</SelectItem>
          <SelectItem value="week">Week</SelectItem>
          <SelectItem value="month">Month</SelectItem>
          <SelectItem value="year">Year</SelectItem>
        </SelectContent>
      </Select>

      <Tooltip>
        <TooltipTrigger asChild>
          <div className="hidden md:flex items-center gap-1.5 cursor-not-allowed">
            <input
              type="date"
              disabled
              className="h-7 rounded-md border border-[rgb(var(--navy-rgb)/0.12)] bg-white px-2 text-xs text-muted-foreground outline-none"
            />
            <span className="text-xs text-muted-foreground">→</span>
            <input
              type="date"
              disabled
              className="h-7 rounded-md border border-[rgb(var(--navy-rgb)/0.12)] bg-white px-2 text-xs text-muted-foreground outline-none"
            />
          </div>
        </TooltipTrigger>
        <TooltipContent>Date filtering coming soon</TooltipContent>
      </Tooltip>

      {isFiltered && (
        <button
          onClick={() => onFilter({ period: 'all', startDate: '', endDate: '' })}
          className="flex items-center gap-1 rounded-md px-2 h-7 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors border border-input"
        >
          <X className="h-3 w-3" /> Clear
        </button>
      )}
    </div>
  )
}

// ─── Stat card ───────────────────────────────────────────────────────────────

function StatCard({ label, description, icon: Icon, href, color, count, loading }) {
  const inner = (
    <div className="relative executive-card p-5 transition-all hover:shadow-md hover:-translate-y-0.5 duration-200">
      <div className="flex items-start justify-between">
        <div className={cn('flex h-10 w-10 items-center justify-center rounded-lg', color)}>
          <Icon className="h-5 w-5" />
        </div>
        {href && <ArrowUpRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />}
      </div>
      <div className="mt-4">
        {loading ? <Skeleton className="h-8 w-16 mb-1" /> : <p className="text-3xl font-bold tracking-tight">{count ?? '—'}</p>}
        <p className="text-sm font-medium mt-1">{label}</p>
        <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{description}</p>
      </div>
    </div>
  )
  if (href) return <Link to={href} className="group block">{inner}</Link>
  return <div>{inner}</div>
}

// ─── Ratings card ────────────────────────────────────────────────────────────

const SCORE_COLOR = { Excellent: 'text-[#22b07d]', Average: 'text-[#f59e0b]', Poor: 'text-[#d25f86]' }

function RatingsCard({ ratings, loading }) {
  const score = ratings?.avg_score
  return (
    <div className="executive-card p-5">
      <div className={cn('flex h-10 w-10 items-center justify-center rounded-lg', statIconClasses('warning'))}>
        <Star className="h-5 w-5" />
      </div>
      <div className="mt-4">
        {loading ? <Skeleton className="h-8 w-24 mb-1" /> : (
          <p className={cn('text-3xl font-bold tracking-tight', SCORE_COLOR[score] ?? 'text-foreground')}>{score ?? '—'}</p>
        )}
        <p className="text-sm font-medium mt-1">Customer Agent Feedback</p>
        <div className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
          {loading ? <Skeleton className="h-3 w-28" /> : ratings ? `${ratings.total_ratings} ratings on human agents` : 'No ratings yet'}
        </div>
        {!loading && ratings?.breakdown && (
          <div className="mt-3 flex flex-wrap gap-3 text-xs font-medium">
            <span className="text-[#22b07d]">{ratings.breakdown.excellent} excellent</span>
            <span className="text-[#f59e0b]">{ratings.breakdown.average} average</span>
            <span className="text-[#d25f86]">{ratings.breakdown.poor} poor</span>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Growth chart ────────────────────────────────────────────────────────────

function formatResponseTime(ms) {
  if (ms == null) return '—'
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`
}

function formatBucketLabel(str) {
  if (!str) return ''
  if (str.includes('T')) {
    const [datePart, hourPart] = str.split('T')
    const [y, m, d] = datePart.split('-')
    const hour = parseInt(hourPart, 10)
    const ampm = hour === 0 ? '12 AM' : hour < 12 ? `${hour} AM` : hour === 12 ? '12 PM' : `${hour - 12} PM`
    const dateLabel = new Date(+y, +m - 1, +d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
    return `${dateLabel}, ${ampm}`
  }
  if (str.includes('-W')) {
    const week = parseInt(str.split('-W')[1], 10)
    return `W${week}`
  }
  if (/^\d{4}$/.test(str)) return str
  if (/^\d{4}-\d{2}$/.test(str)) {
    const [y, m] = str.split('-')
    return new Date(+y, +m - 1).toLocaleDateString('en-IN', { month: 'short' })
  }
  const [y, m, d] = str.split('-')
  return new Date(+y, +m - 1, +d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

function GrowthChart({ data, barColor, loading, unavailable }) {
  if (loading) {
    return (
      <div className="mt-3">
        <div className="flex items-end gap-0.75 h-24">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="flex-1 rounded-t-sm bg-muted animate-pulse" style={{ height: `${20 + (i % 5) * 16}%` }} />
          ))}
        </div>
      </div>
    )
  }

  if (unavailable) {
    return (
      <div className="h-24 mt-3 flex items-center justify-center text-sm text-muted-foreground border border-dashed rounded-lg">
        Analytics coming soon
      </div>
    )
  }

  if (!data?.length) {
    return <div className="h-24 mt-3 flex items-center justify-center text-sm text-muted-foreground">No data for this period</div>
  }

  const max = Math.max(...data.map(d => d.count), 1)
  const step = Math.max(1, Math.floor(data.length / 6))

  return (
    <div className="mt-3 select-none">
      <div className="relative flex items-end gap-0.75 h-24">
        {data.map((d, i) => {
          const pct = Math.max((d.count / max) * 100, 4)
          const showLabel = i % step === 0
          return (
            <div key={i} className="group relative flex-1 h-full">
              <div className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-20 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
                <div className="bg-popover border rounded-lg shadow-lg px-2.5 py-1.5 text-xs whitespace-nowrap">
                  <p className="font-semibold text-foreground">{d.count}</p>
                  <p className="text-muted-foreground text-[10px] mt-0.5">{formatBucketLabel(d.period)}</p>
                </div>
              </div>
              {showLabel && (
                <span
                  className="absolute left-0 right-0 text-center text-[10px] font-semibold text-muted-foreground leading-none pointer-events-none"
                  style={{ bottom: `calc(${pct}% + 4px)` }}
                >
                  {d.count}
                </span>
              )}
              <div
                className="absolute bottom-0 left-0 right-0 rounded-t-sm transition-all duration-300"
                style={{
                  height: `${pct}%`,
                  backgroundColor: barColor,
                  opacity: 0.3 + (i / Math.max(data.length - 1, 1)) * 0.7,
                }}
              />
            </div>
          )
        })}
      </div>
      <div className="flex gap-0.75 mt-2">
        {data.map((d, i) => (
          <div key={i} className="flex-1 min-w-0 text-center">
            {i % step === 0 && (
              <span className="text-[10px] text-muted-foreground leading-none">
                {formatBucketLabel(d.period)}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function GrowthCard({ title, icon: Icon, iconBg, barColor, data, loading, unavailable }) {
  const last = data?.[data.length - 1]?.count ?? 0
  const prev = data?.[data.length - 2]?.count ?? 0
  const trendPct = !loading && !unavailable && (data?.length ?? 0) >= 2 && prev > 0
    ? Math.round(((last - prev) / prev) * 100)
    : null
  const up = (trendPct ?? 0) >= 0

  return (
    <div className="executive-card chart-surface p-5 flex flex-col md:flex-row gap-6 items-start">
      <div className="w-44 shrink-0">
        <div className={cn('flex h-10 w-10 items-center justify-center rounded-lg', iconBg)}>
          <Icon className="h-5 w-5" />
        </div>
        <div className="mt-4">
          {loading ? <Skeleton className="h-8 w-16" /> : unavailable ? (
            <p className="text-sm text-muted-foreground">—</p>
          ) : (
            <div className="flex items-baseline gap-2">
              <p className="text-3xl font-bold tracking-tight">{last}</p>
              {trendPct !== null && (
                <span className={cn('flex items-center gap-0.5 text-xs font-medium', up ? 'text-[#22b07d]' : 'text-[#d25f86]')}>
                  {up ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                  {Math.abs(trendPct)}%
                </span>
              )}
            </div>
          )}
          <p className="text-sm font-medium mt-1">{title}</p>
          <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
            {loading ? '' : unavailable ? 'Analytics coming soon' : (data?.length ? `${data.length} data points` : 'No data')}
          </p>
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <GrowthChart data={data} barColor={barColor} loading={loading} unavailable={unavailable} />
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Overview() {
  const [searchParams, setSearchParams] = useSearchParams()
  const period = searchParams.get('period') || 'all'

  const setFilter = ({ period: p } = {}) => {
    setSearchParams(prev => {
      const params = new URLSearchParams(prev)
      if (p !== undefined) { p && p !== 'all' ? params.set('period', p) : params.delete('period') }
      params.delete('start_date')
      params.delete('end_date')
      return params
    }, { replace: true })
  }

  const [stats, setStats] = useState(null)
  const [userGrowth, setUserGrowth] = useState(null)
  const [userGrowthUnavailable, setUserGrowthUnavailable] = useState(false)
  const [modelMix, setModelMix] = useState(null)
  const [loading, setLoading] = useState(true)
  const [lastSync, setLastSync] = useState(null)
  const intervalRef = useRef(null)

  const fetchStats = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true)
    const growthPeriod = mapGrowthPeriod(period)

    try {
      const [statsData, userGrowthRes, modelMixRes] = await Promise.all([
        getDashboardStats({ period }),
        getUserGrowth(growthPeriod).catch(() => null),
        getModelMix(7).catch(() => null),
      ])

      setStats(statsData)
      setLastSync(new Date())

      setUserGrowth(userGrowthRes?.data ?? null)
      setUserGrowthUnavailable(userGrowthRes == null)
      setModelMix(modelMixRes)
    } catch {
      setStats(null)
      setUserGrowth(null)
      setUserGrowthUnavailable(true)
      setModelMix(null)
    } finally {
      setLoading(false)
    }
  }, [period])

  useEffect(() => {
    fetchStats(true)
  }, [fetchStats])

  useEffect(() => {
    intervalRef.current = setInterval(() => fetchStats(false), 30_000)
    return () => clearInterval(intervalRef.current)
  }, [fetchStats])

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description={`${new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })} — Here's what's in the system.`}
        action={
          <div className="flex flex-col items-end gap-2">
            <PeriodFilter period={period} onFilter={setFilter} />
            <div className="flex items-center gap-2">
              {lastSync && (
                <span className="text-xs text-muted-foreground font-medium">
                  Last synced {lastSync.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })}
                </span>
              )}
              <button
                onClick={() => fetchStats(true)}
                disabled={loading}
                className="brand-button-ghost flex items-center gap-1.5 px-2.5 h-7 text-xs disabled:opacity-50"
              >
                <RefreshCw className={cn('h-3 w-3', loading && 'animate-spin')} />
                Refresh
              </button>
            </div>
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard label="Total Users" description="Seekers on WhatsApp" icon={Users} href="/users" color={statIconClasses('primary')} count={stats?.total_users} loading={loading} />
        <StatCard label="Messages" description={stats ? `${stats.avg_messages_per_user?.toFixed(1) ?? '—'} avg per user` : 'Avg per user'} icon={MessageSquare} color={statIconClasses('deep')} count={stats?.total_messages} loading={loading} />
        <StatCard label="Readings Delivered" description="Free kundli readings sent" icon={Sparkles} color={statIconClasses('soft')} count={stats?.total_readings} loading={loading} />
        <StatCard label="Beat 1 sent" description="Identity punches delivered" icon={Sparkles} color={statIconClasses('soft')} count={stats?.total_beat1_sent ?? stats?.funnel?.beat1_sent} loading={loading} />
        <StatCard label="Topics chosen" description="Topic picker taps" icon={HelpCircle} color={statIconClasses('warning')} count={stats?.total_topics_chosen ?? stats?.funnel?.topic_chosen} loading={loading} />
        <StatCard label="Free deep answers" description="Beat 4 answers delivered" icon={Sparkles} color={statIconClasses('success')} count={stats?.total_free_deep_answers ?? stats?.funnel?.free_deep_answer_sent} loading={loading} />
        <StatCard label="Date confirm rate" description="Beat 2b confirmed / offered" icon={Sparkles} color={statIconClasses('success')} count={loading ? null : (stats?.date_confirmation_rate != null ? `${Math.round(stats.date_confirmation_rate * 100)}%` : '—')} loading={loading} />
        <StatCard label="Gate shown" description="Paywall impressions" icon={HelpCircle} color={statIconClasses('warning')} count={stats?.total_gate_shown ?? stats?.funnel?.gate_shown} loading={loading} />
        <StatCard label="Payments succeeded" description="Razorpay success events" icon={Zap} color={statIconClasses('success')} count={stats?.total_payment_succeeded ?? stats?.funnel?.payment_succeeded} loading={loading} />
        <StatCard label="Follow-up Questions" description="Questions after free path" icon={HelpCircle} color={statIconClasses('warning')} count={stats?.total_followup_questions} loading={loading} />
        <StatCard label="AI Response Time" description="Average across all messages" icon={Zap} color={statIconClasses('success')} count={loading ? null : formatResponseTime(stats?.avg_ai_response_time_ms)} loading={loading} />
        <RatingsCard ratings={stats?.ratings} loading={loading} />
        <div className="col-span-full">
          <GrowthCard title="User Growth" icon={Users} iconBg={statIconClasses('primary')} barColor={BRAND_COLORS.primary} data={userGrowth} loading={loading} unavailable={userGrowthUnavailable} />
        </div>
        {!loading && stats?.funnel && (
          <div className="col-span-full executive-card p-5">
            <p className="text-sm font-medium mb-3">Conversation funnel</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 text-xs">
              {Object.entries(stats.funnel).map(([key, val]) => (
                <div key={key} className="rounded-md border border-[rgb(var(--navy-rgb)/0.08)] px-3 py-2">
                  <p className="text-muted-foreground">{key.replace(/_/g, ' ')}</p>
                  <p className="text-lg font-semibold mt-0.5">{val}</p>
                </div>
              ))}
            </div>
          </div>
        )}
        {!loading && modelMix && (
          <div className="col-span-full executive-card p-5">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-medium">Model mix &amp; cost (last 7 days)</p>
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                <span>Total cost: <strong className="text-foreground">${modelMix.total_cost_usd?.toFixed(4)}</strong></span>
                <span>Cost/conversation: <strong className="text-foreground">${modelMix.cost_per_conversation_usd?.toFixed(4)}</strong></span>
                <span>Active users: <strong className="text-foreground">{modelMix.active_users_with_chat}</strong></span>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
              {(modelMix.by_model || []).map((m) => (
                <div key={m.model} className="rounded-md border border-[rgb(var(--navy-rgb)/0.08)] px-3 py-2">
                  <p className="font-medium text-foreground truncate">{m.model}</p>
                  <div className="mt-1 space-y-0.5 text-muted-foreground">
                    <p>{m.requests} requests · {m.pct_of_cost}% of cost</p>
                    <p>${m.estimated_cost_usd?.toFixed(4)} · {((m.prompt_tokens || 0) + (m.completion_tokens || 0)).toLocaleString()} tokens</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
