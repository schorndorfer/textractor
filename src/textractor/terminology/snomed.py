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
    
    def _score_match(self, query: str, term: str, fuzzy_score: float) -> float:
        """
        Multi-factor scoring for better relevance ranking.

        Priority order:
        1. Exact match (100 bonus)
        2. Prefix match (80 bonus)
        3. Word boundary match (60 bonus)
        4. Contains match with position bonus (40-20 bonus)
        5. Fuzzy score (base score)
        """
        query_lower = query.lower()
        term_lower = term.lower()

        # Exact match
        if query_lower == term_lower:
            return fuzzy_score + 100

        # Prefix match (term starts with query)
        if term_lower.startswith(query_lower):
            return fuzzy_score + 80

        # Word boundary match (query matches start of a word in term)
        words = term_lower.split()
        for i, word in enumerate(words):
            if word.startswith(query_lower):
                # Earlier words get higher bonus
                position_bonus = 60 - (i * 5)
                return fuzzy_score + max(position_bonus, 30)

        # Contains match with position-based bonus
        if query_lower in term_lower:
            position = term_lower.index(query_lower)
            # Earlier positions get higher bonus (40 at start, 20 at end)
            position_ratio = position / max(len(term_lower), 1)
            position_bonus = 40 - (position_ratio * 20)
            return fuzzy_score + position_bonus

        # Just fuzzy score
        return fuzzy_score

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
            limit=limit * 3  # Get more candidates for re-ranking
        )

        # Step 3: Re-rank with custom scoring
        scored_matches = []
        for term, fuzzy_score, _ in matches:
            custom_score = self._score_match(query_lower, term, fuzzy_score)
            idx = candidates[term]
            desc = self.descriptions[idx]
            scored_matches.append({
                "concept_id": desc.concept_id,
                "term": desc.term,
                "type": desc.term_type,
                "score": round(custom_score, 1),
                "idx": idx
            })

        # Sort by custom score (descending)
        scored_matches.sort(key=lambda x: x["score"], reverse=True)

        # Return top results
        results = []
        for match in scored_matches[:limit]:
            results.append({
                "concept_id": match["concept_id"],
                "term": match["term"],
                "type": match["type"],
                "score": match["score"]
            })
        return results