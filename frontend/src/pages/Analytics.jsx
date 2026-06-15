/**
 * frontend/src/pages/Analytics.jsx
 *
 * Summary stats + charts:
 * - Summary cards (jobs seen, saved, applied, response rate)
 * - Bar chart: top 10 sources by match volume
 * - Line chart: jobs per day (last 30 days)
 * - Score distribution histogram
 */

import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  LineChart, Line, CartesianGrid, Area, AreaChart,
} from 'recharts'
import { supabase } from '../lib/supabase'

const COLORS = ['#6470f3', '#7c85f5', '#9399f7', '#abaef9', '#c3c6fb']

function StatCard({ label, value, sub, color = 'brand' }) {
  const colorMap = {
    brand:   'text-brand-400 bg-brand-900/30 border-brand-800/30',
    green:   'text-emerald-400 bg-emerald-900/30 border-emerald-800/30',
    yellow:  'text-yellow-400 bg-yellow-900/30 border-yellow-800/30',
    purple:  'text-purple-400 bg-purple-900/30 border-purple-800/30',
  }
  return (
    <div className={`card border ${colorMap[color]} flex flex-col gap-1`}>
      <p className="text-xs text-gray-500 uppercase tracking-wider font-semibold">{label}</p>
      <p className={`text-3xl font-bold ${colorMap[color].split(' ')[0]}`}>{value}</p>
      {sub && <p className="text-xs text-gray-500">{sub}</p>}
    </div>
  )
}

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload?.length) {
    return (
      <div className="glass px-3 py-2 text-xs">
        <p className="text-gray-300 font-medium">{label}</p>
        <p className="text-brand-300">{payload[0].value} jobs</p>
      </div>
    )
  }
  return null
}

export default function Analytics() {
  const [stats, setStats] = useState({ seen: 0, saved: 0, applied: 0, rejected: 0 })
  const [sourceData, setSourceData] = useState([])
  const [timeData, setTimeData] = useState([])
  const [scoreData, setScoreData] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadAnalytics()
  }, [])

  async function loadAnalytics() {
    setLoading(true)
    try {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) return

      // Status counts
      const { data: matchData } = await supabase
        .from('job_matches')
        .select('status, match_score, created_at, jobs(job_sources(name))')
        .eq('user_id', user.id)

      if (!matchData) return

      // Compute stats
      const statusCounts = { new: 0, seen: 0, saved: 0, applied: 0, rejected: 0 }
      matchData.forEach(m => { statusCounts[m.status] = (statusCounts[m.status] || 0) + 1 })
      setStats({
        seen: (statusCounts.seen || 0) + (statusCounts.new || 0),
        saved: statusCounts.saved || 0,
        applied: statusCounts.applied || 0,
        rejected: statusCounts.rejected || 0,
      })

      // Top sources
      const sourceCounts = {}
      matchData.forEach(m => {
        const src = m.jobs?.job_sources?.name || 'Unknown'
        sourceCounts[src] = (sourceCounts[src] || 0) + 1
      })
      const sortedSources = Object.entries(sourceCounts)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 10)
        .map(([name, count]) => ({ name: name.length > 15 ? name.slice(0, 15) + '…' : name, count }))
      setSourceData(sortedSources)

      // Jobs per day (last 30 days)
      const now = Date.now()
      const thirtyDaysAgo = now - 30 * 24 * 3600 * 1000
      const dayMap = {}
      matchData
        .filter(m => new Date(m.created_at).getTime() > thirtyDaysAgo)
        .forEach(m => {
          const day = new Date(m.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
          dayMap[day] = (dayMap[day] || 0) + 1
        })
      // Fill in all 30 days
      const days = []
      for (let i = 29; i >= 0; i--) {
        const d = new Date(now - i * 24 * 3600 * 1000)
        const label = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
        days.push({ date: label, count: dayMap[label] || 0 })
      }
      setTimeData(days)

      // Score distribution in 10-point buckets
      const buckets = Array.from({ length: 10 }, (_, i) => ({
        range: `${i * 10}-${i * 10 + 9}`,
        count: 0,
      }))
      matchData.forEach(m => {
        const bucket = Math.min(9, Math.floor(m.match_score / 10))
        buckets[bucket].count++
      })
      setScoreData(buckets.reverse())

    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const responseRate = stats.applied
    ? `${Math.round((stats.applied / Math.max(stats.seen, 1)) * 100)}%`
    : '—'

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="spinner w-8 h-8" />
      </div>
    )
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">Analytics</h1>
        <p className="text-sm text-gray-400 mt-0.5">Your job search activity at a glance</p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Jobs Seen" value={stats.seen} color="brand" />
        <StatCard label="Saved" value={stats.saved} color="yellow" />
        <StatCard label="Applied" value={stats.applied} color="green" />
        <StatCard label="Response Rate" value={responseRate} sub="applied / seen" color="purple" />
      </div>

      {/* Jobs per day chart */}
      <div className="card">
        <h2 className="section-title mb-4">Jobs Found — Last 30 Days</h2>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={timeData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6470f3" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#6470f3" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: '#6b7280' }}
              tickLine={false}
              interval={6}
            />
            <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="count"
              stroke="#6470f3"
              fill="url(#areaGrad)"
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Top sources */}
        <div className="card">
          <h2 className="section-title mb-4">Top Sources</h2>
          {sourceData.length === 0 ? (
            <p className="text-sm text-gray-500">No data yet</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={sourceData}
                layout="vertical"
                margin={{ top: 0, right: 10, left: 0, bottom: 0 }}
              >
                <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={90}
                  tick={{ fontSize: 10, fill: '#9ca3af' }}
                  tickLine={false}
                />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {sourceData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Score distribution */}
        <div className="card">
          <h2 className="section-title mb-4">Score Distribution</h2>
          {scoreData.every(b => b.count === 0) ? (
            <p className="text-sm text-gray-500">No data yet</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={scoreData}
                layout="vertical"
                margin={{ top: 0, right: 10, left: 0, bottom: 0 }}
              >
                <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} />
                <YAxis
                  type="category"
                  dataKey="range"
                  width={55}
                  tick={{ fontSize: 10, fill: '#9ca3af' }}
                  tickLine={false}
                />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {scoreData.map((entry, i) => {
                    const score = parseInt(entry.range)
                    const color =
                      score >= 90 ? '#10b981'
                      : score >= 70 ? '#84cc16'
                      : score >= 50 ? '#f59e0b'
                      : '#6b7280'
                    return <Cell key={i} fill={color} />
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  )
}
