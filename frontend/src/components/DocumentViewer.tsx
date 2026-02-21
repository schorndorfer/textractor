import { useRef } from 'react';
import type { Document, Span } from '../types';
import { SpanHighlighter } from './SpanHighlighter';

function randomId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Walk DOM tree depth-first to compute character offset of (targetNode, targetOffset)
 * relative to the start of container's text content.
 * Works correctly even when SpanHighlighter has inserted <mark> elements.
 */
function getCharOffset(container: HTMLElement, targetNode: Node, targetOffset: number): number {
  let charCount = 0;

  function walk(node: Node): boolean {
    if (node === targetNode) {
      charCount += targetOffset;
      return true;
    }
    if (node.nodeType === Node.TEXT_NODE) {
      charCount += node.textContent?.length ?? 0;
      return false;
    }
    for (const child of Array.from(node.childNodes)) {
      if (walk(child)) return true;
    }
    return false;
  }

  walk(container);
  return charCount;
}

interface Props {
  doc: Document;
  spans: Span[];
  onSpanCreated: (span: Span) => void;
}

export function DocumentViewer({ doc, spans, onSpanCreated }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseUp = () => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !containerRef.current) return;

    const range = selection.getRangeAt(0);
    if (!containerRef.current.contains(range.commonAncestorContainer)) return;

    const start = getCharOffset(containerRef.current, range.startContainer, range.startOffset);
    const end = getCharOffset(containerRef.current, range.endContainer, range.endOffset);

    if (start >= end) return;

    const selectedText = doc.text.slice(start, end);
    if (!selectedText.trim()) return;

    onSpanCreated({ id: randomId('span'), start, end, text: selectedText });
    selection.removeAllRanges();
  };

  return (
    <main className="doc-viewer">
      <div className="doc-viewer-header">
        <h2 className="doc-id">{doc.id}</h2>
        {Object.keys(doc.metadata).length > 0 && (
          <div className="doc-meta">
            {Object.entries(doc.metadata).map(([k, v]) => (
              <span key={k} className="meta-tag">
                <strong>{k}:</strong> {String(v)}
              </span>
            ))}
          </div>
        )}
      </div>
      <div
        ref={containerRef}
        onMouseUp={handleMouseUp}
        onDragStart={(e) => e.preventDefault()}
        className="doc-text"
      >
        <SpanHighlighter text={doc.text} spans={spans} />
      </div>
    </main>
  );
}
