import { useState } from 'react'
import SettingsPanel from './SettingsPanel'
import Dashboard from './Dashboard'

const TABS = [
  { id: 'dashboard', label: '📊 Dashboard' },
  { id: 'settings',  label: '⚙️  Settings' },
]

const styles = {
  root: { fontFamily: 'system-ui, sans-serif', minHeight: '100vh', background: '#fff', color: '#111' },
  header: {
    background: '#1e3a5f',
    color: '#fff',
    padding: '0 24px',
    display: 'flex',
    alignItems: 'center',
    gap: 32,
    height: 52,
  },
  appTitle: { fontSize: 16, fontWeight: 700, whiteSpace: 'nowrap', marginRight: 16 },
  tabBar: { display: 'flex', gap: 4 },
  tab: {
    padding: '6px 18px',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 14,
    fontWeight: 500,
    border: 'none',
    background: 'transparent',
    color: '#cbd5e1',
  },
  tabActive: {
    background: '#fff',
    color: '#1e3a5f',
    fontWeight: 700,
  },
}

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard')

  return (
    <div style={styles.root}>
      <header style={styles.header}>
        <div style={styles.appTitle}>Chute Liner Monitor</div>
        <nav style={styles.tabBar}>
          {TABS.map((t) => (
            <button
              key={t.id}
              style={{ ...styles.tab, ...(activeTab === t.id ? styles.tabActive : {}) }}
              onClick={() => setActiveTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <main>
        {activeTab === 'dashboard' && <Dashboard />}
        {activeTab === 'settings'  && <SettingsPanel />}
      </main>
    </div>
  )
}
