/**
 * Shared utility functions for common patterns across components
 */

/**
 * Toggle an item in a Set and return a new Set.
 * Useful for managing checkbox groups and multi-select state.
 */
export function toggleInSet<T>(item: T, set: Set<T>): Set<T> {
  const next = new Set(set);
  if (next.has(item)) {
    next.delete(item);
  } else {
    next.add(item);
  }
  return next;
}

/**
 * Toggle an item in an array and return a new array.
 * Useful for managing checkbox groups when arrays are preferred over Sets.
 */
export function toggleInArray<T>(item: T, array: T[]): T[] {
  return array.includes(item)
    ? array.filter(x => x !== item)
    : [...array, item];
}

/**
 * Generate a random ID with a given prefix.
 * Used for creating unique IDs for annotations, spans, etc.
 */
export function randomId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Deep clone an object using JSON serialization.
 * Warning: This only works for JSON-serializable objects.
 */
export function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj));
}
