"""Recursive token-based text splitter with separator cascade and overlap.

Follows architecture spec §4.4:
Separator cascade: \\n\\n -> \\n -> sentence endings (. , ? , ! ) -> space.
Preserves semantic continuity with controlled overlap.
"""

import re

from src.ingest.chunking.tokenizer import estimate_tokens


class RecursiveTokenSplitter:
    """Recursively splits text into chunks within token bounds using natural separators."""

    def __init__(
        self,
        target_tokens: int = 300,
        max_tokens: int = 450,
        min_tokens: int = 120,
        overlap_ratio: float = 0.12,
    ) -> None:
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.overlap_tokens = max(10, int(target_tokens * overlap_ratio))
        self.separators = ["\n\n", "\n", ". ", "? ", "! ", " "]

    def split_text(self, text: str) -> list[str]:
        """Split text into chunks meeting the target token sizes."""
        cleaned = text.strip()
        if not cleaned:
            return []

        if estimate_tokens(cleaned) <= self.max_tokens:
            return [cleaned]

        raw_pieces = self._recursive_split(cleaned, self.separators)
        merged_pieces = self._merge_pieces(raw_pieces)
        return merged_pieces

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text using the current or next separator."""
        if estimate_tokens(text) <= self.max_tokens or not separators:
            return [text]

        separator = separators[0]
        remaining_separators = separators[1:]

        # Split text on current separator
        if separator in (". ", "? ", "! "):
            # Split preserving punctuation
            pattern = re.escape(separator.strip()) + r"\s+"
            splits = [s.strip() for s in re.split(pattern, text) if s.strip()]
        else:
            splits = [s.strip() for s in text.split(separator) if s.strip()]

        if len(splits) <= 1:
            # Separator did not break text, try next separator in cascade
            return self._recursive_split(text, remaining_separators)

        result: list[str] = []
        for piece in splits:
            if estimate_tokens(piece) > self.max_tokens:
                result.extend(self._recursive_split(piece, remaining_separators))
            else:
                result.append(piece)

        return result

    def _merge_pieces(self, pieces: list[str]) -> list[str]:
        """Combine smaller pieces up to target_tokens with overlap when chunks split."""
        if not pieces:
            return []

        chunks: list[str] = []
        current_chunk_parts: list[str] = []
        current_tokens = 0

        for piece in pieces:
            piece_tokens = estimate_tokens(piece)

            if current_chunk_parts and (current_tokens + piece_tokens > self.max_tokens):
                # Finalize current chunk
                full_text = " ".join(current_chunk_parts)
                chunks.append(full_text)

                # Overlap context for next chunk
                overlap_text = self._extract_overlap(full_text, self.overlap_tokens)
                if overlap_text:
                    current_chunk_parts = [overlap_text, piece]
                    current_tokens = estimate_tokens(overlap_text) + piece_tokens
                else:
                    current_chunk_parts = [piece]
                    current_tokens = piece_tokens
            else:
                current_chunk_parts.append(piece)
                current_tokens += piece_tokens

        if current_chunk_parts:
            chunks.append(" ".join(current_chunk_parts))

        # Second pass: if the last chunk is too small, merge into previous if possible
        if len(chunks) > 1 and estimate_tokens(chunks[-1]) < self.min_tokens:
            combined = chunks[-2] + " " + chunks[-1]
            if estimate_tokens(combined) <= self.max_tokens * 1.2:
                chunks[-2] = combined
                chunks.pop()

        return chunks

    def _extract_overlap(self, text: str, overlap_tokens: int) -> str:
        """Extract trailing tokens from text to seed the next chunk."""
        words = text.split()
        if not words:
            return ""

        overlap_words: list[str] = []
        accumulated = 0
        for word in reversed(words):
            word_tok = estimate_tokens(word)
            if accumulated + word_tok > overlap_tokens:
                break
            overlap_words.insert(0, word)
            accumulated += word_tok

        return " ".join(overlap_words)
