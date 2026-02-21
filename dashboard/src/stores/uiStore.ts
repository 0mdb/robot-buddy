import { create } from 'zustand'
import type { TabId } from '../types'

interface UiState {
  activeTab: TabId
  videoEnabled: boolean
  setActiveTab: (tab: TabId) => void
  setVideoEnabled: (enabled: boolean) => void
}

export const useUiStore = create<UiState>()((set) => ({
  activeTab: 'drive',
  videoEnabled: false,
  setActiveTab: (tab) => set({ activeTab: tab }),
  setVideoEnabled: (enabled) => set({ videoEnabled: enabled }),
}))
