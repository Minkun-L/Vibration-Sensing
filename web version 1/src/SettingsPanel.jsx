import { useState } from 'react'

const styles = {
  page: { maxWidth: 520, margin: '0 auto', padding: '32px 24px' },
  heading: { fontSize: 22, fontWeight: 700, marginBottom: 28 },
  label: { display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 6, color: '#444' },
  input: {
    display: 'block',
    width: '100%',
    padding: '10px 12px',
    fontSize: 15,
    border: '1px solid #ccc',
    borderRadius: 6,
    marginBottom: 28,
    boxSizing: 'border-box',
  },
  button: {
    padding: '12px 28px',
    fontSize: 15,
    fontWeight: 600,
    background: '#2563eb',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
  },
  statusBox: {
    marginTop: 20,
    padding: '14px 18px',
    background: '#f0fdf4',
    border: '1px solid #86efac',
    borderRadius: 6,
    fontSize: 15,
    color: '#166534',
    fontWeight: 500,
  },
  sectionTitle: { fontSize: 14, fontWeight: 600, color: '#444', marginBottom: 8 },
  currentTime: {
    padding: '10px 14px',
    background: '#f1f5f9',
    borderRadius: 6,
    fontSize: 14,
    color: '#475569',
    marginBottom: 28,
  },
}

export default function SettingsPanel() {
  const [nextMeasurement, setNextMeasurement] = useState('')
  const [measuring, setMeasuring] = useState(false)
  const [done, setDone] = useState(false)

  function handleStart() {
    setMeasuring(true)
    setDone(false)
    // Simulate a 3-second "measurement"
    setTimeout(() => {
      setMeasuring(false)
      setDone(true)
    }, 3000)
  }

  const now = new Date().toLocaleString()

  return (
    <div style={styles.page}>
      <div style={styles.heading}>Settings</div>

      <div style={styles.sectionTitle}>Current System Time</div>
      <div style={styles.currentTime}>{now}</div>

      <label style={styles.label} htmlFor="next-time">
        Schedule Next Measurement
      </label>
      <input
        id="next-time"
        type="datetime-local"
        style={styles.input}
        value={nextMeasurement}
        onChange={(e) => setNextMeasurement(e.target.value)}
      />

      {nextMeasurement && (
        <div style={{ ...styles.currentTime, marginBottom: 20 }}>
          Next scheduled: {new Date(nextMeasurement).toLocaleString()}
        </div>
      )}

      <button style={styles.button} onClick={handleStart} disabled={measuring}>
        {measuring ? 'Measuring...' : 'Start Measurement Now'}
      </button>

      {measuring && (
        <div style={styles.statusBox}>
          ⏳ Measuring and collecting data...
        </div>
      )}

      {done && !measuring && (
        <div style={styles.statusBox}>
          ✅ Measurement complete. View results on the Dashboard tab.
        </div>
      )}
    </div>
  )
}
