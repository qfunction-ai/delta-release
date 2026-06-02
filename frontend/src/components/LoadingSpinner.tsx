interface Props {
  size?: 'sm' | 'md' | 'lg'
  label?: string
}

export function LoadingSpinner({ size = 'md', label = 'Loading...' }: Props) {
  return (
    <output className={`loading-spinner loading-spinner-${size}`} aria-live="polite">
      <div className="loading-spinner-icon" aria-hidden="true" />
      <span className="loading-spinner-label">{label}</span>
    </output>
  )
}
