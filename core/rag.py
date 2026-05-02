"""
OmniDiag AI — RAG (Retrieval-Augmented Generation) Module

Enriches diagnostic context with knowledge from the local knowledge base,
including error code references, known issue patterns, and remediation templates.
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KnowledgeEntry:
    """A single retrieved knowledge base entry."""
    entry_id: str
    source_file: str
    content: dict
    relevance_score: float = 0.0
    match_type: str = "keyword"


class RAGPipeline:
    """
    Local Retrieval-Augmented Generation pipeline for OmniDiag AI.

    Instead of a vector database, uses fast keyword and pattern matching
    against JSON knowledge base files to find relevant context.
    This keeps the system fully offline-capable with zero dependencies
    on external embedding services.

    Knowledge base files:
    - knowledge/bugcheck_codes.json — Windows BSOD stop codes
    - knowledge/whea_codes.json    — Hardware error architecture codes
    - knowledge/known_issues.json  — Historical incident patterns & fixes
    """

    def __init__(self, knowledge_dir: Path):
        self.knowledge_dir = knowledge_dir
        self._cache: dict[str, dict] = {}
        self._load_knowledge_base()

    def _load_knowledge_base(self) -> None:
        """Load all JSON knowledge files into memory cache."""
        if not self.knowledge_dir.exists():
            return

        for kb_file in self.knowledge_dir.glob("*.json"):
            try:
                with open(kb_file, "r", encoding="utf-8") as f:
                    self._cache[kb_file.stem] = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass  # Silently skip malformed files

    def retrieve(self, query_text: str, max_entries: int = 10) -> list[KnowledgeEntry]:
        """
        Retrieve relevant knowledge entries for a given diagnostic context.

        Uses a three-pass retrieval strategy:
        1. Exact hex code matching (e.g., 0x00000124)
        2. Keyword matching against entry names/descriptions
        3. Pattern-based heuristics (e.g., driver names, error categories)

        Args:
            query_text: Raw probe output or normalized diagnostic context
            max_entries: Maximum number of entries to return

        Returns:
            List of KnowledgeEntry ranked by relevance score
        """
        results: list[KnowledgeEntry] = []

        # Pass 1: Extract and match hex error codes
        hex_codes = re.findall(r"0x[0-9A-Fa-f]{4,8}", query_text)
        for code in set(code.upper() for code in hex_codes):
            entry = self._lookup_bugcheck(code)
            if entry:
                results.append(entry)
            entry = self._lookup_whea(code)
            if entry:
                results.append(entry)

        # Pass 2: Keyword matching for known issues
        known_issues = self._cache.get("known_issues", {})
        patterns = known_issues.get("patterns", [])
        for pattern_entry in patterns:
            keywords = pattern_entry.get("triggers", [])
            score = self._keyword_score(query_text, keywords)
            if score > 0:
                results.append(KnowledgeEntry(
                    entry_id=pattern_entry.get("id", "unknown"),
                    source_file="known_issues",
                    content=pattern_entry,
                    relevance_score=score,
                    match_type="pattern",
                ))

        # Deduplicate and sort by relevance
        seen = set()
        unique_results = []
        for r in sorted(results, key=lambda x: x.relevance_score, reverse=True):
            if r.entry_id not in seen:
                seen.add(r.entry_id)
                unique_results.append(r)

        return unique_results[:max_entries]

    def format_context(self, entries: list[KnowledgeEntry]) -> str:
        """
        Format retrieved entries into an LLM-ready context string.

        Args:
            entries: List of retrieved knowledge entries

        Returns:
            Formatted string ready for injection into LLM prompt
        """
        if not entries:
            return ""

        parts = ["### Retrieved Knowledge Base Context\n"]
        for entry in entries:
            parts.append(f"**[{entry.source_file.upper()} / {entry.entry_id}]** "
                        f"(relevance: {entry.relevance_score:.2f}, match: {entry.match_type})")
            parts.append(json.dumps(entry.content, indent=2, ensure_ascii=False))
            parts.append("")

        return "\n".join(parts)

    def _lookup_bugcheck(self, hex_code: str) -> Optional[KnowledgeEntry]:
        """Look up a BugCheck stop code in the knowledge base."""
        bugcheck_db = self._cache.get("bugcheck_codes", {})
        codes = bugcheck_db.get("bugcheck_codes", {})
        if hex_code in codes:
            return KnowledgeEntry(
                entry_id=hex_code,
                source_file="bugcheck_codes",
                content={hex_code: codes[hex_code]},
                relevance_score=1.0,
                match_type="exact_hex",
            )
        return None

    def _lookup_whea(self, hex_code: str) -> Optional[KnowledgeEntry]:
        """Look up a WHEA hardware error code."""
        whea_db = self._cache.get("whea_codes", {})
        codes = whea_db.get("error_codes", {})
        if hex_code in codes:
            return KnowledgeEntry(
                entry_id=hex_code,
                source_file="whea_codes",
                content={hex_code: codes[hex_code]},
                relevance_score=1.0,
                match_type="exact_hex",
            )
        return None

    def _keyword_score(self, text: str, keywords: list[str]) -> float:
        """Calculate keyword relevance score (0.0 to 1.0)."""
        if not keywords:
            return 0.0
        text_lower = text.lower()
        matches = sum(1 for kw in keywords if kw.lower() in text_lower)
        return matches / len(keywords)

    def get_stats(self) -> dict:
        """Return statistics about the loaded knowledge base."""
        stats = {}
        for name, data in self._cache.items():
            if isinstance(data, dict):
                for key, val in data.items():
                    if isinstance(val, dict):
                        stats[name] = len(val)
                        break
        return stats
