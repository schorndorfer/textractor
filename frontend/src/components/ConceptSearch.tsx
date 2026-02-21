import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { TerminologyConcept } from '../types';

interface Props {
  value: TerminologyConcept | null;
  onChange: (concept: TerminologyConcept | null) => void;
  placeholder?: string;
}

export function ConceptSearch({ value, onChange, placeholder = 'Search concepts...' }: Props) {
  const [query, setQuery] = useState(value?.display ?? '');
  const [results, setResults] = useState<TerminologyConcept[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setQuery(value?.display ?? '');
  }, [value]);

  const handleQueryChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const q = e.target.value;
    setQuery(q);
    onChange(null);

    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!q.trim()) {
      setResults([]);
      setIsOpen(false);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      setIsLoading(true);
      try {
        const hits = await api.searchTerminology(q, 20);
        setResults(hits);
        setIsOpen(hits.length > 0);
      } finally {
        setIsLoading(false);
      }
    }, 250);
  };

  const handleSelect = (concept: TerminologyConcept) => {
    onChange(concept);
    setQuery(concept.display);
    setResults([]);
    setIsOpen(false);
  };

  const handleBlur = () => {
    // Delay to allow mouseDown on dropdown item to fire first
    setTimeout(() => setIsOpen(false), 150);
  };

  return (
    <div className="concept-search">
      <div className="concept-search-input-wrap">
        <input
          type="text"
          value={query}
          onChange={handleQueryChange}
          onBlur={handleBlur}
          onFocus={() => results.length > 0 && setIsOpen(true)}
          placeholder={placeholder}
          className={`concept-input${value ? ' has-value' : ''}`}
        />
        {isLoading && <span className="search-spinner" />}
      </div>
      {isOpen && (
        <ul className="concept-dropdown" role="listbox">
          {results.map((c) => (
            <li
              key={`${c.system}:${c.code}`}
              role="option"
              onMouseDown={() => handleSelect(c)}
              className="concept-option"
            >
              <span className="concept-display">{c.display}</span>
              <span className="concept-meta">
                {c.code} · {c.system}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
