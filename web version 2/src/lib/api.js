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
 */
export async function triggerMeasurement() {
  const res = await fetch(`${getPiBaseUrl()}/trigger`, { method: 'POST' })
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
