/**
 * Application-wide constants and configuration values
 */

// Color palette for document annotations (hue, saturation, lightness)
export const COLOR_PALETTE = [
  { bg: '#e3f2fd', border: '#2196f3' }, // blue
  { bg: '#f3e5f5', border: '#9c27b0' }, // purple
  { bg: '#e8f5e9', border: '#4caf50' }, // green
  { bg: '#fff3e0', border: '#ff9800' }, // orange
  { bg: '#fce4ec', border: '#e91e63' }, // pink
  { bg: '#e0f7fa', border: '#00bcd4' }, // cyan
  { bg: '#fff9c4', border: '#fdd835' }, // yellow
  { bg: '#f1f8e9', border: '#8bc34a' }, // lime
  { bg: '#ede7f6', border: '#673ab7' }, // deep purple
  { bg: '#ffebee', border: '#f44336' }, // red
  { bg: '#e0f2f1', border: '#009688' }, // teal
  { bg: '#fff8e1', border: '#ffc107' }, // amber
];

// Sidebar configuration
export const SIDEBAR = {
  MIN_WIDTH: 200,
  MAX_WIDTH: 600,
  DEFAULT_LEFT_WIDTH: 260,
  DEFAULT_RIGHT_WIDTH: 380,
};

// Font size configuration
export const FONT_SIZE = {
  MIN: 10,
  MAX: 24,
  DEFAULT: 14,
  STORAGE_KEY: 'textractor-font-size',
};

// Auto-save configuration
export const AUTO_SAVE = {
  DEBOUNCE_MS: 3000, // 3 seconds after last change
};

// Search configuration
export const SEARCH = {
  DEBOUNCE_MS: 250, // Terminology search debounce
  DEFAULT_LIMIT: 20, // Default number of search results
};

// UI delays and timeouts
export const UI = {
  BLUR_DELAY_MS: 150, // Delay to allow mouseDown on dropdown before blur
};
