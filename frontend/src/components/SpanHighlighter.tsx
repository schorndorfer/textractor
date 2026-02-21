import type { Span } from '../types';
import type { SpanColorMap } from '../App';

interface Props {
  text: string;
  spans: Span[];
  colorMap: SpanColorMap;
  focusedSpanId?: string | null;
}

/**
 * Renders document text with <mark> highlights for each span.
 * Handles overlapping spans by tracking nesting depth — any character
 * covered by one or more spans is highlighted with colors from the colorMap.
 */
export function SpanHighlighter({ text, spans, colorMap, focusedSpanId }: Props) {
  if (spans.length === 0) {
    return <>{text}</>;
  }

  type Event = { pos: number; type: 'open' | 'close'; spanId: string };
  const events: Event[] = [];

  for (const span of spans) {
    events.push({ pos: span.start, type: 'open', spanId: span.id });
    events.push({ pos: span.end, type: 'close', spanId: span.id });
  }

  // Sort by position; closes before opens at the same position
  events.sort((a, b) => a.pos - b.pos || (a.type === 'close' ? -1 : 1));

  const parts: React.ReactNode[] = [];
  let pos = 0;
  const activeSpans: string[] = []; // Track which spans are currently active

  for (const event of events) {
    if (event.pos > pos) {
      const segment = text.slice(pos, event.pos);
      if (activeSpans.length > 0) {
        // Use the color of the first active span (topmost in hierarchy)
        const primarySpanId = activeSpans[0];
        const color = colorMap.get(primarySpanId);

        const isFocused = focusedSpanId === primarySpanId;
        parts.push(
          <mark
            key={`mark-${pos}-${event.pos}`}
            className={`span-highlight${isFocused ? ' focused' : ''}`}
            data-span-id={primarySpanId}
            style={
              color
                ? {
                    background: color.bg,
                    borderBottomColor: color.border,
                  }
                : undefined
            }
          >
            {segment}
          </mark>
        );
      } else {
        parts.push(segment);
      }
      pos = event.pos;
    }

    if (event.type === 'open') {
      activeSpans.push(event.spanId);
    } else {
      const idx = activeSpans.indexOf(event.spanId);
      if (idx !== -1) {
        activeSpans.splice(idx, 1);
      }
    }
  }

  if (pos < text.length) {
    parts.push(text.slice(pos));
  }

  return <>{parts}</>;
}
