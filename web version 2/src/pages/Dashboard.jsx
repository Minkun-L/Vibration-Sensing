import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ReferenceArea,
} from 'recharts'
import { mockHistory, latestMeasurement, getThicknessStatus } from '../lib/mockData.js'
import { AlertTriangle, CheckCircle2, ShieldAlert, Info } from 'lucide-react'

// ── Thickness banner ──────────────────────────────────────────────────────────
function ThicknessBanner() {
  const pct = latestMeasurement.linerThicknessPct
  const status = getThicknessStatus(pct)

  const cfg = {
    healthy:  { border: '#22c55e', bg: 'rgba(34,197,94,0.08)',   text: '#4ade80', msg: 'Liner condition is good.',                                  icon: <CheckCircle2 size={22} style={{ color: '#4ade80', flexShrink: 0 }} /> },
    warning:  { border: '#f59e0b', bg: 'rgba(245,158,11,0.08)',  text: '#fbbf24', msg: 'Liner wear is significant. Plan maintenance soon.',          icon: <AlertTriangle size={22} style={{ color: '#fbbf24', flexShrink: 0 }} /> },
    critical: { border: '#ef4444', bg: 'rgba(239,68,68,0.08)',   text: '#f87171', msg: 'Critical wear detected. Immediate inspection required.',     icon: <ShieldAlert size={22} style={{ color: '#f87171', flexShrink: 0 }} /> },
  }[status]

  return (
    <div style={{
      borderRadius: 'var(--radius)',
      padding: '16px 20px',
      marginBottom: 28,
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      background: cfg.bg,
      border: `1px solid ${cfg.border}30`,
      borderLeft: `4px solid ${cfg.border}`,
    }}>
      {cfg.icon}
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: '0.7rem', color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600, marginBottom: 2 }}>
          Latest Prediction · {latestMeasurement.date}
        </p>
        <p style={{ fontSize: '1.125rem', fontWeight: 700, color: cfg.text, fontFamily: 'var(--font-mono)' }}>
          Estimated liner thickness remaining:{' '}
          <span style={{ fontSize: '1.5rem' }}>{pct}%</span>{' '}
          <span style={{ fontSize: '1rem', fontWeight: 400 }}>of initial</span>
        </p>
        <p style={{ fontSize: '0.875rem', color: cfg.text, opacity: 0.8, marginTop: 2 }}>{cfg.msg}</p>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
        <span style={{ fontSize: '0.7rem', color: 'var(--muted-foreground)' }}>Wear progress</span>
        <div style={{ width: 128, height: 10, borderRadius: 9999, background: 'var(--border)', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${100 - pct}%`, background: cfg.border, borderRadius: 9999, transition: 'width 0.7s' }} />
        </div>
        <span style={{ fontSize: '0.7rem', color: cfg.text }}>{100 - pct}% worn</span>
      </div>
    </div>
  )
}

// ── Custom tooltip ────────────────────────────────────────────────────────────
function ThicknessTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const val = payload[0]?.value
  const color = val > 60 ? '#4ade80' : val > 40 ? '#fbbf24' : '#f87171'
  return (
    <div style={{
      borderRadius: 'var(--radius)', border: '1px solid var(--border)',
      background: 'var(--card)', padding: '8px 12px', fontSize: '0.7rem',
      fontFamily: 'var(--font-mono)', minWidth: 140, boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
    }}>
      <p style={{ color: 'var(--muted-foreground)', fontWeight: 500, marginBottom: 6, borderBottom: '1px solid var(--border)', paddingBottom: 6 }}>{label}</p>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
        <span style={{ color: 'var(--muted-foreground)' }}>Liner thickness</span>
        <span style={{ fontWeight: 700, color }}>{val}%</span>
      </div>
    </div>
  )
}

// ── Coloured dots ─────────────────────────────────────────────────────────────
function ThicknessDot({ cx, cy, payload }) {
  const v = payload.linerThicknessPct
  const fill = v > 60 ? '#4ade80' : v > 40 ? '#fbbf24' : '#f87171'
  return <circle cx={cx} cy={cy} r={5} fill={fill} stroke="var(--card)" strokeWidth={2} />
}

// ── Thickness chart ───────────────────────────────────────────────────────────
function ThicknessChart() {
  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 4 }}>
        <div>
          <div className="card-title">Liner Thickness Remaining Over Time</div>
          <div className="card-sub">Each dot is colour-coded by wear zone. Dashed line = replacement threshold (40%).</div>
        </div>
        <span className="badge">{mockHistory.length} measurements</span>
      </div>

      <div className="info-box">
        <Info size={12} style={{ color: 'var(--muted-foreground)', flexShrink: 0, marginTop: 1 }} />
        Green zone (&gt;60%) indicates a healthy liner. Yellow zone (40–60%) means wear is significant and maintenance should be planned. Red zone (&lt;40%) requires immediate inspection.
      </div>

      <div style={{ height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={mockHistory} margin={{ top: 8, right: 16, left: -10, bottom: 0 }}>
            <ReferenceArea y1={0}  y2={40}  fill="#ef4444" fillOpacity={0.08} />
            <ReferenceArea y1={40} y2={60}  fill="#f59e0b" fillOpacity={0.08} />
            <ReferenceArea y1={60} y2={100} fill="#22c55e" fillOpacity={0.07} />
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.15)" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'rgba(148,163,184,0.8)', fontFamily: 'var(--font-mono)' }} axisLine={{ stroke: 'rgba(128,128,128,0.2)' }} tickLine={false} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: 'rgba(148,163,184,0.8)', fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} unit="%" width={42} />
            <Tooltip content={<ThicknessTooltip />} />
            <ReferenceLine y={40} stroke="rgba(239,68,68,0.5)" strokeDasharray="5 4" label={{ value: 'Replace soon  40%', fill: 'rgba(239,68,68,0.7)', fontSize: 10, position: 'insideTopLeft' }} />
            <ReferenceLine y={60} stroke="rgba(245,158,11,0.4)" strokeDasharray="5 4" label={{ value: 'Warning  60%', fill: 'rgba(245,158,11,0.6)', fontSize: 10, position: 'insideTopLeft' }} />
            <Line type="monotone" dataKey="linerThicknessPct" stroke="#94a3b8" strokeWidth={2.5} dot={<ThicknessDot />} activeDot={{ r: 7, stroke: 'var(--card)', strokeWidth: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-legend">
        {[{ color: '#4ade80', label: '≥ 60%  Healthy' }, { color: '#fbbf24', label: '40–60%  Warning' }, { color: '#f87171', label: '< 40%  Critical' }].map(({ color, label }) => (
          <div key={label} className="legend-label">
            <span className="legend-dot" style={{ background: color }} />
            {label}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Dashboard() {
  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--foreground)', letterSpacing: '-0.01em' }}>Measurement Dashboard</h2>
        <p style={{ fontSize: '0.875rem', color: 'var(--muted-foreground)', marginTop: 4 }}>
          Liner wear overview. See <span style={{ color: 'var(--primary)', fontWeight: 500 }}>Details</span> for feature breakdown and full history.
        </p>
      </div>
      <ThicknessBanner />
      <ThicknessChart />
    </div>
  )
}
