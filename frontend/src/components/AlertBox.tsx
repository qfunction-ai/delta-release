interface AlertBoxProps {
  variant: 'warning' | 'danger' | 'info'
  children: React.ReactNode
}

const VARIANT_STYLES: Record<AlertBoxProps['variant'], React.CSSProperties> = {
  warning: {
    background: 'var(--warning-subtle)',
    border: '1px solid var(--warning-border)',
  },
  danger: {
    background: 'var(--danger-subtle)',
    border: '1px solid var(--danger-border)',
  },
  info: {
    background: 'var(--info-subtle)',
    border: '1px solid var(--info-border)',
  },
}

export default function AlertBox({ variant, children }: AlertBoxProps) {
  return (
    <div
      role="alert"
      style={{
        marginTop: '1rem',
        padding: '0.75rem 1rem',
        borderRadius: 'var(--radius-md)',
        fontSize: '0.8125rem',
        color: 'var(--text-secondary)',
        ...VARIANT_STYLES[variant],
      }}
    >
      {children}
    </div>
  )
}
