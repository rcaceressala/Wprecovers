'use client'

import { scoreColor, scoreLabel } from '@/lib/api'

interface RecoveryGaugeProps {
  score: number
  size?: 'sm' | 'lg'
}

export function RecoveryGauge({ score, size = 'lg' }: RecoveryGaugeProps) {
  const clamped = Math.min(100, Math.max(0, Math.round(score)))
  const color   = scoreColor(clamped)
  const label   = scoreLabel(clamped)

  if (size === 'sm') {
    const r    = 32
    const cx   = 50
    const cy   = 46
    const circ = Math.PI * r
    const prog = (clamped / 100) * circ
    const path = `M ${cx - r},${cy} A ${r},${r} 0 0,1 ${cx + r},${cy}`

    return (
      <div className="flex flex-col items-center gap-0.5">
        <svg viewBox="0 0 100 58" className="w-20">
          <path d={path} fill="none" stroke="#1e1e2e" strokeWidth="7" strokeLinecap="round" />
          <path
            d={path} fill="none" stroke={color} strokeWidth="7" strokeLinecap="round"
            strokeDasharray={`${prog} ${circ - prog}`}
            style={{ transition: 'stroke-dasharray 0.5s ease' }}
          />
          <text x={cx} y={cy - 5} textAnchor="middle" fill={color} fontSize="14"
                fontWeight="bold" fontFamily="monospace">{clamped}</text>
        </svg>
        <span className="text-[10px] font-mono" style={{ color }}>{label}</span>
      </div>
    )
  }

  // ---- Large gauge ----
  const r    = 80
  const cx   = 100
  const cy   = 105
  const circ = Math.PI * r
  const prog = (clamped / 100) * circ
  const path = `M ${cx - r},${cy} A ${r},${r} 0 0,1 ${cx + r},${cy}`

  // Threshold tick marks at 60 and 75
  const ticks = [
    { t: 60, col: '#ff4d4d' },
    { t: 75, col: '#f5a623' },
  ].map(({ t, col }) => {
    const angle = ((180 - (t / 100) * 180) * Math.PI) / 180
    const x1 = cx + (r - 8) * Math.cos(angle)
    const y1 = cy - (r - 8) * Math.sin(angle)
    const x2 = cx + (r + 8) * Math.cos(angle)
    const y2 = cy - (r + 8) * Math.sin(angle)
    return { x1, y1, x2, y2, col }
  })

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 200 128" className="w-64">
        {/* Track */}
        <path d={path} fill="none" stroke="#1a1a24" strokeWidth="14" strokeLinecap="round" />

        {/* Glow layer */}
        <path
          d={path} fill="none" stroke={color} strokeWidth="22" strokeLinecap="round"
          strokeDasharray={`${prog} ${circ - prog}`}
          style={{ filter: 'blur(9px)', opacity: 0.25, transition: 'stroke-dasharray 0.6s ease' }}
        />

        {/* Fill */}
        <path
          d={path} fill="none" stroke={color} strokeWidth="14" strokeLinecap="round"
          strokeDasharray={`${prog} ${circ - prog}`}
          style={{ transition: 'stroke-dasharray 0.6s ease, stroke 0.3s ease' }}
        />

        {/* Threshold ticks */}
        {ticks.map((tk, i) => (
          <line key={i} x1={tk.x1} y1={tk.y1} x2={tk.x2} y2={tk.y2}
                stroke={tk.col} strokeWidth="2.5" strokeLinecap="round" opacity={0.6} />
        ))}

        {/* Score number */}
        <text x={cx} y={cy - 20} textAnchor="middle" fill={color}
              fontSize="38" fontWeight="bold" fontFamily="monospace">
          {clamped}
        </text>

        {/* Labels */}
        <text x={cx} y={cy - 4} textAnchor="middle" fill="#6b7280" fontSize="10"
              fontFamily="sans-serif" letterSpacing="1">
          RECOVERY SCORE
        </text>
        <text x={cx} y={cy + 13} textAnchor="middle" fill={color} fontSize="12"
              fontFamily="sans-serif" fontWeight="500">
          {label}
        </text>

        {/* Axis labels */}
        <text x={cx - r + 4} y={cy + 20} textAnchor="middle" fill="#6b7280" fontSize="9" fontFamily="monospace">0</text>
        <text x={cx + r - 4} y={cy + 20} textAnchor="middle" fill="#6b7280" fontSize="9" fontFamily="monospace">100</text>
      </svg>
    </div>
  )
}
