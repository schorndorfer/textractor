import type { Span } from '../types';
import type { SpanColorMap } from '../App';

interface Props {
  spans: Span[];
  onChange: (spans: Span[]) => void;
  spanColorMap: SpanColorMap;
}

export function SpanList({ spans, onChange, spanColorMap }: Props) {
  const deleteSpan = (id: string) => onChange(spans.filter((s) => s.id !== id));

  return (
    <ul className="span-list">
      {spans.map((span) => {
        const color = spanColorMap.get(span.id);
        return (
          <li key={span.id} className="span-item">
            {color && (
              <span
                className="color-indicator"
                style={{ backgroundColor: color.border }}
                title="Linked to document annotation"
              />
            )}
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
        );
      })}
      {spans.length === 0 && (
        <li className="empty-hint">Select text in the document to create spans</li>
      )}
    </ul>
  );
}
