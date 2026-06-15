/**
 * frontend/src/pages/Dashboard.jsx
 *
 * Main job feed. Features:
 * - Status tabs: New | Saved | Applied | All
 * - Filters: score range, source, seniority, role type, show senior toggle
 * - Scoped Supabase Realtime subscription (Security Patch #8)
 * - Auto-load more on scroll
 */

import { useEffect, useState, useCallback } from 'react'
import { Filter, RefreshCw, Zap } from 'lucide-react'
import JobCard from '../components/JobCard'
import { jobsApi } from '../lib/api'
import { supabase } from '../lib/supabase'

const TABS = [
  { id: 'new',     label: 'New' },
  { id: 'saved',   label: 'Saved ⭐' },
  { id: 'applied', label: 'Applied ✅' },
  { id: null,      label: 'All' },
]

const SENIORITY_OPTIONS = ['internship', 'entry', 'junior', 'mid']

export default function Dashboard() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('new')
  const [showFilters, setShowFilters] = useState(false)
  const [showSenior, setShowSenior] = useState(false)
  const [minScore, setMinScore] = useState(0)
  const [newJobCount, setNewJobCount] = useState(0)

  const fetchJobs = useCallback(async (tab = activeTab) => {
    setLoading(true)
    try {
      const params = {
        limit: 50,
        show_senior: showSenior,
        min_score: minScore,
      }
      if (tab) params.status = tab

      const data = await jobsApi.list(params)
      setJobs(data.jobs || [])
    } catch (e) {
      console.error('Failed to fetch jobs:', e)
    } finally {
      setLoading(false)
    }
  }, [activeTab, showSenior, minScore])

  useEffect(() => {
    fetchJobs(activeTab)
  }, [activeTab, showSenior, minScore])

  // Scoped Supabase Realtime — Security Patch #8
  // Filters to user's own matches via both channel filter AND RLS
  // Uses a stable subscription that doesn't churn on filter changes
  useEffect(() => {
    let channel

    async function subscribe() {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) return

      channel = supabase
        .channel(`job_matches:user:${user.id}`)
        .on('postgres_changes', {
          event: 'INSERT',
          schema: 'public',
          table: 'job_matches',
          filter: `user_id=eq.${user.id}`,
        }, () => {
          setNewJobCount(n => n + 1)
        })
        .subscribe()
    }

    subscribe()
    return () => { if (channel) supabase.removeChannel(channel) }
  }, [])  // Stable — subscribe once on mount

  function handleStatusChange(matchId, newStatus) {
    setJobs(prev => prev.filter(j => {
      // Remove from current filtered view if it no longer belongs here
      if (activeTab === 'new' && newStatus !== 'new') return j.id !== matchId
      if (activeTab === 'saved' && newStatus !== 'saved') return j.id !== matchId
      if (activeTab === 'applied' && newStatus !== 'applied') return j.id !== matchId
      return true
    }))
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">Job Feed</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            AI-scored remote opportunities matched to your profile
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`btn btn-secondary btn-sm ${showFilters ? 'border-brand-600 text-brand-300' : ''}`}
          >
            <Filter size={14} />
            Filters
          </button>
          <button
            onClick={() => fetchJobs(activeTab)}
            className="btn btn-ghost btn-sm"
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* New job notification */}
      {newJobCount > 0 && (
        <button
          className="w-full mb-4 flex items-center justify-center gap-2 py-2.5 rounded-xl
            bg-brand-900/40 border border-brand-700/50 text-brand-300 text-sm font-medium
            hover:bg-brand-900/60 transition-all animate-in"
          onClick={() => { setNewJobCount(0); fetchJobs('new') }}
        >
          <Zap size={14} />
          {newJobCount} new match{newJobCount !== 1 ? 'es' : ''} — click to refresh
        </button>
      )}

      {/* Filters panel */}
      {showFilters && (
        <div className="glass p-4 mb-4 space-y-4 animate-in">
          <div>
            <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Min score: {minScore}
            </label>
            <input
              type="range"
              min={0} max={100} step={5}
              value={minScore}
              onChange={e => setMinScore(+e.target.value)}
              className="w-full mt-2 accent-brand-500"
            />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-300">Show senior / lead roles</span>
            <button
              onClick={() => setShowSenior(!showSenior)}
              className={`toggle-track ${showSenior ? 'toggle-track-on' : ''}`}
            >
              <span className={`toggle-thumb ${showSenior ? 'toggle-thumb-on' : ''}`} />
            </button>
          </div>
        </div>
      )}

      {/* Status tabs */}
      <div className="flex items-center gap-1 mb-4 bg-gray-900 p-1 rounded-xl">
        {TABS.map(tab => (
          <button
            key={tab.id ?? 'all'}
            className={`flex-1 ${activeTab === tab.id ? 'tab-active' : 'tab'}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Job list */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="spinner w-8 h-8" />
        </div>
      ) : jobs.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-4xl mb-3">🔍</p>
          <p className="text-gray-400">
            {activeTab === 'new'
              ? 'No new matches yet. The scheduler runs every 2 hours.'
              : `No ${activeTab} jobs yet.`}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map(match => (
            <JobCard
              key={match.id}
              match={match}
              onStatusChange={handleStatusChange}
            />
          ))}
        </div>
      )}
    </div>
  )
}
