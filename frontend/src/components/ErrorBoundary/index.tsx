'use client';

/**
 * ErrorBoundary Component
 * Catches JavaScript errors in child component tree and displays fallback UI
 */

import React, { Component, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export interface ErrorBoundaryProps {
  /** Child components to wrap */
  children: ReactNode;
  /** Optional custom fallback UI */
  fallback?: ReactNode;
  /** Callback when error is caught */
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * ErrorBoundary catches JavaScript errors anywhere in the child component tree,
 * logs those errors, and displays a fallback UI instead of the crashed component tree.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.props.onError?.(error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100vh',
            padding: '20px',
            textAlign: 'center',
            backgroundColor: '#fafafa',
          }}
          role="alert"
          aria-live="assertive"
        >
          <AlertTriangle size={64} color="#ff4d4f" aria-hidden="true" />
          <h1
            style={{
              marginTop: '20px',
              fontSize: '24px',
              fontWeight: 600,
              color: '#262626',
            }}
          >
            Something went wrong
          </h1>
          <p
            style={{
              color: '#666',
              maxWidth: '500px',
              marginTop: '10px',
              lineHeight: 1.6,
            }}
          >
            We encountered an unexpected error. Please try refreshing the page.
            If the problem persists, please contact support.
          </p>
          <button
            onClick={this.handleReset}
            style={{
              marginTop: '24px',
              padding: '12px 24px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              border: 'none',
              borderRadius: '3px',
              background: '#ff6b81',
              color: 'white',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: 500,
              transition: 'background 0.2s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = '#40a9ff';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.background = '#ff6b81';
            }}
            aria-label="重新載入應用程式"
          >
            <RefreshCw size={16} aria-hidden="true" />
            Reload Application
          </button>
          {process.env.NODE_ENV === 'development' && this.state.error && (
            <details
              style={{
                marginTop: '24px',
                padding: '16px',
                background: '#fff1f0',
                borderRadius: '8px',
                maxWidth: '600px',
                width: '100%',
                textAlign: 'left',
                border: '1px solid #ffa39e',
              }}
            >
              <summary
                style={{
                  cursor: 'pointer',
                  fontWeight: 500,
                  color: '#cf1322',
                }}
              >
                Error Details (Development Only)
              </summary>
              <pre
                style={{
                  marginTop: '12px',
                  padding: '12px',
                  background: '#fff',
                  borderRadius: '4px',
                  overflow: 'auto',
                  fontSize: '12px',
                  lineHeight: 1.5,
                }}
              >
                {this.state.error.toString()}
                {'\n\n'}
                {this.state.error.stack}
              </pre>
            </details>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
