export const DEFAULT_PI_IP  = '192.168.4.1'
export const PI_IP_STORAGE_KEY = 'pi_ip'

/** Returns the Pi base URL, reading the IP from localStorage if set. */
export function getPiBaseUrl() {
  const ip = localStorage.getItem(PI_IP_STORAGE_KEY) || DEFAULT_PI_IP
  return `http://${ip}:5000`
}

/**
 * Fetch the latest extracted features from the Pi.
 * Returns { primaryFreq, rmsAcceleration, spectralCentroid, timestamp } or throws on error.
 */
export async function fetchFeatures() {
  const res = await fetch(`${getPiBaseUrl()}/features`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

/**
 * POST to /trigger to start a measurement on the Pi immediately.
 * @param {string}  note     Optional user note attached to this run.
 * @param {boolean} noMotor  If true, skip the motor impulse (background noise mode).
 */
export async function triggerMeasurement(note = '', noMotor = false) {
  const res = await fetch(`${getPiBaseUrl()}/trigger`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note, noMotor }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

/**
 * Check if the Pi server is reachable and has data.
 */
export async function fetchStatus() {
  const res = await fetch(`${getPiBaseUrl()}/status`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

/**
 * Fetch the full measurement history recorded on the Pi.
 * Returns an array of records or throws on error.
 */
export async function fetchHistory() {
  const res = await fetch(`${getPiBaseUrl()}/history`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

/**
 * Fetch the latest FFT chart data from the Pi.
 * Returns { points: [{freq, mag}, ...] } or throws on error.
 */
export async function fetchFftData() {
  const res = await fetch(`${getPiBaseUrl()}/fft`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
