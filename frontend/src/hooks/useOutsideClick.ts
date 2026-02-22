import { useEffect, type RefObject } from 'react';

/**
 * Custom hook to detect clicks outside of specified elements.
 * Useful for closing menus, dialogs, and dropdowns.
 *
 * @param refs - Array of refs to elements that should NOT trigger the callback
 * @param callback - Function to call when clicking outside
 * @param enabled - Whether the hook is active (default: true)
 */
export function useOutsideClick(
  refs: RefObject<HTMLElement | null>[],
  callback: () => void,
  enabled = true
): void {
  useEffect(() => {
    if (!enabled) return;

    const handleClickOutside = (event: MouseEvent) => {
      const clickedOutside = refs.every(
        (ref) => ref.current && !ref.current.contains(event.target as Node)
      );

      if (clickedOutside) {
        callback();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [refs, callback, enabled]);
}
