import { describe, it, expect } from 'vitest';
import { cn } from '../utils/cn';

describe('cn utility', () => {
  it('concatenates static class strings with single whitespace', () => {
    expect(cn('flex', 'items-center', 'justify-between')).toBe('flex items-center justify-between');
  });

  it('filters out falsy, empty, and nullish inputs cleanly', () => {
    expect(cn('card', false, null, undefined, '', 0, 'card-hover')).toBe('card card-hover');
  });

  it('evaluates conditional class records based on truthiness', () => {
    expect(
      cn('badge', {
        'badge-active': true,
        'badge-inactive': false,
        'badge-pending': null,
      })
    ).toBe('badge badge-active');
  });

  it('flattens nested arrays and handles mixed arguments', () => {
    expect(
      cn(
        'font-mono',
        ['text-sm', ['uppercase', false]],
        { 'tracking-wider': true },
        undefined
      )
    ).toBe('font-mono text-sm uppercase tracking-wider');
  });

  it('returns an empty string when invoked with zero arguments or exclusively falsy values', () => {
    expect(cn()).toBe('');
    expect(cn(false, null, undefined, '')).toBe('');
  });
});
