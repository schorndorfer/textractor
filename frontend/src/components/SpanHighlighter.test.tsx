import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SpanHighlighter } from './SpanHighlighter';
import type { Span } from '../types';
import type { SpanColorMap } from '../App';

describe('SpanHighlighter', () => {
  const colorMap: SpanColorMap = new Map([
    ['span1', { bg: '#ffeb3b', border: '#fdd835' }],
    ['span2', { bg: '#4caf50', border: '#43a047' }],
    ['span3', { bg: '#2196f3', border: '#1e88e5' }],
  ]);

  describe('Basic Rendering', () => {
    it('should render plain text when no spans provided', () => {
      const { container } = render(
        <SpanHighlighter text="Plain text" spans={[]} colorMap={colorMap} />
      );
      expect(container.textContent).toBe('Plain text');
      expect(container.querySelector('mark')).toBeNull();
    });

    it('should render single span with highlight', () => {
      const spans: Span[] = [
        { id: 'span1', start: 0, end: 5, text: 'chest', source: 'human' },
      ];

      render(<SpanHighlighter text="chest pain" spans={spans} colorMap={colorMap} />);

      const mark = screen.getByText('chest').closest('mark');
      expect(mark).toBeInTheDocument();
      expect(mark).toHaveAttribute('data-span-id', 'span1');
      expect(mark).toHaveStyle({
        background: '#ffeb3b',
        borderBottomColor: '#fdd835',
      });
    });

    it('should render multiple non-overlapping spans', () => {
      const text = 'chest pain and fever';
      const spans: Span[] = [
        { id: 'span1', start: 0, end: 5, text: 'chest', source: 'human' },
        { id: 'span2', start: 15, end: 20, text: 'fever', source: 'human' },
      ];

      const { container } = render(
        <SpanHighlighter text={text} spans={spans} colorMap={colorMap} />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks).toHaveLength(2);

      expect(marks[0]).toHaveAttribute('data-span-id', 'span1');
      expect(marks[0].textContent).toBe('chest');

      expect(marks[1]).toHaveAttribute('data-span-id', 'span2');
      expect(marks[1].textContent).toBe('fever');
    });
  });

  describe('Overlapping Spans', () => {
    it('should handle overlapping spans using first span color', () => {
      const text = 'chest pain';
      const spans: Span[] = [
        { id: 'span1', start: 0, end: 10, text: 'chest pain', source: 'human' },
        { id: 'span2', start: 0, end: 5, text: 'chest', source: 'human' },
      ];

      const { container } = render(
        <SpanHighlighter text={text} spans={spans} colorMap={colorMap} />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks.length).toBeGreaterThan(0);

      // First mark should use span1's color (first active span)
      const firstMark = marks[0];
      expect(firstMark).toHaveStyle({ background: '#ffeb3b' });
    });

    it('should handle partially overlapping spans', () => {
      const text = 'chest pain syndrome';
      const spans: Span[] = [
        { id: 'span1', start: 0, end: 10, text: 'chest pain', source: 'human' },
        { id: 'span2', start: 6, end: 19, text: 'pain syndrome', source: 'human' },
      ];

      const { container } = render(
        <SpanHighlighter text={text} spans={spans} colorMap={colorMap} />
      );

      expect(container.textContent).toBe(text);

      const marks = container.querySelectorAll('mark');
      expect(marks.length).toBeGreaterThan(0);
    });

    it('should handle nested spans', () => {
      const text = 'severe chest pain';
      const spans: Span[] = [
        { id: 'span1', start: 0, end: 17, text: 'severe chest pain', source: 'human' },
        { id: 'span2', start: 7, end: 17, text: 'chest pain', source: 'human' },
        { id: 'span3', start: 13, end: 17, text: 'pain', source: 'human' },
      ];

      const { container } = render(
        <SpanHighlighter text={text} spans={spans} colorMap={colorMap} />
      );

      expect(container.textContent).toBe(text);
    });
  });

  describe('Focus Highlighting', () => {
    it('should add focused class to focused span', () => {
      const spans: Span[] = [
        { id: 'span1', start: 0, end: 5, text: 'chest', source: 'human' },
        { id: 'span2', start: 6, end: 10, text: 'pain', source: 'human' },
      ];

      const { container } = render(
        <SpanHighlighter
          text="chest pain"
          spans={spans}
          colorMap={colorMap}
          focusedSpanId="span1"
        />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks[0]).toHaveClass('span-highlight', 'focused');
      expect(marks[1]).toHaveClass('span-highlight');
      expect(marks[1]).not.toHaveClass('focused');
    });

    it('should not add focused class when no span is focused', () => {
      const spans: Span[] = [
        { id: 'span1', start: 0, end: 5, text: 'chest', source: 'human' },
      ];

      const { container } = render(
        <SpanHighlighter text="chest pain" spans={spans} colorMap={colorMap} />
      );

      const mark = container.querySelector('mark');
      expect(mark).toHaveClass('span-highlight');
      expect(mark).not.toHaveClass('focused');
    });
  });

  describe('Color Mapping', () => {
    it('should use color from colorMap if available', () => {
      const spans: Span[] = [
        { id: 'span1', start: 0, end: 5, text: 'chest', source: 'human' },
      ];

      const { container } = render(
        <SpanHighlighter text="chest pain" spans={spans} colorMap={colorMap} />
      );

      const mark = container.querySelector('mark');
      expect(mark).toHaveStyle({
        background: '#ffeb3b',
        borderBottomColor: '#fdd835',
      });
    });

    it('should render without inline style if span not in colorMap', () => {
      const spans: Span[] = [
        { id: 'unknown_span', start: 0, end: 5, text: 'chest', source: 'human' },
      ];

      const { container } = render(
        <SpanHighlighter text="chest pain" spans={spans} colorMap={colorMap} />
      );

      const mark = container.querySelector('mark');
      expect(mark).toBeInTheDocument();
      expect(mark).toHaveAttribute('data-span-id', 'unknown_span');
      // Should not have inline styles when color not found
      expect(mark).not.toHaveStyle({ background: expect.any(String) });
    });
  });

  describe('Edge Cases', () => {
    it('should handle empty text', () => {
      const { container } = render(
        <SpanHighlighter text="" spans={[]} colorMap={colorMap} />
      );
      expect(container.textContent).toBe('');
    });

    it('should handle span at start of text', () => {
      const spans: Span[] = [
        { id: 'span1', start: 0, end: 5, text: 'chest', source: 'human' },
      ];

      const { container } = render(
        <SpanHighlighter text="chest" spans={spans} colorMap={colorMap} />
      );

      expect(container.querySelector('mark')).toBeInTheDocument();
      expect(container.textContent).toBe('chest');
    });

    it('should handle span at end of text', () => {
      const text = 'patient has pain';
      const spans: Span[] = [
        { id: 'span1', start: 12, end: 16, text: 'pain', source: 'human' },
      ];

      const { container } = render(
        <SpanHighlighter text={text} spans={spans} colorMap={colorMap} />
      );

      expect(container.textContent).toBe(text);
      const mark = screen.getByText('pain').closest('mark');
      expect(mark).toBeInTheDocument();
    });

    it('should handle adjacent spans', () => {
      const text = 'chestpain';
      const spans: Span[] = [
        { id: 'span1', start: 0, end: 5, text: 'chest', source: 'human' },
        { id: 'span2', start: 5, end: 9, text: 'pain', source: 'human' },
      ];

      const { container } = render(
        <SpanHighlighter text={text} spans={spans} colorMap={colorMap} />
      );

      const marks = container.querySelectorAll('mark');
      expect(marks).toHaveLength(2);
      expect(container.textContent).toBe(text);
    });
  });
});
