import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ErrorBoundary } from '../components/common/ErrorBoundary';

const FaultyChild: React.FC<{ shouldThrow?: boolean }> = ({ shouldThrow = true }) => {
  if (shouldThrow) {
    throw new Error('KernelFault: Memory segment violation at 0xDEADBEEF');
  }
  return <div data-testid="healthy-child">System Operational</div>;
};

describe('ErrorBoundary Component', () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // Suppress expected React error boundary console output in test log
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('renders children transparently when no runtime error occurs', () => {
    render(
      <ErrorBoundary>
        <FaultyChild shouldThrow={false} />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('healthy-child')).toBeDefined();
    expect(screen.getByText('System Operational')).toBeDefined();
  });

  it('catches rendering crash in child component and displays retro panic screen', () => {
    render(
      <ErrorBoundary>
        <FaultyChild shouldThrow={true} />
      </ErrorBoundary>
    );

    // Verifies child crash is caught and fallback panic UI is rendered
    expect(screen.queryByTestId('healthy-child')).toBeNull();
    const heading = screen.getByRole('heading', { level: 2, name: /SYSTEM FAULT|CRITICAL ERROR/i });
    expect(heading).toBeDefined();

    expect(screen.getByText(/KernelFault: Memory segment violation/i)).toBeDefined();
  });

  it('triggers optional onError callback with caught error and errorInfo', () => {
    const onErrorMock = vi.fn();

    render(
      <ErrorBoundary onError={onErrorMock}>
        <FaultyChild shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(onErrorMock).toHaveBeenCalledTimes(1);
    expect(onErrorMock.mock.calls[0][0]).toBeInstanceOf(Error);
    expect(onErrorMock.mock.calls[0][0].message).toContain('KernelFault');
  });

  it('provides recovery action to reset boundary state on user click', () => {
    let throwError = true;
    const DynamicChild = () => {
      if (throwError) {
        throw new Error('Transient hardware lock');
      }
      return <div data-testid="recovered-child">Recovered System</div>;
    };

    const { rerender } = render(
      <ErrorBoundary>
        <DynamicChild />
      </ErrorBoundary>
    );

    expect(screen.getByText(/Transient hardware lock/i)).toBeDefined();

    // Fix problem and click recovery button
    throwError = false;
    const resetButton = screen.getByRole('button', { name: /REBOOT|RESET|RETRY/i });
    fireEvent.click(resetButton);

    rerender(
      <ErrorBoundary>
        <DynamicChild />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('recovered-child')).toBeDefined();
  });
});
