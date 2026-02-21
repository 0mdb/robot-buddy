import { TABS } from '../constants'
import { useUiStore } from '../stores/uiStore'
import styles from '../styles/tabs.module.css'

export function TabBar() {
  const activeTab = useUiStore((s) => s.activeTab)
  const setActiveTab = useUiStore((s) => s.setActiveTab)

  return (
    <div className={styles.tabBar}>
      {TABS.map((t) => (
        <button
          type="button"
          key={t.id}
          className={`${styles.tab} ${activeTab === t.id ? styles.tabActive : ''}`}
          onClick={() => setActiveTab(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}
