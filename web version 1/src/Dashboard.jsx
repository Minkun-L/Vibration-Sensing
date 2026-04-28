import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
} from 'recharts'
import { mockHistory, latestMeasurement } from './mockData'

// ── Threshold below which we show a "replace soon" warning ──
const WARN_THRESHOLD = 40

const styles = {
  page: { maxWidth: 820, margin: '0 auto', padding: '32px 24px' },
  heading: { fontSize: 22, fontWeight: 700, marginBottom: 24 },

  // Prediction banner
  bannerGreen: {
    padding: '18px 24px',
    borderRadius: 8,
    background: '#dcfce7',
    border: '1px solid #86efac',
    marginBottom: 28,
  },
  bannerYellow: {
    padding: '18px 24px',
    borderRadius: 8,
    background: '#fef9c3',
    border: '1px solid #fde047',
    marginBottom: 28,
  },
  bannerRed: {
    padding: '18px 24px',
    borderRadius: 8,
    background: '#fee2e2',
    border: '1px solid #fca5a5',
    marginBottom: 28,
  },
  bannerLabel: { fontSize: 13, fontWeight: 600, color: '#555', marginBottom: 4 },
  bannerValue: { fontSize: 32, fontWeight: 800, color: '#111' },
  bannerSub: { fontSize: 13, color: '#666', marginTop: 4 },

  sectionTitle: {
    fontSize: 16,
    fontWeight: 700,
    marginBottom: 14,
    borderBottom: '1px solid #e5e7eb',
    paddingBottom: 6,
  },

  // Feature list
  featureGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
    gap: 12,
    marginBottom: 36,
  },
  featureCard: {
    padding: '14px 16px',
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: 8,
  },
  featureLabel: { fontSize: 12, color: '#64748b', marginBottom: 4 },
  featureValue: { fontSize: 22, fontWeight: 700, color: '#0f172a' },
  featureUnit: { fontSize: 12, color: '#94a3b8', marginLeft: 4 },

  // History table
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13, marginBottom: 36 },
  th: {
    textAlign: 'left',
    padding: '8px 12px',
    background: '#f1f5f9',
    fontWeight: 600,
    color: '#475569',
    borderBottom: '1px solid #e2e8f0',
  },
  td: { padding: '8px 12px', borderBottom: '1px solid #f1f5f9', color: '#334155' },
  tdNum: { padding: '8px 12px', borderBottom: '1px solid #f1f5f9', color: '#334155', textAlign: 'right' },

  chartWrap: { marginBottom: 36 },
}

function BannerColor(pct) {
  if (pct > 60) return styles.bannerGreen
  if (pct > WARN_THRESHOLD) return styles.bannerYellow
  return styles.bannerRed
}

function BannerEmoji(pct) {
  if (pct > 60) return '🟢'
  if (pct > WARN_THRESHOLD) return '🟡'
  return '🔴'
}

// FeatureCard supports an array of { value, unit, sub } rows for multi-value features
function FeatureCard({ label, rows }) {
  return (
    <div style={styles.featureCard}>
      <div style={styles.featureLabel}>{label}</div>
      {rows.map((r, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 2, marginTop: i > 0 ? 6 : 0 }}>
          <span style={styles.featureValue}>{r.value}</span>
          <span style={styles.featureUnit}>{r.unit}</span>
          {r.sub && <span style={{ fontSize: 11, color: '#94a3b8', marginLeft: 4 }}>{r.sub}</span>}
        </div>
      ))}
    </div>
  )
}

// Custom tooltip for the freq chart
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: '#fff', border: '1px solid #ccc', padding: '8px 12px', borderRadius: 6, fontSize: 13 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      <div>Resonance Freq 1: <b>{payload[0].value} Hz</b></div>
    </div>
  )
}

// Custom tooltip for the thickness chart
function ThicknessTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const val = payload[0].value
  const color = val > 60 ? '#16a34a' : val > 40 ? '#ca8a04' : '#dc2626'
  return (
    <div style={{ background: '#fff', border: '1px solid #ccc', padding: '8px 12px', borderRadius: 6, fontSize: 13 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      <div>Liner thickness: <b style={{ color }}>{val}%</b></div>
    </div>
  )
}

// Color each dot on the thickness line by wear severity
function ThicknessDot(props) {
  const { cx, cy, payload } = props
  const v = payload.thickness
  const fill = v > 60 ? '#16a34a' : v > 40 ? '#f59e0b' : '#ef4444'
  return <circle cx={cx} cy={cy} r={5} fill={fill} stroke='#fff' strokeWidth={1.5} />
}

export default function Dashboard() {
  const latest = latestMeasurement

  // Chart data: use short date labels
  const chartData = mockHistory.map((m) => ({
    date: m.timestamp.slice(5, 10), // "MM-DD"
    freq1: m.resonanceFreq1,
    thickness: m.thicknessPercent,
  }))

  const pct = latest.thicknessPercent

  return (
    <div style={styles.page}>
      <div style={styles.heading}>Measurement Dashboard</div>

      {/* ── Prediction Banner ── */}
      <div style={BannerColor(pct)}>
        <div style={styles.bannerLabel}>
          {BannerEmoji(pct)}  Estimated Liner Thickness Remaining
        </div>
        <div style={styles.bannerValue}>{pct}% of initial</div>
        <div style={styles.bannerSub}>
          Last measured: {latest.timestamp}
          {pct <= WARN_THRESHOLD
            ? '  — ⚠️ Liner wear is critical. Plan replacement soon.'
            : '  — Liner condition is acceptable.'}
        </div>
      </div>

      {/* ── Latest Key Features ── */}
      <div style={styles.sectionTitle}>Latest Measurement Features</div>
      <div style={styles.featureGrid}>
        <FeatureCard
          label="Primary Resonance Frequency"
          rows={[{ value: latest.resonanceFreq1, unit: 'Hz' }]}
        />
        <FeatureCard
          label="Modal Frequency Ratio (f₂ / f₁)"
          rows={[
            { value: latest.modalFreqRatio.toFixed(2) },
            { value: latest.resonanceFreq2, unit: 'Hz', sub: 'f₂' },
          ]}
        />
        <FeatureCard
          label="Decay Time · Damping Ratio · Q Factor"
          rows={[
            { value: latest.decayTime,     unit: 's',  sub: 'decay' },
            { value: latest.dampingRatio,  unit: 'ζ',  sub: 'damping' },
            { value: latest.qFactor,                   sub: 'Q factor' },
          ]}
        />
        <FeatureCard
          label="Spectral Centroid · Energy"
          rows={[
            { value: latest.spectralCentroid, unit: 'Hz', sub: 'centroid' },
            { value: latest.spectralEnergy,   unit: 'g²', sub: 'energy' },
          ]}
        />
        <FeatureCard
          label="RMS of Acceleration"
          rows={[{ value: latest.meanRMS, unit: 'g' }]}
        />
      </div>

      {/* ── Resonance Freq 1 Trend Chart ── */}
      <div style={styles.sectionTitle}>Resonance Frequency 1 vs Time</div>
      <div style={styles.chartWrap}>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={chartData} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="date" tick={{ fontSize: 12 }} />
            <YAxis
              domain={['auto', 'auto']}
              tickFormatter={(v) => `${v} Hz`}
              tick={{ fontSize: 12 }}
              width={72}
            />
            <Tooltip content={<ChartTooltip />} />
            <Line
              type="monotone"
              dataKey="freq1"
              stroke="#2563eb"
              strokeWidth={2}
              dot={{ r: 4, fill: '#2563eb' }}
              activeDot={{ r: 6 }}
            />
            {/* Guideline: new liner baseline */}
            <ReferenceLine y={312} stroke="#86efac" strokeDasharray="4 4" label={{ value: 'New liner', fontSize: 11, fill: '#16a34a' }} />
          </LineChart>
        </ResponsiveContainer>
        <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>
          Declining frequency indicates increased liner wear. Green dashed line = new liner baseline (312 Hz).
        </div>
      </div>

      {/* ── Liner Thickness Trend Chart ── */}
      <div style={styles.sectionTitle}>Liner Thickness Remaining Over Time</div>
      <div style={styles.chartWrap}>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={chartData} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
            {/* Red zone: critical wear */}
            <ReferenceArea y1={0} y2={WARN_THRESHOLD} fill="#fee2e2" fillOpacity={0.5} />
            {/* Yellow zone: caution */}
            <ReferenceArea y1={WARN_THRESHOLD} y2={60} fill="#fef9c3" fillOpacity={0.5} />
            {/* Green zone: healthy */}
            <ReferenceArea y1={60} y2={100} fill="#dcfce7" fillOpacity={0.4} />
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="date" tick={{ fontSize: 12 }} />
            <YAxis
              domain={[0, 100]}
              tickFormatter={(v) => `${v}%`}
              tick={{ fontSize: 12 }}
              width={48}
            />
            <Tooltip content={<ThicknessTooltip />} />
            <ReferenceLine y={WARN_THRESHOLD} stroke="#ef4444" strokeDasharray="4 4"
              label={{ value: 'Replace soon', fontSize: 11, fill: '#dc2626', position: 'insideTopLeft' }} />
            <Line
              type="monotone"
              dataKey="thickness"
              stroke="#64748b"
              strokeWidth={2}
              dot={<ThicknessDot />}
              activeDot={{ r: 7 }}
            />
          </LineChart>
        </ResponsiveContainer>
        <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>
          Green = healthy (&gt;60%) · Yellow = caution (40–60%) · Red = replace soon (&lt;40%). Each dot is color-coded.
        </div>
      </div>

      {/* ── Historical Table ── */}
      <div style={styles.sectionTitle}>Measurement History</div>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Date</th>
            <th style={{ ...styles.th, textAlign: 'right' }}>Freq 1 (Hz)</th>
            <th style={{ ...styles.th, textAlign: 'right' }}>Freq 2 (Hz)</th>
            <th style={{ ...styles.th, textAlign: 'right' }}>RMS (g)</th>
            <th style={{ ...styles.th, textAlign: 'right' }}>Decay (s)</th>
            <th style={{ ...styles.th, textAlign: 'right' }}>Peak (g)</th>
            <th style={{ ...styles.th, textAlign: 'right' }}>Thickness %</th>
          </tr>
        </thead>
        <tbody>
          {[...mockHistory].reverse().map((m) => (
            <tr key={m.id}>
              <td style={styles.td}>{m.timestamp}</td>
              <td style={styles.tdNum}>{m.resonanceFreq1}</td>
              <td style={styles.tdNum}>{m.resonanceFreq2}</td>
              <td style={styles.tdNum}>{m.meanRMS}</td>
              <td style={styles.tdNum}>{m.decayTime}</td>
              <td style={styles.tdNum}>{m.peakAmplitude}</td>
              <td style={{ ...styles.tdNum, fontWeight: m.thicknessPercent <= WARN_THRESHOLD ? 700 : 400, color: m.thicknessPercent <= WARN_THRESHOLD ? '#dc2626' : styles.tdNum.color }}>
                {m.thicknessPercent}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
