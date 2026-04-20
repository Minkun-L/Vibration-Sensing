import { useState, useEffect } from 'react'
import { Calendar, Clock, PlayCircle, CheckCircle2, Loader2, Monitor, WifiOff, Wifi, Save } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { useTheme } from '../contexts/ThemeContext.jsx'
import { triggerMeasurement, fetchStatus, fetchFeatures, fetchFftData, DEFAULT_PI_IP, PI_IP_STORAGE_KEY } from '../lib/api.js'

export default function SettingsPanel() {
  const { theme } = useTheme()

  // ── Real-time clock ────────────────────────────────────────────────────────
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  // ── Scheduled time ─────────────────────────────────────────────────────────
  const [nextTime, setNextTime] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + 1)
    d.setHours(8, 0, 0, 0)
    return d.toISOString().slice(0, 16)
  })

  // ── Measurement state ──────────────────────────────────────────────────────
  const [status, setStatus] = useState('idle') // idle | measuring | done | error
  const [completedAt, setCompletedAt] = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  const [piOnline, setPiOnline] = useState(null) // null=checking, true, false
  const [features, setFeatures] = useState(null)  // features received from Pi after measurement
  const [note, setNote] = useState('')
  const [fftData, setFftData] = useState(null)
  const [piIpDraft, setPiIpDraft] = useState(
    () => localStorage.getItem(PI_IP_STORAGE_KEY) || DEFAULT_PI_IP
  )

  function checkConnection() {
    setPiOnline(null)
    fetchStatus()
      .then(() => setPiOnline(true))
      .catch(() => setPiOnline(false))
  }

  function saveAndTestIp() {
    const trimmed = piIpDraft.trim()
    if (!trimmed) return
    localStorage.setItem(PI_IP_STORAGE_KEY, trimmed)
    checkConnection()
  }

  // Check Pi reachability on mount
  useEffect(() => { checkConnection() }, [])

  async function handleStart() {
    if (status === 'measuring') return
    setStatus('measuring')
    setErrorMsg('')
    try {
      await triggerMeasurement(note)
      // Poll /status until hasMeasurement flips or timeout (90s = 20s run + processing)
      const deadline = Date.now() + 90000
      while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 1500))
        const s = await fetchStatus()
        if (s.hasMeasurement) break
      }
      setStatus('done')
      setCompletedAt(new Date().toLocaleTimeString())
      setPiOnline(true)
      // Fetch the features that were just written by mk_kx132.py
      try {
        const f = await fetchFeatures()
        setFeatures(f)
      } catch {
        setFeatures(null)
      }
      try {
        const fft = await fetchFftData()
        setFftData(fft)
      } catch {
        setFftData(null)
      }
    } catch (e) {
      setStatus('error')
      setErrorMsg('Could not reach the Pi. Make sure you are connected to the Pi hotspot.')
      setPiOnline(false)
    }
  }

  // Next scheduled preview
  const scheduledPreview = nextTime
    ? new Date(nextTime).toLocaleString(undefined, { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : null

  const msUntil = nextTime ? new Date(nextTime).getTime() - now.getTime() : null

  function formatCountdown(ms) {
    if (ms <= 0) return 'Overdue'
    const s = Math.floor(ms / 1000)
    const d = Math.floor(s / 86400)
    const h = Math.floor((s % 86400) / 3600)
    const m = Math.floor((s % 3600) / 60)
    const sec = s % 60
    if (d > 0) return `${d}d ${h}h ${m}m`
    if (h > 0) return `${h}h ${m}m ${sec}s`
    return `${m}m ${sec}s`
  }

  return (
    <div className="max-w-xl">
      <div style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--foreground)', letterSpacing: '-0.01em' }}>Measurement Settings</h2>
        <p style={{ fontSize: '0.875rem', color: 'var(--muted-foreground)', marginTop: 4 }}>
          Configure the next scheduled measurement or start one immediately.
        </p>
      </div>

      {/* ── Pi Connection ───────────────────────────────────────────────────── */}
      <div className="card" style={{ padding: 24, marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Wifi size={16} style={{ color: 'var(--primary)' }} />
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--foreground)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Pi Connection
          </span>
        </div>

        <label style={{ display: 'block', fontSize: '0.65rem', color: 'var(--muted-foreground)', marginBottom: 8, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Pi IP Address
        </label>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            type="text"
            value={piIpDraft}
            onChange={e => setPiIpDraft(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && saveAndTestIp()}
            placeholder="192.168.4.1"
            style={{ flex: 1, fontFamily: 'var(--font-mono)' }}
          />
          <button className="btn-outline" onClick={saveAndTestIp} style={{ display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}>
            <Save size={13} /> Save &amp; Test
          </button>
        </div>
        <p style={{ marginTop: 8, fontSize: '0.7rem', color: 'var(--muted-foreground)', lineHeight: 1.5 }}>
          Use <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem' }}>192.168.4.1</code> when connected to the Pi hotspot,
          or the router-assigned IP when both devices share the same WiFi.
        </p>
        <p style={{ marginTop: 8, fontSize: '0.7rem', lineHeight: 1.5,
          color: piOnline === true ? '#4ade80' : piOnline === false ? '#f87171' : 'var(--muted-foreground)'
        }}>
          {piOnline === null  && '⏳ Checking connection...'}
          {piOnline === true  && '✅ Pi is reachable.'}
          {piOnline === false && '⚠️ Pi not reachable at this address.'}
        </p>
      </div>

      {/* ── Current system time ─────────────────────────────────────────────── */}
      <div className="card" style={{ padding: '16px 20px', marginBottom: 24, display: 'flex', alignItems: 'center', gap: 12 }}>
        <Monitor size={15} style={{ color: 'var(--muted-foreground)', flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontSize: '0.65rem', color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600, marginBottom: 2 }}>
            Current System Time
          </p>
          <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--foreground)', fontFamily: 'var(--font-mono)' }}>
            {now.toLocaleString(undefined, { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </p>
        </div>
        <span className="live-dot" style={{ flexShrink: 0 }}>
          <span className="live-dot-ring pulse-dot" />
          <span className="live-dot-core" />
        </span>
      </div>

      {/* ── Schedule card ───────────────────────────────────────────────────── */}
      <div className="card" style={{ padding: 24, marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Calendar size={16} style={{ color: 'var(--primary)' }} />
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--foreground)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Next Scheduled Measurement
          </span>
        </div>

        <label style={{ display: 'block', fontSize: '0.65rem', color: 'var(--muted-foreground)', marginBottom: 8, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Date &amp; Time
        </label>
        <input
          type="datetime-local"
          value={nextTime}
          onChange={e => setNextTime(e.target.value)}
          style={{ colorScheme: theme }}
        />

        {scheduledPreview && (
          <div className="status-preview">
            <p style={{ fontSize: '0.65rem', color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600, marginBottom: 4 }}>
              Next scheduled
            </p>
            <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--foreground)', fontFamily: 'var(--font-mono)' }}>
              {scheduledPreview}
            </p>
            {msUntil !== null && (
              <p style={{ fontSize: '0.7rem', color: 'var(--muted-foreground)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Clock size={11} />
                {msUntil > 0 ? `Starts in ${formatCountdown(msUntil)}` : 'This time has already passed'}
              </p>
            )}
          </div>
        )}

        <p style={{ marginTop: 12, fontSize: '0.7rem', color: 'var(--muted-foreground)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <Clock size={12} />
          Sensor will automatically activate at the scheduled time.
        </p>
      </div>

      {/* ── Manual trigger card ─────────────────────────────────────────────── */}
      <div className="card" style={{ padding: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <PlayCircle size={16} style={{ color: 'var(--primary)' }} />
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--foreground)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Manual Trigger
          </span>
        </div>

        <label style={{ display: 'block', fontSize: '0.65rem', color: 'var(--muted-foreground)', marginBottom: 8, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Run Note (optional)
        </label>
        <input
          type="text"
          value={note}
          onChange={e => setNote(e.target.value)}
          placeholder="e.g. baseline, after impact, liner replaced..."
          disabled={status === 'measuring'}
          style={{ marginBottom: 16 }}
        />

        {status === 'idle' && (
          <p style={{ fontSize: '0.875rem', color: 'var(--muted-foreground)', marginBottom: 16 }}>
            Click the button below to start a measurement immediately. The sensor will collect vibration data for approximately 4 seconds.
          </p>
        )}

        {status === 'measuring' && (
          <div className="status-measuring">
            <span className="live-dot">
              <span className="live-dot-ring pulse-dot" />
              <span className="live-dot-core" />
            </span>
            <span style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--primary)', flex: 1 }}>
              Measuring and collecting data...
            </span>
            <Loader2 size={14} style={{ color: 'var(--primary)', animation: 'spin 1s linear infinite' }} />
          </div>
        )}

        {status === 'done' && (
          <div className="status-done">
            <CheckCircle2 size={16} style={{ color: '#34d399', flexShrink: 0 }} />
            <div>
              <p style={{ fontSize: '0.875rem', fontWeight: 500, color: '#34d399' }}>Measurement complete</p>
              <p style={{ fontSize: '0.7rem', color: 'var(--muted-foreground)', marginTop: 2 }}>
                Completed at {completedAt}. Switch to Vibration Signal Analysis to see the results.
              </p>
            </div>
          </div>
        )}

        {status === 'error' && (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '12px 14px', borderRadius: 'var(--radius)', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)', marginBottom: 16 }}>
            <WifiOff size={15} style={{ color: '#f87171', flexShrink: 0, marginTop: 1 }} />
            <p style={{ fontSize: '0.8rem', color: '#f87171' }}>{errorMsg}</p>
          </div>
        )}

        <div style={{ display: 'flex', gap: 12 }}>
          <button className="btn-primary" onClick={handleStart} disabled={status === 'measuring'}>
            {status === 'measuring'
              ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Measuring...</>
              : <><PlayCircle size={14} /> Start Measurement Now</>}
          </button>
          {(status === 'done' || status === 'error') && (
            <button className="btn-outline" onClick={() => { setStatus('idle'); setErrorMsg(''); setFeatures(null); setFftData(null); setNote('') }}>Reset</button>
          )}
        </div>

        {/* ── Features result ───────────────────────────────────────────────── */}
        {status === 'done' && features && (
          <div style={{ marginTop: 20, padding: 16, borderRadius: 'var(--radius)', background: 'rgba(74,222,128,0.06)', border: '1px solid rgba(74,222,128,0.25)' }}>
            <p style={{ fontSize: '0.65rem', fontWeight: 600, color: '#4ade80', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
              Measurement Results
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                <span style={{ color: 'var(--muted-foreground)' }}>Primary Resonance Frequency</span>
                <span style={{ fontWeight: 700, color: 'var(--foreground)', fontFamily: 'var(--font-mono)' }}>{features.primaryFreq} Hz</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                <span style={{ color: 'var(--muted-foreground)' }}>Spectral Centroid</span>
                <span style={{ fontWeight: 700, color: 'var(--foreground)', fontFamily: 'var(--font-mono)' }}>{features.spectralCentroid} Hz</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                <span style={{ color: 'var(--muted-foreground)' }}>RMS Acceleration</span>
                <span style={{ fontWeight: 700, color: 'var(--foreground)', fontFamily: 'var(--font-mono)' }}>{features.rmsAcceleration?.toFixed(4)} g</span>
              </div>
            </div>
            {features.note && (
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid rgba(74,222,128,0.15)' }}>
                <span style={{ fontSize: '0.65rem', color: 'var(--muted-foreground)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Note: </span>
                <span style={{ fontSize: '0.8rem', color: 'var(--foreground)' }}>{features.note}</span>
              </div>
            )}
            <p style={{ fontSize: '0.65rem', color: 'var(--muted-foreground)', marginTop: 10 }}>
              Recorded at {new Date(features.timestamp).toLocaleString()}
            </p>
            {fftData?.points?.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <p style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
                  FFT Magnitude Spectrum
                </p>
                <ResponsiveContainer width="100%" height={180}>
                  <LineChart data={fftData.points} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
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
                      width={40}
                      tickFormatter={v => v.toFixed(3)}
                    />
                    <Tooltip
                      formatter={v => [`${v.toFixed(4)} g`, 'Magnitude']}
                      labelFormatter={l => `${l} Hz`}
                      contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }}
                    />
                    <Line type="monotone" dataKey="mag" stroke="#4ade80" dot={false} strokeWidth={1.5} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        )}
        {status === 'done' && !features && (
          <div style={{ marginTop: 20, padding: '12px 14px', borderRadius: 'var(--radius)', background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.25)' }}>
            <p style={{ fontSize: '0.8rem', color: '#fbbf24' }}>Measurement completed but features could not be retrieved from the Pi.</p>
          </div>
        )}
      </div>


    </div>
  )
}
