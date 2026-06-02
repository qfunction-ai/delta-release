interface ToggleSwitchProps {
  checked: boolean
  onChange: () => void
  disabled?: boolean
  'aria-label'?: string
  id?: string
}

export default function ToggleSwitch({ checked, onChange, disabled = false, 'aria-label': ariaLabel, id }: ToggleSwitchProps) {
  return (
    <button
      id={id}
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel || 'Toggle'}
      onClick={onChange}
      disabled={disabled}
      style={{
        width: 36,
        height: 18,
        borderRadius: 0,
        border: `1px solid ${checked ? 'var(--accent-border)' : 'var(--border)'}`,
        cursor: disabled ? 'wait' : 'pointer',
        background: checked ? 'var(--accent-subtle)' : 'var(--bg-input)',
        position: 'relative',
        transition: 'all 0.2s ease',
        flexShrink: 0,
        padding: 0,
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: 1,
          left: checked ? 19 : 1,
          width: 14,
          height: 14,
          borderRadius: 0,
          background: checked ? 'var(--accent)' : 'var(--text-tertiary)',
          transition: 'left 0.2s ease, background 0.2s ease',
          boxShadow: checked ? '0 0 8px rgba(253, 176, 34, 0.4)' : 'none',
        }}
      />
    </button>
  )
}
