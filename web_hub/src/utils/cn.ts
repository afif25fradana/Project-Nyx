import { clsx, type ClassValue } from 'clsx';

/**
 * Lightweight classname concatenation utility backed by clsx.
 * Filters falsy, empty, and nullish inputs, evaluates conditional objects,
 * and flattens nested arrays.
 */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
