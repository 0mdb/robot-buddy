import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect } from 'react'
import { Header } from './components/Header'
import { TabBar } from './components/TabBar'
import { wsConversationManager } from './lib/wsConversation'
import { wsLogsManager } from './lib/wsLogs'
import { wsManager } from './lib/wsManager'
import { wsProtocolManager } from './lib/wsProtocol'
import { useUiStore } from './stores/uiStore'
import CalibrationTab from './tabs/CalibrationTab'
import DevicesTab from './tabs/DevicesTab'
import DriveTab from './tabs/DriveTab'
import FaceTab from './tabs/FaceTab'
import LogsTab from './tabs/LogsTab'
import MonitorTab from './tabs/MonitorTab'
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
    case 'monitor':
      return <MonitorTab />
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
      wsConversationManager.dispose()
    }
  }, [])

  // Connect protocol WS when Protocol or Face tab is active (face mirror needs TX packets)
  useEffect(() => {
    if (activeTab === 'protocol' || activeTab === 'face') {
      wsProtocolManager.connect()
    } else {
      wsProtocolManager.dispose()
    }
  }, [activeTab])

  // Connect conversation WS when Face tab is active (pipeline timeline + studio)
  useEffect(() => {
    if (activeTab === 'face') {
      wsConversationManager.connect()
    } else {
      wsConversationManager.dispose()
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
