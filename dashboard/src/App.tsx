import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import { Header } from './components/Header'
import { TabBar } from './components/TabBar'
import { wsLogsManager } from './lib/wsLogs'
import { wsManager } from './lib/wsManager'
import { wsProtocolManager } from './lib/wsProtocol'
import { useUiStore } from './stores/uiStore'
import CalibrationTab from './tabs/CalibrationTab'
import DevicesTab from './tabs/DevicesTab'
import DriveTab from './tabs/DriveTab'
import FaceTab from './tabs/FaceTab'
import LogsTab from './tabs/LogsTab'
import ParamsTab from './tabs/ParamsTab'
import ProtocolTab from './tabs/ProtocolTab'
import TelemetryTab from './tabs/TelemetryTab'
import './styles/global.module.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 2000,
    },
  },
})

function TabContent() {
  const activeTab = useUiStore((s) => s.activeTab)

  switch (activeTab) {
    case 'drive':
      return <DriveTab />
    case 'telemetry':
      return <TelemetryTab />
    case 'devices':
      return <DevicesTab />
    case 'logs':
      return <LogsTab />
    case 'protocol':
      return <ProtocolTab />
    case 'calibration':
      return <CalibrationTab />
    case 'params':
      return <ParamsTab />
    case 'face':
      return <FaceTab />
    default:
      return <DriveTab />
  }
}

export default function App() {
  const activeTab = useUiStore((s) => s.activeTab)

  useEffect(() => {
    wsManager.connect()
    wsLogsManager.connect()
    return () => {
      wsManager.dispose()
      wsLogsManager.dispose()
      wsProtocolManager.dispose()
    }
  }, [])

  // Connect protocol WS only when the Protocol tab is active
  useEffect(() => {
    if (activeTab === 'protocol') {
      wsProtocolManager.connect()
    } else {
      wsProtocolManager.dispose()
    }
  }, [activeTab])

  return (
    <QueryClientProvider client={queryClient}>
      <div className="layout">
        <Header />
        <TabBar />
        <div className="tabContent">
          <TabContent />
        </div>
      </div>
    </QueryClientProvider>
  )
}
