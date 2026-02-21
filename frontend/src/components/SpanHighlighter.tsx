import type { Span } from '../types';

interface Props {
  text: string;
  spans: Span[];
}

/**
 * Renders document text with <mark> highlights for each span.
 * Handles overlapping spans by tracking nesting depth — any character
 * covered by one or more spans is highlighted.
 */
export function SpanHighlighter({ text, spans }: Props) {
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
  let depth = 0;

  for (const event of events) {
    if (event.pos > pos) {
      const segment = text.slice(pos, event.pos);
      if (depth > 0) {
        parts.push(
          <mark key={`mark-${pos}-${event.pos}`} className="span-highlight">
            {segment}
          </mark>
        );
      } else {
        parts.push(segment);
      }
      pos = event.pos;
    }

    if (event.type === 'open') {
      depth++;
    } else {
      depth = Math.max(0, depth - 1);
    }
  }

  if (pos < text.length) {
    parts.push(text.slice(pos));
  }

  return <>{parts}</>;
}
