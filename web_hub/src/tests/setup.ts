import { expect, afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import * as matchers from 'vitest-axe/matchers';
import axe from 'axe-core';

expect.extend(matchers);

// Disable asset preloader in headless JSDOM to prevent 10s video/font preload timeouts
const originalAxeRun = axe.run.bind(axe);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
axe.run = ((context: any, options: any, callback?: any) => {
  if (typeof options === 'function') {
    callback = options;
    options = {};
  }
  const mergedOptions = { ...options, preload: false };
  return originalAxeRun(context, mergedOptions, callback);
}) as unknown as typeof axe.run;

// Stub HTMLMediaElement playback controls
HTMLMediaElement.prototype.play = vi.fn().mockImplementation(() => Promise.resolve());
HTMLMediaElement.prototype.pause = vi.fn();
HTMLMediaElement.prototype.load = vi.fn();

// Stub HTMLVideoElement requestVideoFrameCallback and cancelVideoFrameCallback
if (typeof HTMLVideoElement !== 'undefined') {
  HTMLVideoElement.prototype.requestVideoFrameCallback = vi.fn().mockImplementation(
    (cb: (now: number, metadata: Record<string, unknown>) => void) => {
      return window.setTimeout(() => {
        cb(performance.now(), {
          presentationTime: performance.now(),
          expectedDisplayTime: performance.now() + 16,
          width: 1920,
          height: 1080,
          mediaTime: 0,
          presentedFrames: 1,
        });
      }, 0);
    }
  );

  HTMLVideoElement.prototype.cancelVideoFrameCallback = vi.fn().mockImplementation((handle: number) => {
    clearTimeout(handle);
  });
}

// Stub HTMLCanvasElement 2D context to silence jsdom axe-core warnings
if (typeof HTMLCanvasElement !== 'undefined') {
  HTMLCanvasElement.prototype.getContext = ((contextId: string) => {
    if (contextId === '2d') {
      return {
        fillRect: () => {},
        clearRect: () => {},
        getImageData: () => ({ data: new Uint8ClampedArray(4) }),
        putImageData: () => {},
        createImageData: () => ({ data: new Uint8ClampedArray(4) }),
        setTransform: () => {},
        drawImage: () => {},
        save: () => {},
        fillText: () => {},
        restore: () => {},
        beginPath: () => {},
        moveTo: () => {},
        lineTo: () => {},
        closePath: () => {},
        stroke: () => {},
        translate: () => {},
        scale: () => {},
        rotate: () => {},
        arc: () => {},
        fill: () => {},
        measureText: (text: string) => ({ width: text.length * 10, height: 10 }),
        transform: () => {},
        rect: () => {},
        clip: () => {},
      } as unknown as RenderingContext;
    }
    return null;
  }) as unknown as typeof HTMLCanvasElement.prototype.getContext;
}

// Stub window.matchMedia for media query and reduced-motion evaluation
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

afterEach(() => {
  cleanup();
});
