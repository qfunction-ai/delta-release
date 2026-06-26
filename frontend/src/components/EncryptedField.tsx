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
      <span className="text-xs text-tertiary font-sans">{label}</span>
      <p className="text-sm text-muted font-sans" style={{ marginTop: '0.25rem' }}>
        <span style={{ opacity: 0.5, letterSpacing: '0.1em' }}>••••••••</span>
        <span className="text-xs text-tertiary" style={{ marginLeft: '0.5rem', verticalAlign: 'middle' }}>🔒 encrypted</span>
      </p>
    </div>
  )
}
