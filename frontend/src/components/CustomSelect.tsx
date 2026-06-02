import { useState, useRef, useEffect } from 'react'

interface Option {
  value: string
  label: string
}

interface CustomSelectProps {
  id?: string
  value: string
  onChange: (value: string) => void
  options: Option[]
  placeholder?: string
  disabled?: boolean
  'aria-label'?: string
}

export default function CustomSelect({
  id,
  value,
  onChange,
  options,
  placeholder = 'Select...',
  disabled = false,
  'aria-label': ariaLabel,
}: CustomSelectProps) {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const containerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  const selectedOption = options.find(opt => opt.value === value)

  // Compute the ID for the active descendant option
  const optionId = (index: number) => `${id || 'custom-select'}-option-${index}`
  const activeDescendant = activeIndex >= 0 ? optionId(activeIndex) : undefined

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        setActiveIndex(-1)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSelect = (optValue: string) => {
    onChange(optValue)
    setOpen(false)
    setActiveIndex(-1)
  }

  const handleTriggerKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        if (!open) {
          setOpen(true)
          setActiveIndex(0)
        } else {
          setActiveIndex(prev => prev < options.length - 1 ? prev + 1 : 0)
        }
        break
      case 'ArrowUp':
        e.preventDefault()
        if (!open) {
          setOpen(true)
          setActiveIndex(options.length - 1)
        } else {
          setActiveIndex(prev => prev > 0 ? prev - 1 : options.length - 1)
        }
        break
      case 'Enter':
      case ' ':
        e.preventDefault()
        if (open && activeIndex >= 0) {
          handleSelect(options[activeIndex].value)
        } else {
          setOpen(!open)
          if (!open) setActiveIndex(0)
        }
        break
      case 'Escape':
        e.preventDefault()
        setOpen(false)
        setActiveIndex(-1)
        break
      case 'Home':
        if (open) {
          e.preventDefault()
          setActiveIndex(0)
        }
        break
      case 'End':
        if (open) {
          e.preventDefault()
          setActiveIndex(options.length - 1)
        }
        break
    }
  }

  return (
    <div
      ref={containerRef}
      id={id}
      className={`custom-select ${open ? 'custom-select-open' : ''} ${disabled ? 'custom-select-disabled' : ''}`}
    >
      <button
        ref={triggerRef}
        type="button"
        className="custom-select-trigger"
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        aria-controls={id ? `${id}-listbox` : 'custom-select-listbox'}
        aria-activedescendant={activeDescendant}
        onKeyDown={handleTriggerKeyDown}
      >
        <span className="custom-select-value">
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <span className="custom-select-arrow">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M6 8L1 3h10z" />
          </svg>
        </span>
      </button>
      {/* role="listbox" kept: native <datalist> does not support custom dropdown styling and keyboard navigation */}
      {open && (
        <div className="custom-select-dropdown" role="listbox" id={id ? `${id}-listbox` : 'custom-select-listbox'}>
          {/* role="option" kept: native <option> cannot be used inside a custom dropdown with custom styling */}
          {options.map((opt, index) => (
            <button
              key={opt.value}
              id={optionId(index)}
              type="button"
              className={`custom-select-option ${opt.value === value ? 'custom-select-option-selected' : ''} ${index === activeIndex ? 'custom-select-option-active' : ''}`}
              onClick={() => handleSelect(opt.value)}
              role="option"
              aria-selected={opt.value === value}
              onMouseEnter={() => setActiveIndex(index)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
