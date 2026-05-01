import { useState, useEffect } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { fetchFeatures, fetchHistory } from '../lib/api.js'
import { Activity, Waves, Timer, Radio, Zap, Wifi, WifiOff, RefreshCw, X, Download } from 'lucide-react'

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

  const primaryFreq      = live?.primaryFreq      ?? null
  const rmsAcceleration  = live?.rmsAcceleration  ?? null
  const dampingRatio     = live?.dampingRatio      ?? null
  const qFactor          = live?.qFactor           ?? null
  const spectralCentroid = live?.spectralCentroid  ?? null
  const dataSource       = live ? `Live · Pi · ${new Date(live.timestamp).toLocaleTimeString()}` : 'Pi offline'

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <div className="card-title">Latest Key Features</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {piStatus === 'connected' && <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.65rem', color: '#4ade80', fontWeight: 600 }}><Wifi size={12} /> Pi connected</span>}
          {piStatus === 'offline'   && <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.65rem', color: '#f87171', fontWeight: 600 }}><WifiOff size={12} /> Pi offline</span>}
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
      <FeatureItem icon={<Timer size={15} />} label="Damping Ratio · Q Factor" sub="ζ · Q = f₁ / bandwidth" value={typeof dampingRatio === 'number' ? dampingRatio.toFixed(4) : dampingRatio} unit="" extra={`Q = ${typeof qFactor === 'number' ? qFactor.toFixed(1) : qFactor}`} />
      <FeatureItem icon={<Radio size={15} />} label="Spectral Centroid" sub="Centroid (Hz) shifts lower as liner thickness decreases" value={spectralCentroid} unit="Hz" />
      <FeatureItem icon={<Zap size={15} />} label="RMS of Acceleration" sub="Root-mean-square of Z-axis; increases as liner wears" value={rmsAcceleration != null ? rmsAcceleration.toFixed(2) : '—'} unit="g" />
    </div>
  )
}

// ── History table ─────────────────────────────────────────────────────────────
function HistoryTable() {
  const [liveHistory, setLiveHistory] = useState(null)
  const [histSrc, setHistSrc] = useState('loading')
  const [compareIds, setCompareIds] = useState([]) // up to 2 selected row ids

  useEffect(() => {
    fetchHistory()
      .then(data => {
        if (Array.isArray(data) && data.length > 0) {
          setLiveHistory([...data].reverse().slice(0, 20))
          setHistSrc('live')
        } else {
          setHistSrc('offline')
        }
      })
      .catch(() => setHistSrc('offline'))
  }, [])

  const rows = liveHistory ?? []

  // Records currently selected (in order of selection)
  const compareRows = compareIds.map(id => rows?.find(r => r.id === id)).filter(Boolean)

  function toggleCompare(r) {
    if (!r.fftPoints?.length) return
    setCompareIds(prev => {
      if (prev.includes(r.id)) return prev.filter(id => id !== r.id)
      if (prev.length >= 2) return [prev[1], r.id] // drop oldest, add new
      return [...prev, r.id]
    })
  }

  // ── Spectral similarity ───────────────────────────────────────────────────
  function computeMetrics(r1, r2) {
    const m1 = Object.fromEntries((r1.fftPoints ?? []).map(p => [p.freq, p.mag]))
    const m2 = Object.fromEntries((r2.fftPoints ?? []).map(p => [p.freq, p.mag]))
    const allFreqs = [...new Set([
      ...Object.keys(m1).map(Number),
      ...Object.keys(m2).map(Number),
    ])].sort((a, b) => a - b)
    const common = allFreqs.filter(f => m1[f] != null && m2[f] != null)
    const v1 = common.map(f => m1[f])
    const v2 = common.map(f => m2[f])

    // Cosine similarity
    const dot = v1.reduce((s, a, i) => s + a * v2[i], 0)
    const n1  = Math.sqrt(v1.reduce((s, a) => s + a * a, 0))
    const n2  = Math.sqrt(v2.reduce((s, a) => s + a * a, 0))
    const cosine = n1 && n2 ? dot / (n1 * n2) : null

    // Pearson correlation
    const mean1 = v1.reduce((s, a) => s + a, 0) / v1.length
    const mean2 = v2.reduce((s, a) => s + a, 0) / v2.length
    const d1 = v1.map(a => a - mean1)
    const d2 = v2.map(a => a - mean2)
    const dotD = d1.reduce((s, a, i) => s + a * d2[i], 0)
    const nd1  = Math.sqrt(d1.reduce((s, a) => s + a * a, 0))
    const nd2  = Math.sqrt(d2.reduce((s, a) => s + a * a, 0))
    const pearson = nd1 && nd2 ? dotD / (nd1 * nd2) : null

    const chartData = allFreqs.map(f => ({ freq: f, mag1: m1[f] ?? null, mag2: m2[f] ?? null }))
    return { cosine, pearson, chartData, nCommon: common.length }
  }

  function downloadCSV() {
    const headers = ['timestamp','date','primaryFreq','spectralCentroid','rmsAcceleration',
                     'secondFreq','qFactor','dampingRatio','noMotor','note']
    const lines = [headers.join(',')]
    for (const r of rows) {
      lines.push([
        r.timestamp ?? '',
        r.date ?? '',
        r.primaryFreq ?? '',
        r.spectralCentroid ?? '',
        r.rmsAcceleration ?? '',
        r.secondFreq ?? '',
        r.qFactor ?? '',
        r.dampingRatio ?? '',
        r.noMotor ? 'true' : 'false',
        `"${(r.note ?? '').replace(/"/g, '""')}"`,
      ].join(','))
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `vibration_history_${new Date().toISOString().slice(0,10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const metrics = compareRows.length === 2 ? computeMetrics(compareRows[0], compareRows[1]) : null

  return (
    <div className="card overflow-hidden">
      <div className="card-header">
        <div>
          <div className="card-title">Measurement History</div>
          <div className="card-sub">
            {histSrc === 'live' && `${liveHistory.length} sessions (latest 20) · newest first${compareIds.length > 0 ? ` · ${compareIds.length}/2 selected` : ''}`}
            {histSrc === 'offline' && 'Pi offline · no data available'}
            {histSrc === 'loading' && 'Loading...'}
          </div>
        </div>
        {histSrc === 'live' && (
          <button
            className="btn-outline"
            onClick={downloadCSV}
            style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.75rem', padding: '6px 12px' }}
          >
            <Download size={13} /> Download CSV
          </button>
        )}
      </div>

      {/* ── Single-row FFT panel ──────────────────────────────────────────── */}
      {compareRows.length === 1 && compareRows[0].fftPoints?.length > 0 && (
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div>
              <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--foreground)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {compareRows[0].date}
              </span>
              {compareRows[0].note && (
                <span style={{ fontSize: '0.7rem', color: 'var(--muted-foreground)', marginLeft: 8 }}>· {compareRows[0].note}</span>
              )}
            </div>
            <button onClick={() => setCompareIds([])} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted-foreground)', padding: 2 }} title="Close">
              <X size={14} />
            </button>
          </div>

          {compareRows[0].timePoints?.length > 0 && (
            <>
              <div style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
                Time Series (HPF) — {compareRows[0].peakWindows?.length ?? 0} peak windows detected
              </div>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={compareRows[0].timePoints.filter(p => Number.isFinite(p.t) && Number.isFinite(p.z))} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                  <XAxis dataKey="t" type="number" domain={['dataMin','dataMax']} tickFormatter={v => Number.isFinite(v) ? `${v.toFixed(1)}s` : ''} tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} axisLine={false} tickLine={false} width={44} tickFormatter={v => Number.isFinite(v) ? v.toFixed(2) : ''} />
                  <Tooltip formatter={v => [Number.isFinite(v) ? `${v.toFixed(4)} g` : '—', 'Z (HPF)']} labelFormatter={l => Number.isFinite(+l) ? `${(+l).toFixed(3)} s` : ''} contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }} />
                  {(compareRows[0].peakWindows ?? []).flatMap((pw, i) => [
                    <ReferenceLine key={`s${i}`} x={pw.tStart} stroke="rgba(239,68,68,0.6)" strokeDasharray="3 2" strokeWidth={1} />,
                    <ReferenceLine key={`e${i}`} x={pw.tEnd}   stroke="rgba(239,68,68,0.3)" strokeDasharray="3 2" strokeWidth={1} />,
                  ])}
                  <Line type="monotone" dataKey="z" stroke="#94a3b8" dot={false} strokeWidth={1} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
              <div style={{ marginBottom: 16 }} />
            </>
          )}

          <div style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
            FFT Magnitude · f₁ = {compareRows[0].primaryFreq} Hz · Centroid = {compareRows[0].spectralCentroid} Hz · RMS = {compareRows[0].rmsAcceleration?.toFixed(4) ?? '—'} g
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={compareRows[0].fftPoints} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
              <XAxis dataKey="freq" type="number" domain={['dataMin','dataMax']} tickFormatter={v => `${v}Hz`} tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} axisLine={false} tickLine={false} width={44} tickFormatter={v => v.toFixed(3)} />
              <Tooltip formatter={v => [`${v.toFixed(4)} g`, 'Magnitude']} labelFormatter={l => `${l} Hz`} contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }} />
              <ReferenceLine x={compareRows[0].primaryFreq} stroke="rgba(96,165,250,0.5)" strokeDasharray="3 3" label={{ value: `f₁=${compareRows[0].primaryFreq}Hz`, fill: 'rgba(96,165,250,0.7)', fontSize: 9, position: 'insideTopRight' }} />
              <Line type="monotone" dataKey="mag" stroke="#60a5fa" dot={false} strokeWidth={1.5} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── Comparison panel (2 rows selected) ───────────────────────────── */}
      {compareRows.length === 2 && metrics && (
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--foreground)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Spectrum Comparison
            </span>
            <button onClick={() => setCompareIds([])} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted-foreground)', padding: 2 }} title="Close">
              <X size={14} />
            </button>
          </div>

          {/* Legend */}
          <div style={{ display: 'flex', gap: 24, marginBottom: 10 }}>
            {compareRows.map((r, idx) => (
              <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.72rem' }}>
                <span style={{ display: 'inline-block', width: 14, height: 3, borderRadius: 2, background: idx === 0 ? '#60a5fa' : '#f472b6' }} />
                <span style={{ color: 'var(--foreground)', fontWeight: 600 }}>{r.date}</span>
                {r.note && <span style={{ color: 'var(--muted-foreground)' }}>· {r.note}</span>}
              </div>
            ))}
          </div>

          {/* Overlaid FFT chart */}
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={metrics.chartData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
              <XAxis dataKey="freq" type="number" domain={['dataMin','dataMax']} tickFormatter={v => `${v}Hz`} tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} axisLine={false} tickLine={false} width={44} tickFormatter={v => v.toFixed(3)} />
              <Tooltip
                formatter={(v, name) => [v != null ? `${(+v).toFixed(4)} g` : '—', name === 'mag1' ? (compareRows[0].note || compareRows[0].date) : (compareRows[1].note || compareRows[1].date)]}
                labelFormatter={l => `${l} Hz`}
                contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }}
              />
              <ReferenceLine x={compareRows[0].primaryFreq} stroke="rgba(96,165,250,0.4)" strokeDasharray="3 3" />
              <ReferenceLine x={compareRows[1].primaryFreq} stroke="rgba(244,114,182,0.4)" strokeDasharray="3 3" />
              <Line type="monotone" dataKey="mag1" stroke="#60a5fa" dot={false} strokeWidth={1.5} isAnimationActive={false} connectNulls={false} />
              <Line type="monotone" dataKey="mag2" stroke="#f472b6" dot={false} strokeWidth={1.5} isAnimationActive={false} connectNulls={false} />
            </LineChart>
          </ResponsiveContainer>

          {/* Metrics row */}
          <div style={{ display: 'flex', gap: 0, marginTop: 16, borderTop: '1px solid var(--border)', paddingTop: 14 }}>
            <div style={{ flex: 1, textAlign: 'center' }}>
              <div style={{ fontSize: '0.6rem', color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>Cosine Similarity</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--foreground)' }}>
                {metrics.cosine != null ? metrics.cosine.toFixed(4) : '—'}
              </div>
              <div style={{ fontSize: '0.65rem', color: 'var(--muted-foreground)', marginTop: 2 }}>1.000 = identical shape</div>
            </div>
            <div style={{ width: 1, background: 'var(--border)', margin: '0 4px' }} />
            <div style={{ flex: 1, textAlign: 'center' }}>
              <div style={{ fontSize: '0.6rem', color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>Pearson Correlation</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--foreground)' }}>
                {metrics.pearson != null ? metrics.pearson.toFixed(4) : '—'}
              </div>
              <div style={{ fontSize: '0.65rem', color: 'var(--muted-foreground)', marginTop: 2 }}>1.000 = perfect linear match</div>
            </div>
            <div style={{ width: 1, background: 'var(--border)', margin: '0 4px' }} />
            <div style={{ flex: 1, textAlign: 'center' }}>
              <div style={{ fontSize: '0.6rem', color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>Common Freq Bins</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--foreground)' }}>
                {metrics.nCommon}
              </div>
              <div style={{ fontSize: '0.65rem', color: 'var(--muted-foreground)', marginTop: 2 }}>shared frequency points</div>
            </div>
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table>
          <thead>
            <tr><th style={{ width: 32 }} />{['Date','f₁ (Hz)','Centroid (Hz)','RMS (g)','ζ','Q','Note'].map(h => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {histSrc === 'offline' || (histSrc !== 'loading' && rows.length === 0)
              ? <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--muted-foreground)', padding: '32px 0', fontStyle: 'italic' }}>Pi offline · connect to Pi to view history</td></tr>
              : rows.map((r, i) => {
                  const selIdx = compareIds.indexOf(r.id)
                  const rowBg = selIdx === 0 ? 'rgba(96,165,250,0.08)' : selIdx === 1 ? 'rgba(244,114,182,0.08)' : undefined
                  return (
                    <tr key={r.id} style={{ opacity: i === 0 ? 1 : 0.85, background: rowBg }}>
                      <td style={{ textAlign: 'center' }}>
                        {r.fftPoints?.length ? (
                          <input
                            type="checkbox"
                            checked={selIdx !== -1}
                            onChange={() => toggleCompare(r)}
                            style={{ accentColor: selIdx === 1 ? '#f472b6' : '#60a5fa', cursor: 'pointer', width: 13, height: 13 }}
                          />
                        ) : null}
                      </td>
                      <td style={{ fontWeight: 500 }}>{r.date}</td>
                      <td>{r.primaryFreq}</td>
                      <td>{r.spectralCentroid}</td>
                      <td>{r.rmsAcceleration?.toFixed(2)}</td>
                      <td>{r.dampingRatio != null ? r.dampingRatio.toFixed(4) : '—'}</td>
                      <td>{r.qFactor != null ? r.qFactor.toFixed(1) : '—'}</td>
                      <td style={{ color: 'var(--muted-foreground)', fontStyle: r.note ? 'normal' : 'italic' }}>{r.note || '—'}</td>
                    </tr>
                  )
                })
              }
          </tbody>
        </table>
      </div>
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
      <div style={{ marginBottom: 20 }}>
        <KeyFeatures />
      </div>
      <HistoryTable />
    </div>
  )
}
