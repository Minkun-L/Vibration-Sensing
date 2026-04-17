import { useState } from 'react'
import { ThemeProvider, useTheme } from './contexts/ThemeContext.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Details from './pages/Details.jsx'
import SettingsPanel from './pages/SettingsPanel.jsx'
import { LayoutDashboard, TableProperties, Settings, Activity, Radio, Sun, Moon } from 'lucide-react'

const PAGE_TITLES = {
  dashboard: { title: 'Measurement Dashboard',  sub: 'Liner wear overview' },
  details:   { title: 'Measurement Details',    sub: 'Feature breakdown & session history' },
  settings:  { title: 'Measurement Settings',   sub: 'Schedule or trigger measurements' },
}

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  return (
    <button className="theme-toggle" onClick={toggleTheme} title="Toggle theme">
      {theme === 'dark'
        ? <><Sun size={13} /> Light</>
        : <><Moon size={13} /> Dark</>}
    </button>
  )
}

function AppShell() {
  const [tab, setTab] = useState('dashboard')
  const { title, sub } = PAGE_TITLES[tab]

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={16} /> },
    { id: 'details',   label: 'Details',   icon: <TableProperties size={16} /> },
    { id: 'settings',  label: 'Settings',  icon: <Settings size={16} /> },
  ]

  return (
    <div className="app-shell">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-row">
            <div className="sidebar-logo">
              <Activity size={14} />
            </div>
            <span className="sidebar-title">Liner Monitor</span>
          </div>
          <p className="sidebar-subtitle">Vibration-based wear sensing</p>
        </div>

        <div className="sidebar-status">
          <span className="live-dot">
            <span className="live-dot-ring pulse-dot" />
            <span className="live-dot-core" />
          </span>
          System online
        </div>

        <nav className="sidebar-nav">
          {navItems.map(item => (
            <button
              key={item.id}
              className={`nav-btn${tab === item.id ? ' active' : ''}`}
              onClick={() => setTab(item.id)}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="flex items-center gap-1" style={{ marginBottom: 2 }}>
            <Radio size={11} style={{ color: 'var(--muted-foreground)' }} />
            <span>KX132 Accelerometer</span>
          </div>
          <p>6400 Hz · ±8g · SPI</p>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="main-area">
        <header className="topbar">
          <div className="min-w-0">
            <div className="topbar-title truncate">{title}</div>
            <div className="topbar-sub">Chute Liner Monitoring System · Demo · {sub}</div>
          </div>
          <div className="topbar-right">
            <ThemeToggle />
            <div className="tab-pills">
              {navItems.map(item => (
                <button
                  key={item.id}
                  className={`tab-pill${tab === item.id ? ' active' : ''}`}
                  onClick={() => setTab(item.id)}
                >
                  {item.icon}
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </header>

        <div className="page-content">
          {tab === 'dashboard' && <Dashboard />}
          {tab === 'details'   && <Details />}
          {tab === 'settings'  && <SettingsPanel />}
        </div>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider defaultTheme="dark">
      <AppShell />
    </ThemeProvider>
  )
}
