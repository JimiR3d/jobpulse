/**
 * frontend/src/components/HealthBadge.jsx
 * Source health status badge with animated dot indicator.
 */

const HEALTH_CONFIG = {
  healthy:     { label: 'Healthy',     dotClass: 'health-healthy',     textClass: 'text-emerald-400' },
  degraded:    { label: 'Degraded',    dotClass: 'health-degraded',    textClass: 'text-yellow-400' },
  dead:        { label: 'Dead',        dotClass: 'health-dead',        textClass: 'text-red-400' },
  low_quality: { label: 'Low Quality', dotClass: 'health-low_quality', textClass: 'text-orange-400' },
}

export default function HealthBadge({ status, showLabel = true }) {
  const config = HEALTH_CONFIG[status] || HEALTH_CONFIG.healthy

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={config.dotClass} />
      {showLabel && (
        <span className={`text-xs ${config.textClass}`}>{config.label}</span>
      )}
    </span>
  )
}
