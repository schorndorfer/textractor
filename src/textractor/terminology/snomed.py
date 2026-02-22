import rapidfuzz
from rapidfuzz import process, fuzz
from dataclasses import dataclass
import csv
from pathlib import Path

@dataclass
class SNOMEDDescription:
    description_id: int
    concept_id: int
    term: str
    term_type: str  # FSN or SYNONYM

class SNOMEDSearch:
    def __init__(self):
        self.descriptions: list[SNOMEDDescription] = []
        self._term_list: list[str] = []  # parallel list for rapidfuzz
        self._word_index: dict[str, set[int]] = {}  # inverted index
    
    def load(self, rf2_dir: str):
        """Load from SNOMED RF2 sct2_Description file."""
        desc_files = list(Path(rf2_dir).glob("**/sct2_Description_Full-en*.txt"))
        if not desc_files:
            desc_files = list(Path(rf2_dir).glob("**/sct2_Description_Snapshot-en*.txt"))
        
        for desc_file in desc_files:
            with open(desc_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    if row["active"] == "1":
                        desc = SNOMEDDescription(
                            description_id=int(row["id"]),
                            concept_id=int(row["conceptId"]),
                            term=row["term"],
                            term_type="FSN" if row["typeId"] == "900000000000003001" else "SYNONYM"
                        )
                        idx = len(self.descriptions)
                        self.descriptions.append(desc)
                        self._term_list.append(desc.term.lower())
                        
                        # Build word-level inverted index for pre-filtering
                        for word in desc.term.lower().split():
                            if len(word) >= 3:
                                if word not in self._word_index:
                                    self._word_index[word] = set()
                                self._word_index[word].add(idx)
        
        print(f"Loaded {len(self.descriptions)} active descriptions")
    
    def search(self, query: str, limit: int = 20) -> list[dict]:
        query_lower = query.lower()
        query_words = [w for w in query_lower.split() if len(w) >= 3]
        
        # Step 1: Pre-filter using inverted index (narrows 800K → hundreds)
        if query_words:
            # Find candidates that match ANY query word (prefix match on index)
            candidate_ids = set()
            for qw in query_words:
                for indexed_word, ids in self._word_index.items():
                    if indexed_word.startswith(qw):
                        candidate_ids.update(ids)
            
            if not candidate_ids:
                # Fall back to full fuzzy search on smaller sample
                candidate_ids = set(range(min(50000, len(self.descriptions))))
            
            candidates = {self._term_list[i]: i for i in candidate_ids}
        else:
            # Very short query — just prefix match
            candidates = {t: i for i, t in enumerate(self._term_list) if t.startswith(query_lower)}
        
        if not candidates:
            return []
        
        # Step 2: Rank with rapidfuzz
        matches = process.extract(
            query_lower,
            candidates.keys(),
            scorer=fuzz.WRatio,
            limit=limit
        )
        
        results = []
        for term, score, _ in matches:
            idx = candidates[term]
            desc = self.descriptions[idx]
            results.append({
                "concept_id": desc.concept_id,
                "term": desc.term,
                "type": desc.term_type,
                "score": round(score, 1)
            })
        return results