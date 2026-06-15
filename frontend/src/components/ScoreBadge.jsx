/**
 * frontend/src/components/ScoreBadge.jsx
 * Colour-coded score badge based on match score range.
 */

export default function ScoreBadge({ score, size = 'md' }) {
  const cls = score >= 90
    ? 'score-90'
    : score >= 75
    ? 'score-75'
    : score >= 60
    ? 'score-60'
    : 'score-low'

  const emoji = score >= 90 ? '🔥' : score >= 75 ? '🎯' : score >= 60 ? '✅' : '📋'
  const sizeCls = size === 'lg' ? 'text-sm px-3 py-1' : 'text-xs px-2 py-0.5'

  return (
    <span className={`${cls} ${sizeCls} font-mono font-semibold`}>
      {emoji} {score}
    </span>
  )
}
