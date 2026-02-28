import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { TerminologyConcept } from '../types';
import { SEARCH, UI } from '../constants';
import { useDebounce } from '../hooks/useDebounce';

interface Props {
  value: TerminologyConcept | null;
  onChange: (concept: TerminologyConcept | null) => void;
  placeholder?: string;
  system?: string;
}

export function ConceptSearch({ value, onChange, placeholder = 'Search concepts...', system }: Props) {
  const [query, setQuery] = useState(value?.display ?? '');
  const [results, setResults] = useState<TerminologyConcept[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    setQuery(value?.display ?? '');
  }, [value]);

  const performSearch = useDebounce(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      setIsOpen(false);
      return;
    }

    setIsLoading(true);
    try {
      const hits = await api.searchTerminology(q, SEARCH.DEFAULT_LIMIT, system);
      setResults(hits);
      setIsOpen(hits.length > 0);
    } finally {
      setIsLoading(false);
    }
  }, SEARCH.DEBOUNCE_MS);

  const handleQueryChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const q = e.target.value;
    setQuery(q);
    onChange(null);
    performSearch(q);
  };

  const handleSelect = (concept: TerminologyConcept) => {
    onChange(concept);
    setQuery(concept.display);
    setResults([]);
    setIsOpen(false);
  };

  const handleBlur = () => {
    // Delay to allow mouseDown on dropdown item to fire first
    setTimeout(() => setIsOpen(false), UI.BLUR_DELAY_MS);
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
