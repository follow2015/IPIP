/**
 * 错误边界组件
 * - 捕获子组件渲染异常，展示友好错误页面
 */
import React from 'react';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ComponentType<{ error: Error; reset: () => void }>;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
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
          <h2>页面出现错误</h2>
          <p>{this.state.error.message}</p>
          <button onClick={this.reset}>重试</button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
