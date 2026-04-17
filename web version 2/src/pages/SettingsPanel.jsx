import { useState, useEffect } from 'react'
import { Calendar, Clock, PlayCircle, CheckCircle2, Loader2, Monitor } from 'lucide-react'
import { useTheme } from '../contexts/ThemeContext.jsx'

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
  const [status, setStatus] = useState('idle') // idle | measuring | done
  const [completedAt, setCompletedAt] = useState('')

  function handleStart() {
    if (status === 'measuring') return
    setStatus('measuring')
    setTimeout(() => {
      setStatus('done')
      setCompletedAt(new Date().toLocaleTimeString())
    }, 4000)
  }

  function handleReset() {
    setStatus('idle')
    setCompletedAt('')
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
                Completed at {completedAt}. Data saved to history.
              </p>
            </div>
          </div>
        )}

        <div style={{ display: 'flex', gap: 12 }}>
          <button className="btn-primary" onClick={handleStart} disabled={status === 'measuring'}>
            {status === 'measuring'
              ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Measuring...</>
              : <><PlayCircle size={14} /> Start Measurement Now</>}
          </button>
          {status === 'done' && (
            <button className="btn-outline" onClick={handleReset}>Reset</button>
          )}
        </div>
      </div>

      <p style={{ marginTop: 20, fontSize: '0.7rem', color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
        <strong style={{ color: 'var(--foreground)', opacity: 0.6 }}>Note:</strong> Each measurement session takes approximately 4 seconds. The system will automatically process the vibration signal and update the Dashboard with the latest liner thickness estimate.
      </p>
    </div>
  )
}
