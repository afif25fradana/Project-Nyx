import { Component, type ErrorInfo, type ReactNode } from 'react';

export interface ErrorBoundaryProps {
  children: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

/**
 * Retro PS1 Hardware / CRT System Fault Panic Screen.
 * Catches render errors, reports to optional telemetry callback,
 * and exposes recovery controls with accessible focus.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, State> {
  public override state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  public override componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ errorInfo });
    this.props.onError?.(error, errorInfo);
    console.error('[Nyx Fault] Subsystem exception caught by ErrorBoundary:', error, errorInfo);
  }

  public handleReset = (): void => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  public override render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          role="alert"
          aria-live="assertive"
          className="min-h-screen bg-chassis-950 text-ink-primary flex items-center justify-center p-6 select-none"
        >
          <div className="w-full max-w-xl bg-panel-800 border-2 border-red-500/80 rounded-none p-6 shadow-2xl font-mono">
            <div className="flex items-center justify-between border-b border-red-500/40 pb-3 mb-4">
              <h2 className="text-red-400 font-bold tracking-wider uppercase text-sm">
                SYSTEM FAULT: UI KERNEL PANIC
              </h2>
              <span className="text-xs text-ink-secondary" aria-label="Fault timestamp">
                {new Date().toISOString()}
              </span>
            </div>
            <p className="text-sm text-ink-secondary mb-4">
              An unhandled hardware exception interrupted the Web Hub runtime.
            </p>
            <div className="bg-panel-recessed p-3 border border-panel-border text-xs text-red-300 overflow-x-auto mb-6 focus-visible:outline-2 focus-visible:outline-red-500">
              <strong>{this.state.error?.name || 'Error'}: </strong>
              <span>{this.state.error?.message || 'Unknown fault'}</span>
            </div>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={this.handleReset}
                className="px-4 py-2 bg-panel-700 hover:bg-panel-750 text-ink-primary text-xs uppercase tracking-wider font-semibold border border-panel-border cursor-pointer focus-visible:outline-2 focus-visible:outline-amber-400 active:translate-y-[1px]"
              >
                RETRY SUBSYSTEM
              </button>
              <button
                type="button"
                onClick={() => {
                  if (typeof window !== 'undefined' && window.location) {
                    window.location.reload();
                  }
                }}
                className="px-4 py-2 bg-amber-glow hover:bg-amber-muted text-chassis-950 text-xs uppercase tracking-wider font-bold border border-amber-600 cursor-pointer focus-visible:outline-2 focus-visible:outline-amber-400 active:translate-y-[1px]"
              >
                HARD RELOAD
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
