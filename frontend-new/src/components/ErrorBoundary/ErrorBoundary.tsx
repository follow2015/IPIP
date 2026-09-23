/**
 * 错误边界组件
 * - 捕获子组件渲染异常，展示友好错误页面
 */
import React from 'react';
import { useTranslation } from 'react-i18next';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ComponentType<{ error: Error; reset: () => void }>;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

type FallbackTextKey = 'error.title' | 'action.retry';

function FallbackText({ k }: { k: FallbackTextKey }) {
  const { t } = useTranslation();
  return <>{t(k)}</>;
}

export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  reset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError && this.state.error) {
      if (this.props.fallback) {
        const Fallback = this.props.fallback;
        return <Fallback error={this.state.error} reset={this.reset} />;
      }
      return (
        <div style={{ textAlign: 'center', padding: '100px 0' }}>
          <h2>
            <FallbackText k="error.title" />
          </h2>
          <p>{this.state.error.message}</p>
          <button onClick={this.reset}>
            <FallbackText k="action.retry" />
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
