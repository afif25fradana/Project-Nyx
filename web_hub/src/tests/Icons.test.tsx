import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import {
  Mic,
  MicOff,
  Volume,
  VolumeMute,
  Settings,
  Terminal,
  Play,
  Pause,
  RefreshCw,
  AudioWave,
  Check,
  AlertTriangle,
} from '../components/common/Icons';

describe('Handcrafted Industrial SVG Micro-Icons', () => {
  const iconEntries: Array<[string, React.ComponentType<{ className?: string; size?: number | string; 'aria-label'?: string }>]> = [
    ['Mic', Mic],
    ['MicOff', MicOff],
    ['Volume', Volume],
    ['VolumeMute', VolumeMute],
    ['Settings', Settings],
    ['Terminal', Terminal],
    ['Play', Play],
    ['Pause', Pause],
    ['RefreshCw', RefreshCw],
    ['AudioWave', AudioWave],
    ['Check', Check],
    ['AlertTriangle', AlertTriangle],
  ];

  it('exports exactly all 12 required industrial micro-icons', () => {
    expect(iconEntries).toHaveLength(12);
    iconEntries.forEach(([name, Component]) => {
      expect(Component, `Icon ${name} should be a valid component`).toBeDefined();
      expect(typeof Component).toBe('function');
    });
  });

  iconEntries.forEach(([name, IconComponent]) => {
    it(`renders ${name} as a valid SVG with standard attributes`, () => {
      const { container } = render(<IconComponent className="custom-icon" />);
      const svg = container.querySelector('svg');

      expect(svg, `${name} must render an <svg> element`).not.toBeNull();
      expect(svg?.getAttribute('viewBox')).toBeTruthy();
      expect(svg?.classList.contains('custom-icon')).toBe(true);
      expect(svg?.getAttribute('aria-hidden')).toBe('true');
    });
  });

  it('allows overriding dimensions via size property', () => {
    const { container } = render(<Settings size={32} />);
    const svg = container.querySelector('svg');

    expect(svg?.getAttribute('width')).toBe('32');
    expect(svg?.getAttribute('height')).toBe('32');
  });

  it('supports accessible labels by exposing role="img" when aria-label is provided', () => {
    const { container } = render(<MicOff aria-label="Microphone disabled" />);
    const svg = container.querySelector('svg');

    expect(svg?.getAttribute('aria-label')).toBe('Microphone disabled');
    expect(svg?.getAttribute('role')).toBe('img');
    expect(svg?.getAttribute('aria-hidden')).not.toBe('true');
  });
});
