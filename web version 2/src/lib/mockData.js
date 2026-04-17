// Mock historical measurement data for Chute Liner Monitoring System
// Each entry represents one measurement session

export const mockHistory = [
  {
    id: "m001", timestamp: "2025-10-01T08:00:00", date: "Oct 1",
    primaryFreq: 312, freqRatio: 2.71, decayTime: 48, dampingRatio: 0.021, qFactor: 23.8,
    spectralCentroid: 428, spectralEnergy: 0.034, rmsAcceleration: 0.82, linerThicknessPct: 100,
  },
  {
    id: "m002", timestamp: "2025-10-15T08:00:00", date: "Oct 15",
    primaryFreq: 308, freqRatio: 2.72, decayTime: 45, dampingRatio: 0.023, qFactor: 21.7,
    spectralCentroid: 421, spectralEnergy: 0.038, rmsAcceleration: 0.86, linerThicknessPct: 97,
  },
  {
    id: "m003", timestamp: "2025-11-01T08:00:00", date: "Nov 1",
    primaryFreq: 301, freqRatio: 2.74, decayTime: 42, dampingRatio: 0.026, qFactor: 19.3,
    spectralCentroid: 412, spectralEnergy: 0.044, rmsAcceleration: 0.91, linerThicknessPct: 93,
  },
  {
    id: "m004", timestamp: "2025-11-15T08:00:00", date: "Nov 15",
    primaryFreq: 295, freqRatio: 2.76, decayTime: 39, dampingRatio: 0.029, qFactor: 17.2,
    spectralCentroid: 403, spectralEnergy: 0.051, rmsAcceleration: 0.97, linerThicknessPct: 89,
  },
  {
    id: "m005", timestamp: "2025-12-01T08:00:00", date: "Dec 1",
    primaryFreq: 287, freqRatio: 2.79, decayTime: 36, dampingRatio: 0.033, qFactor: 15.2,
    spectralCentroid: 392, spectralEnergy: 0.061, rmsAcceleration: 1.04, linerThicknessPct: 84,
  },
  {
    id: "m006", timestamp: "2025-12-15T08:00:00", date: "Dec 15",
    primaryFreq: 279, freqRatio: 2.81, decayTime: 33, dampingRatio: 0.037, qFactor: 13.5,
    spectralCentroid: 380, spectralEnergy: 0.073, rmsAcceleration: 1.12, linerThicknessPct: 79,
  },
  {
    id: "m007", timestamp: "2026-01-01T08:00:00", date: "Jan 1",
    primaryFreq: 268, freqRatio: 2.84, decayTime: 30, dampingRatio: 0.042, qFactor: 11.9,
    spectralCentroid: 366, spectralEnergy: 0.089, rmsAcceleration: 1.21, linerThicknessPct: 73,
  },
  {
    id: "m008", timestamp: "2026-01-15T08:00:00", date: "Jan 15",
    primaryFreq: 256, freqRatio: 2.89, decayTime: 27, dampingRatio: 0.048, qFactor: 10.4,
    spectralCentroid: 350, spectralEnergy: 0.108, rmsAcceleration: 1.33, linerThicknessPct: 66,
  },
  {
    id: "m009", timestamp: "2026-02-01T08:00:00", date: "Feb 1",
    primaryFreq: 243, freqRatio: 2.95, decayTime: 24, dampingRatio: 0.055, qFactor: 9.1,
    spectralCentroid: 332, spectralEnergy: 0.132, rmsAcceleration: 1.48, linerThicknessPct: 58,
  },
  {
    id: "m010", timestamp: "2026-02-15T08:00:00", date: "Feb 15",
    primaryFreq: 229, freqRatio: 3.02, decayTime: 21, dampingRatio: 0.063, qFactor: 7.9,
    spectralCentroid: 313, spectralEnergy: 0.161, rmsAcceleration: 1.65, linerThicknessPct: 50,
  },
  {
    id: "m011", timestamp: "2026-03-01T08:00:00", date: "Mar 1",
    primaryFreq: 214, freqRatio: 3.10, decayTime: 18, dampingRatio: 0.073, qFactor: 6.8,
    spectralCentroid: 292, spectralEnergy: 0.197, rmsAcceleration: 1.84, linerThicknessPct: 41,
  },
  {
    id: "m012", timestamp: "2026-04-01T08:00:00", date: "Apr 1",
    primaryFreq: 197, freqRatio: 3.20, decayTime: 15, dampingRatio: 0.085, qFactor: 5.9,
    spectralCentroid: 269, spectralEnergy: 0.241, rmsAcceleration: 2.08, linerThicknessPct: 31,
  },
]

// Latest measurement (most recent)
export const latestMeasurement = mockHistory[mockHistory.length - 1]

// Threshold helper
export function getThicknessStatus(pct) {
  if (pct >= 60) return 'healthy'
  if (pct >= 40) return 'warning'
  return 'critical'
}
