import type { Span } from '../types';

interface Props {
  spans: Span[];
  onChange: (spans: Span[]) => void;
}

export function SpanList({ spans, onChange }: Props) {
  const deleteSpan = (id: string) => onChange(spans.filter((s) => s.id !== id));

  return (
    <ul className="span-list">
      {spans.map((span) => (
        <li key={span.id} className="span-item">
          <span className="span-text">"{span.text}"</span>
          <span className="span-offsets">
            [{span.start}–{span.end}]
          </span>
          <button
            onClick={() => deleteSpan(span.id)}
            className="delete-btn"
            title="Delete span"
          >
            ×
          </button>
        </li>
      ))}
      {spans.length === 0 && (
        <li className="empty-hint">Select text in the document to create spans</li>
      )}
    </ul>
  );
}
