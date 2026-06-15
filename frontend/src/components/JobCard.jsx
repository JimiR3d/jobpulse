/**
 * frontend/src/components/JobCard.jsx
 * 
 * Job listing card with expandable detail panel.
 * Shows: title, company, score, remote type, seniority, currency, source health.
 * Expandable: full description, match reasons, disqualifiers, apply button.
 */

import { useState } from 'react'
import { ChevronDown, ChevronUp, ExternalLink, Star, Check, X, AlertTriangle } from 'lucide-react'
import ScoreBadge from './ScoreBadge'
import HealthBadge from './HealthBadge'
import { jobsApi } from '../lib/api'

const CURRENCY_EMOJI = { usd: '💵', gbp: '💷', eur: '💶' }
const SENIORITY_BADGE = {
  internship: { label: '🎓 Internship', cls: 'badge-purple' },
  entry:      { label: '🟢 Entry',      cls: 'badge-green' },
  junior:     { label: '🔵 Junior',     cls: 'badge-blue' },
  mid:        { label: 'Mid-level',     cls: 'badge-gray' },
  senior:     { label: 'Senior',        cls: 'badge-yellow' },
  lead:       { label: 'Lead',          cls: 'badge-orange' },
}

function timeAgo(dateStr) {
  if (!dateStr) return 'Recently'
  const diff = Date.now() - new Date(dateStr).getTime()
  const h = Math.floor(diff / 3600000)
  const d = Math.floor(h / 24)
  if (d > 30) return `${Math.floor(d / 30)}mo ago`
  if (d > 0) return `${d}d ago`
  if (h > 0) return `${h}h ago`
  return 'Just now'
}

export default function JobCard({ match, onStatusChange }) {
  const [expanded, setExpanded] = useState(false)
  const [status, setStatus] = useState(match.status)
  const [loading, setLoading] = useState(null)

  const job = match.jobs || {}
  const source = job.job_sources || {}
  const seniority = SENIORITY_BADGE[job.seniority]
  const currencyEmoji = CURRENCY_EMOJI[match.currency_signal] || '❓'
  const isTrainee = job.is_trainee

  async function updateStatus(newStatus) {
    setLoading(newStatus)
    try {
      await jobsApi.updateStatus(match.id, newStatus)
      setStatus(newStatus)
      onStatusChange?.(match.id, newStatus)
    } catch (e) {
      console.error('Status update failed:', e)
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className={`card-hover border-l-2 animate-in ${
      match.match_score >= 90
        ? 'border-l-emerald-500'
        : match.match_score >= 75
        ? 'border-l-lime-500'
        : match.match_score >= 60
        ? 'border-l-amber-500'
        : 'border-l-gray-700'
    }`}>
      {/* Header row */}
      <div
        className="flex items-start justify-between gap-4"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex-1 min-w-0">
          {/* Title + score */}
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <ScoreBadge score={match.match_score} />
            <h3 className="text-base font-semibold text-gray-100 truncate">
              {job.title || 'Untitled Role'}
            </h3>
          </div>

          {/* Company + meta */}
          <div className="flex items-center gap-2 flex-wrap text-sm text-gray-400">
            <span className="text-gray-300 font-medium">{job.company || 'Unknown Co.'}</span>
            <span className="text-gray-600">·</span>
            <span>🌍 Worldwide</span>
            <span className="text-gray-600">·</span>
            <span>{currencyEmoji}</span>
            <span className="text-gray-600">·</span>
            <span>{timeAgo(job.posted_at || match.created_at)}</span>
          </div>

          {/* Badges row */}
          <div className="flex items-center gap-2 flex-wrap mt-2">
            {isTrainee && (
              <span className="badge badge-purple">📚 Trainee</span>
            )}
            {seniority && !isTrainee && (
              <span className={seniority.cls}>{seniority.label}</span>
            )}
            {!match.remote_verified && (
              <span className="badge badge-orange">
                <AlertTriangle size={10} /> Unverified Remote
              </span>
            )}
            {source.name && (
              <span className="inline-flex items-center gap-1 badge badge-gray">
                <HealthBadge status={source.health_status} showLabel={false} />
                {source.name}
              </span>
            )}
          </div>
        </div>

        {/* Expand toggle */}
        <button className="text-gray-500 hover:text-gray-300 mt-1 shrink-0">
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      {/* Expanded detail panel */}
      {expanded && (
        <div className="mt-4 pt-4 border-t border-gray-800 space-y-4 slide-in">
          {/* Match reasons */}
          {match.match_reasons?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                Why it matches
              </p>
              <ul className="space-y-1">
                {match.match_reasons.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-emerald-300">
                    <Check size={14} className="mt-0.5 shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Disqualifiers */}
          {match.disqualifiers?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                Watch out for
              </p>
              <ul className="space-y-1">
                {match.disqualifiers.map((d, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-orange-300">
                    <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                    {d}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Description snippet */}
          {job.description && (
            <div>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                Description
              </p>
              <p className="text-sm text-gray-300 leading-relaxed line-clamp-6">
                {job.description}
              </p>
            </div>
          )}

          {/* Tags */}
          {job.tags?.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {job.tags.slice(0, 8).map((tag, i) => (
                <span key={i} className="badge badge-gray text-xs">{tag}</span>
              ))}
            </div>
          )}

          {/* Salary */}
          {job.salary_range && (
            <p className="text-sm text-gray-400">
              💰 {job.salary_range}
            </p>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-2 flex-wrap pt-2">
            <a
              href={job.apply_url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-primary"
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink size={14} />
              Apply Now
            </a>

            {status !== 'saved' && (
              <button
                className="btn btn-secondary"
                onClick={(e) => { e.stopPropagation(); updateStatus('saved') }}
                disabled={!!loading}
              >
                <Star size={14} className={status === 'saved' ? 'fill-yellow-400 text-yellow-400' : ''} />
                {loading === 'saved' ? 'Saving…' : 'Save'}
              </button>
            )}

            {status !== 'applied' && (
              <button
                className="btn btn-secondary"
                onClick={(e) => { e.stopPropagation(); updateStatus('applied') }}
                disabled={!!loading}
              >
                <Check size={14} />
                {loading === 'applied' ? 'Marking…' : 'Applied'}
              </button>
            )}

            {status !== 'rejected' && (
              <button
                className="btn btn-ghost text-gray-500"
                onClick={(e) => { e.stopPropagation(); updateStatus('rejected') }}
                disabled={!!loading}
              >
                <X size={14} />
                Not interested
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
