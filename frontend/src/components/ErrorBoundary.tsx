import { Component, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
  resetKey: number
}

/**
 * Catches render errors in child components and shows a fallback UI
 * instead of crashing the entire app to a white screen.
 */
export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null, resetKey: 0 }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, resetKey: 0 }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack)
  }

  handleReload = () => {
    this.setState(prev => ({ hasError: false, error: null, resetKey: prev.resetKey + 1 }))
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
          padding: '2rem',
        }}>
          <div className="card" style={{ maxWidth: '480px', width: '100%' }}>
            <h2 style={{ marginTop: 0, marginBottom: '1rem' }}>Something went wrong</h2>
            <p className="text-sm text-muted" style={{ marginBottom: '1rem' }}>
              An unexpected error occurred. This has been logged to the console.
            </p>
            <details style={{ marginBottom: '1.5rem' }}>
              <summary className="text-sm" style={{ cursor: 'pointer', marginBottom: '0.5rem' }}>
                Error details
              </summary>
              <pre style={{
                fontSize: '0.75rem',
                overflow: 'auto',
                maxHeight: '200px',
                padding: '0.75rem',
                background: 'var(--bg-secondary, #f5f5f5)',
                borderRadius: 'var(--radius-sm, 0)',
                margin: 0,
              }}>
                {this.state.error?.message}
              </pre>
            </details>
            <button className="btn btn-primary" onClick={this.handleReload}>
              Reload
            </button>
          </div>
        </div>
      )
    }

    return <div key={this.state.resetKey}>{this.props.children}</div>
  }
}
