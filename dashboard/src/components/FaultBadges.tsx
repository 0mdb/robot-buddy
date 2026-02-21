import { decodeFaults } from '../constants'
import styles from '../styles/header.module.css'

interface Props {
  flags: number
}

export function FaultBadges({ flags }: Props) {
  if (flags === 0) return null
  const faults = decodeFaults(flags)
  return (
    <>
      {faults.map((f) => (
        <span key={f} className={styles.faultBadge}>
          {f}
        </span>
      ))}
    </>
  )
}
