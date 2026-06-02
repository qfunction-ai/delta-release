interface EncryptedFieldProps {
  label: string
}

/**
 * Displays an encrypted/masked credential field with a lock icon.
 * Used for all credential display fields (API keys, tokens, passwords, etc.)
 */
export function EncryptedField({ label }: EncryptedFieldProps) {
  return (
    <div>
      <span className="text-xs text-tertiary" style={{ fontFamily: 'var(--font-body)' }}>{label}</span>
      <p className="text-sm text-muted" style={{ marginTop: '0.25rem', fontFamily: 'var(--font-body)' }}>
        <span style={{ opacity: 0.5, letterSpacing: '0.1em' }}>••••••••</span>
        <span className="text-xs text-tertiary" style={{ marginLeft: '0.5rem', verticalAlign: 'middle' }}>🔒 encrypted</span>
      </p>
    </div>
  )
}
