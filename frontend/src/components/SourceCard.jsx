/**
 * frontend/src/components/SourceCard.jsx
 * Single job source card with health badge + toggle.
 */

import HealthBadge from './HealthBadge'
import { sourcesApi } from '../lib/api'
import { useState } from 'react'

const TYPE_BADGE = {
  api:          { label: 'API',     cls: 'badge-green' },
  rss:          { label: 'RSS',     cls: 'badge-blue' },
  jina:         { label: 'Scrape',  cls: 'badge-yellow' },
  company_page: { label: 'Company', cls: 'badge-purple' },
}

export default function SourceCard({ source, onToggle }) {
  const [active, setActive] = useState(source.is_active)
  const [loading, setLoading] = useState(false)
  const typeBadge = TYPE_BADGE[source.source_type] || TYPE_BADGE.jina

  async function handleToggle() {
    setLoading(true)
    try {
      await sourcesApi.toggle(source.id, !active)
      setActive(!active)
      onToggle?.(source.id, !active)
    } catch (e) {
      console.error('Toggle failed:', e)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={`card transition-all duration-200 ${!active ? 'opacity-50' : ''}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-sm font-semibold text-gray-100 truncate">{source.name}</span>
            <span className={typeBadge.cls}>{typeBadge.label}</span>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500 flex-wrap">
            <HealthBadge status={source.health_status} />
            {source.category && (
              <span className="badge badge-gray">{source.category}</span>
            )}
            {source.last_job_count != null && (
              <span>{source.last_job_count} jobs last run</span>
            )}
            {source.last_fetched && (
              <span>
                Last: {new Date(source.last_fetched).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>

        {/* Toggle switch */}
        <button
          onClick={handleToggle}
          disabled={loading}
          className={`toggle-track ${active ? 'toggle-track-on' : ''} shrink-0`}
          title={active ? 'Disable source' : 'Enable source'}
          aria-label={`${active ? 'Disable' : 'Enable'} ${source.name}`}
        >
          <span className={`toggle-thumb ${active ? 'toggle-thumb-on' : ''}`} />
        </button>
      </div>
    </div>
  )
}
