interface PolicyListProps {
  items: { key: string; label: React.ReactNode; badge?: React.ReactNode }[]
  onRemove: (key: string) => void
  disabled?: boolean
}

/**
 * Reusable list for policy items (denied tools, approval tools, rate limits).
 * Each row shows a label, optional badge, and a remove button.
 */
export function PolicyList({ items, onRemove, disabled }: PolicyListProps) {
  if (items.length === 0) return null
  return (
    <div className="gap-2" style={{ display: 'grid', marginBottom: '1rem' }}>
      {items.map(item => (
        <div key={item.key} className="flex items-center justify-between policy-list-item">
          <span className="font-mono text-sm">{item.label}</span>
          <div className="flex items-center gap-2">
            {item.badge}
            <button className="btn btn-danger btn-sm" onClick={() => onRemove(item.key)} disabled={disabled}>Remove</button>
          </div>
        </div>
      ))}
    </div>
  )
}
