// Pi hotspot IP — when Pi is in AP mode the address is always 192.168.4.1
// Change this if you're on a shared router instead.
export const PI_BASE_URL = 'http://192.168.4.1:5000'

/**
 * Fetch the latest extracted features from the Pi.
 * Returns { primaryFreq, rmsAcceleration, timestamp } or throws on error.
 */
export async function fetchFeatures() {
  const res = await fetch(`${PI_BASE_URL}/features`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

/**
 * POST to /trigger to start a measurement on the Pi immediately.
 */
export async function triggerMeasurement() {
  const res = await fetch(`${PI_BASE_URL}/trigger`, { method: 'POST' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

/**
 * Check if the Pi server is reachable and has data.
 */
export async function fetchStatus() {
  const res = await fetch(`${PI_BASE_URL}/status`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
