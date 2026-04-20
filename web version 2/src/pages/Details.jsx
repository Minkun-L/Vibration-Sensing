import { useState, useEffect } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { mockHistory, latestMeasurement, getThicknessStatus } from '../lib/mockData.js'
import { fetchFeatures, fetchHistory } from '../lib/api.js'
import { Activity, Waves, Timer, Radio, Zap, Wifi, WifiOff, RefreshCw, X } from 'lucide-react'

// ── Feature row ───────────────────────────────────────────────────────────────
function FeatureItem({ icon, label, sub, value, unit, extra }) {
  return (
    <div className="feature-row">
      <div className="feature-icon">{icon}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="feature-label">{label}</div>
        <div className="feature-sub">{sub}</div>
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <span className="feature-value">{value}</span>
        <span className="feature-unit">{unit}</span>
        {extra && <div className="feature-extra">{extra}</div>}
      </div>
    </div>
  )
}

function KeyFeatures() {
  const d = latestMeasurement
  const [live, setLive] = useState(null)   // { primaryFreq, rmsAcceleration, timestamp }
  const [piStatus, setPiStatus] = useState('loading') // loading | connected | offline
  const [refreshing, setRefreshing] = useState(false)

  async function load() {
    setRefreshing(true)
    try {
      const data = await fetchFeatures()
      setLive(data)
      setPiStatus('connected')
    } catch {
      setPiStatus('offline')
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => { load() }, [])

  const primaryFreq     = live ? live.primaryFreq             : d.primaryFreq
  const rmsAcceleration = live ? live.rmsAcceleration         : d.rmsAcceleration
  const decayTime       = live ? live.decayTime               : d.decayTime
  const dampingRatio    = live ? live.dampingRatio            : d.dampingRatio
  const qFactor         = live ? live.qFactor                 : d.qFactor
  const spectralCentroid = live ? live.spectralCentroid       : d.spectralCentroid
  const dataSource      = live ? `Live · Pi · ${new Date(live.timestamp).toLocaleTimeString()}` : `Mock data · ${d.date}`

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <div className="card-title">Latest Key Features</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {piStatus === 'connected' && <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.65rem', color: '#4ade80', fontWeight: 600 }}><Wifi size={12} /> Pi connected</span>}
          {piStatus === 'offline'   && <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.65rem', color: '#f87171', fontWeight: 600 }}><WifiOff size={12} /> Pi offline — showing mock data</span>}
          <button
            onClick={load}
            disabled={refreshing}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted-foreground)', padding: 2 }}
            title="Refresh from Pi"
          >
            <RefreshCw size={13} style={{ animation: refreshing ? 'spin 1s linear infinite' : 'none' }} />
          </button>
        </div>
      </div>
      <div className="card-sub" style={{ marginBottom: 16 }}>{dataSource}</div>

      <FeatureItem icon={<Activity size={15} />} label="Primary Resonance Frequency" sub="f₁ — fundamental bending mode of the liner" value={primaryFreq} unit="Hz" />
      <FeatureItem icon={<Waves size={15} />} label="Modal Frequency Ratio" sub="f₂ / f₁ — ratio of 2nd to 1st mode; rises as liner thins" value={d.freqRatio.toFixed(2)} unit="" />
      <FeatureItem icon={<Timer size={15} />} label="Decay Time · Damping Ratio · Q Factor" sub="τ (ms) · ζ · Q = f₁ / bandwidth" value={typeof decayTime === 'number' ? decayTime.toFixed(1) : decayTime} unit="ms" extra={`ζ = ${typeof dampingRatio === 'number' ? dampingRatio.toFixed(4) : dampingRatio}  ·  Q = ${typeof qFactor === 'number' ? qFactor.toFixed(1) : qFactor}`} />
      <FeatureItem icon={<Radio size={15} />} label="Spectral Centroid" sub="Centroid (Hz) shifts lower as liner thickness decreases" value={spectralCentroid} unit="Hz" />
      <FeatureItem icon={<Zap size={15} />} label="RMS of Acceleration" sub="Root-mean-square of Z-axis; increases as liner wears" value={rmsAcceleration.toFixed(2)} unit="g" />
    </div>
  )
}

// ── Freq tooltip ──────────────────────────────────────────────────────────────
function FreqTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      borderRadius: 'var(--radius)', border: '1px solid var(--border)',
      background: 'var(--card)', padding: '8px 12px', fontSize: '0.7rem',
      fontFamily: 'var(--font-mono)', boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
    }}>
      <p style={{ color: 'var(--muted-foreground)', marginBottom: 4 }}>{label}</p>
      <p style={{ color: '#60a5fa', fontWeight: 700 }}>{payload[0].value} Hz</p>
    </div>
  )
}

function FreqChart() {
  const initialFreq = mockHistory[0].primaryFreq
  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 4 }}>
        <div>
          <div className="card-title">Primary Resonance Frequency Over Time</div>
          <div className="card-sub">Decreasing f₁ indicates liner wear. Initial: {initialFreq} Hz</div>
        </div>
        <span className="badge">{mockHistory.length} pts</span>
      </div>
      <div style={{ height: 240, marginTop: 16 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={mockHistory} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.15)" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'rgba(148,163,184,0.8)', fontFamily: 'var(--font-mono)' }} axisLine={{ stroke: 'rgba(128,128,128,0.2)' }} tickLine={false} />
            <YAxis domain={['auto', 'auto']} tick={{ fontSize: 11, fill: 'rgba(148,163,184,0.8)', fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} unit=" Hz" />
            <Tooltip content={<FreqTooltip />} />
            <ReferenceLine y={initialFreq} stroke="rgba(128,128,128,0.2)" strokeDasharray="4 4" label={{ value: 'Initial', fill: 'rgba(128,128,128,0.4)', fontSize: 10, position: 'insideTopRight' }} />
            <Line type="monotone" dataKey="primaryFreq" stroke="#60a5fa" strokeWidth={2.5} dot={{ r: 3, fill: '#60a5fa', strokeWidth: 0 }} activeDot={{ r: 5, fill: '#60a5fa', stroke: 'var(--background)', strokeWidth: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// ── History table ─────────────────────────────────────────────────────────────
function HistoryTable() {
  const [liveHistory, setLiveHistory] = useState(null)  // null = not loaded yet
  const [histSrc, setHistSrc] = useState('loading')     // loading | live | mock
  const [selectedRow, setSelectedRow] = useState(null)  // selected history record

  useEffect(() => {
    fetchHistory()
      .then(data => {
        if (Array.isArray(data) && data.length > 0) {
          setLiveHistory([...data].reverse())
          setHistSrc('live')
        } else {
          setHistSrc('mock')
        }
      })
      .catch(() => setHistSrc('mock'))
  }, [])

  const useMock = histSrc === 'mock' || histSrc === 'loading'
  const rows    = useMock ? [...mockHistory].reverse() : liveHistory

  return (
    <div className="card overflow-hidden">
      <div className="card-header">
        <div className="card-title">Measurement History</div>
        <div className="card-sub">
          {histSrc === 'live' && `${liveHistory.length} recorded sessions from Pi · newest first`}
          {histSrc === 'mock' && 'Pi offline — showing mock data · newest first'}
          {histSrc === 'loading' && 'Loading...'}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table>
          <thead>
            {useMock
              ? <tr>{['Date','f₁ (Hz)','f₂/f₁','Decay (ms)','ζ','Q','Centroid (Hz)','RMS (g)','Thickness'].map(h => <th key={h}>{h}</th>)}</tr>
              : <tr>{['Date','f₁ (Hz)','Centroid (Hz)','RMS (g)','Decay (ms)','ζ','Q','Note'].map(h => <th key={h}>{h}</th>)}</tr>
            }
          </thead>
          <tbody>
            {useMock
              ? rows.map((r, i) => {
                  const status = getThicknessStatus(r.linerThicknessPct)
                  const color = status === 'healthy' ? '#4ade80' : status === 'warning' ? '#fbbf24' : '#f87171'
                  return (
                    <tr key={r.id} style={{ opacity: i === 0 ? 1 : 0.85 }}>
                      <td style={{ fontWeight: 500 }}>{r.date}</td>
                      <td>{r.primaryFreq}</td>
                      <td>{r.freqRatio.toFixed(2)}</td>
                      <td>{r.decayTime}</td>
                      <td>{r.dampingRatio.toFixed(3)}</td>
                      <td>{r.qFactor.toFixed(1)}</td>
                      <td>{r.spectralCentroid}</td>
                      <td>{r.rmsAcceleration.toFixed(2)}</td>
                      <td style={{ fontWeight: 600, color }}>{r.linerThicknessPct}%</td>
                    </tr>
                  )
                })
              : rows.map((r, i) => (
                  <tr
                    key={r.id}
                    style={{
                      opacity: i === 0 ? 1 : 0.85,
                      cursor: r.fftPoints?.length ? 'pointer' : 'default',
                      background: selectedRow?.id === r.id ? 'rgba(96,165,250,0.08)' : undefined,
                    }}
                    onClick={() => r.fftPoints?.length && setSelectedRow(selectedRow?.id === r.id ? null : r)}
                    title={r.fftPoints?.length ? 'Click to view FFT' : undefined}
                  >
                    <td style={{ fontWeight: 500 }}>{r.date}</td>
                    <td>{r.primaryFreq}</td>
                    <td>{r.spectralCentroid}</td>
                    <td>{r.rmsAcceleration?.toFixed(2)}</td>
                    <td>{r.decayTime != null ? r.decayTime.toFixed(1) : '—'}</td>
                    <td>{r.dampingRatio != null ? r.dampingRatio.toFixed(4) : '—'}</td>
                    <td>{r.qFactor != null ? r.qFactor.toFixed(1) : '—'}</td>
                    <td style={{ color: 'var(--muted-foreground)', fontStyle: r.note ? 'normal' : 'italic' }}>{r.note || '—'}</td>
                  </tr>
                ))
            }
          </tbody>
        </table>
      </div>

      {/* ── Per-measurement FFT panel ──────────────────────────────────────── */}
      {selectedRow && selectedRow.fftPoints?.length > 0 && (
        <div style={{ padding: '16px 20px', borderTop: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div>
              <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--foreground)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                FFT Magnitude — {selectedRow.date}
              </span>
              {selectedRow.note && (
                <span style={{ fontSize: '0.7rem', color: 'var(--muted-foreground)', marginLeft: 8 }}>· {selectedRow.note}</span>
              )}
              <span style={{ fontSize: '0.65rem', color: 'var(--muted-foreground)', marginLeft: 8 }}>
                f₁ = {selectedRow.primaryFreq} Hz · Centroid = {selectedRow.spectralCentroid} Hz · RMS = {selectedRow.rmsAcceleration.toFixed(4)} g
              </span>
            </div>
            <button
              onClick={() => setSelectedRow(null)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted-foreground)', padding: 2 }}
              title="Close chart"
            >
              <X size={14} />
            </button>
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={selectedRow.fftPoints} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
              <XAxis
                dataKey="freq"
                type="number"
                domain={['dataMin', 'dataMax']}
                tickFormatter={v => `${v}Hz`}
                tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }}
                axisLine={false}
                tickLine={false}
                width={44}
                tickFormatter={v => v.toFixed(3)}
              />
              <Tooltip
                formatter={v => [`${v.toFixed(4)} g`, 'Magnitude']}
                labelFormatter={l => `${l} Hz`}
                contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }}
              />
              <ReferenceLine x={selectedRow.primaryFreq} stroke="rgba(96,165,250,0.5)" strokeDasharray="3 3" label={{ value: `f₁=${selectedRow.primaryFreq}Hz`, fill: 'rgba(96,165,250,0.7)', fontSize: 9, position: 'insideTopRight' }} />
              <Line type="monotone" dataKey="mag" stroke="#60a5fa" dot={false} strokeWidth={1.5} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

export default function Details() {
  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--foreground)', letterSpacing: '-0.01em' }}>Measurement Details</h2>
        <p style={{ fontSize: '0.875rem', color: 'var(--muted-foreground)', marginTop: 4 }}>Vibration feature breakdown and full session history.</p>
      </div>
      <div className="grid-2" style={{ marginBottom: 20 }}>
        <KeyFeatures />
        <FreqChart />
      </div>
      <HistoryTable />
    </div>
  )
}
