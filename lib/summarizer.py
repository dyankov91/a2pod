"""Episode summarization for podcast feed descriptions.

Generates a 2-3 sentence summary via the configured LLM provider.
Uses extractive pre-processing (sumy/LexRank) to pull key sentences from the
entire article before sending to the LLM, producing better summaries that
reference content throughout the article rather than just the intro.
Falls back gracefully if sumy or the LLM is unavailable.
"""

import re

from llm import generate, strip_preamble

MAX_INPUT_CHARS = 3000  # fallback: truncate to first N chars
MAX_EXTRACT_CHARS = 2000  # target size for extracted key content
EXTRACT_SENTENCE_COUNT = 15  # max sentences to request from sumy


def _extract_headers(text: str) -> list[str]:
    """Extract likely section headers from article text.

    Heuristic: short lines (<80 chars) preceded by a blank line, not ending
    in sentence punctuation, followed by longer content.
    """
    lines = text.split("\n")
    headers = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) >= 80:
            continue
        # Must not end with sentence punctuation
        if stripped[-1] in ".!?:;,":
            continue
        # Must be preceded by a blank line (or be the first line)
        if i > 0 and lines[i - 1].strip():
            continue
        # Must be followed by a longer line within the next 2 lines
        has_content_after = False
        for j in range(i + 1, min(i + 3, len(lines))):
            if len(lines[j].strip()) > len(stripped):
                has_content_after = True
                break
        if has_content_after:
            headers.append(stripped)
    return headers


def _extract_key_content(text: str, title: str = "") -> str:
    """Extract key sentences and headers from the full article text.

    Uses sumy's LexRank algorithm to rank sentences by importance, then
    re-orders them by original position to preserve narrative flow.
    Falls back to simple truncation if sumy is unavailable.
    """
    if len(text) <= MAX_INPUT_CHARS:
        return text

    try:
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.summarizers.lex_rank import LexRankSummarizer
    except ImportError:
        return text[:MAX_INPUT_CHARS]

    try:
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = LexRankSummarizer()
        ranked_sentences = summarizer(parser.document, EXTRACT_SENTENCE_COUNT)

        # Re-order by original position in the document
        sentence_list = []
        for sentence in ranked_sentences:
            sent_text = str(sentence).strip()
            pos = text.find(sent_text)
            if pos == -1:
                pos = len(text)  # put unfound sentences at the end
            sentence_list.append((pos, sent_text))
        sentence_list.sort(key=lambda x: x[0])

        # Extract headers for structural context
        headers = _extract_headers(text)
        header_budget = MAX_EXTRACT_CHARS // 3
        header_block = ""
        header_chars = 0
        for h in headers:
            entry = f"- {h}\n"
            if header_chars + len(entry) > header_budget:
                break
            header_block += entry
            header_chars += len(entry)

        # Assemble extract within budget
        remaining_budget = MAX_EXTRACT_CHARS - len(header_block)
        sentences_block = ""
        for _, sent_text in sentence_list:
            entry = sent_text + " "
            if len(sentences_block) + len(entry) > remaining_budget:
                break
            sentences_block += entry

        parts = []
        if header_block:
            parts.append("Section headers:\n" + header_block.rstrip())
        if sentences_block:
            parts.append("Key passages:\n" + sentences_block.strip())

        extract = "\n\n".join(parts)
        return extract if extract else text[:MAX_INPUT_CHARS]

    except Exception:
        return text[:MAX_INPUT_CHARS]


def _fallback_summary(text: str) -> str:
    """Extract the first sentence as a fallback summary, truncated to 500 chars."""
    text = text.strip()
    # Find first sentence-ending punctuation
    for end in (".  ", ". ", ".\n", "! ", "!\n", "? ", "?\n"):
        idx = text.find(end)
        if idx != -1 and idx < 500:
            return text[: idx + 1]
    # No sentence boundary found — truncate at word boundary
    if len(text) <= 500:
        return text
    truncated = text[:500].rsplit(" ", 1)[0]
    return truncated + "..."


def summarize(text: str, title: str = "", model: str | None = None) -> str | None:
    """Generate a summary via LLM. Returns None on any failure."""
    if model is None:
        from llm import DEFAULT_MODEL
        model = DEFAULT_MODEL
    extract = _extract_key_content(text, title)
    prompt = (
        f"Write a 2-3 sentence summary of the following text for a podcast episode description. "
        f"The text below contains key sentences and section headers extracted from the full article. "
        f"Output ONLY the summary sentences — no preamble, no labels, no introductory phrases. "
        f"Do not start with 'This article', 'The article', 'This episode', or 'Here is'. "
        f"Jump straight into the content.\n\n"
        f"Title: {title}\n\n"
        f"{extract}"
    )

    summary = generate(prompt, temperature=0.3, max_tokens=200, model=model)

    if summary:
        summary = strip_preamble(summary)
    if summary:
        # Truncate to 4000 chars (iTunes limit)
        return summary[:4000]
    return None


def get_summary(text: str, title: str = "", model: str | None = None) -> str:
    """Generate a summary, falling back to first-sentence extraction on failure."""
    result = summarize(text, title, model)
    if result:
        return result
    return _fallback_summary(text)
