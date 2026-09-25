"""Drop blocks that repeat across most pages of a batch (site nav, footers, banners)."""

import math
import re

_MIN_PAGES = 3
_SHARE = 0.6
_LINK_TARGET = re.compile(r"\]\(([^)\s]*)")
_FENCE = re.compile(r"^\s*(```|~~~)")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


def _split_blocks(markdown: str) -> list[str]:
    """Blank-line separated blocks; blank lines inside code fences do not split."""
    blocks: list[list[str]] = [[]]
    in_fence = False
    for line in markdown.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
        if not line.strip() and not in_fence:
            if blocks[-1]:
                blocks.append([])
        else:
            blocks[-1].append(line)
    return ["\n".join(b) for b in blocks if b]


def _fingerprint(block: str, is_chapter_target) -> str:
    return _LINK_TARGET.sub(
        lambda m: "](@chapter" if is_chapter_target(m.group(1)) else m.group(0), block
    )


def _removable(block: str) -> bool:
    # Headings and pure rules are structure, not chrome, even when they repeat.
    return not block.lstrip().startswith("#") and bool(re.search(r"[^\W_]", block))


def strip_shared_blocks(markdowns: list[str], is_chapter_target=lambda target: False) -> list[str]:
    """Remove non-heading blocks present in most of `markdowns` (the first block, the
    title, is always kept). Links to other chapters compare equal regardless of which
    chapter they point at, so a sidebar linking every chapter still matches everywhere."""
    if len(markdowns) < _MIN_PAGES:
        return markdowns
    docs = [_split_blocks(m) for m in markdowns]
    prints = [[_fingerprint(b, is_chapter_target) for b in blocks] for blocks in docs]
    counts: dict[str, int] = {}
    for doc_prints in prints:
        for fp in set(doc_prints[1:]):
            counts[fp] = counts.get(fp, 0) + 1
    needed = max(_MIN_PAGES, math.ceil(_SHARE * len(markdowns)))
    shared = {fp for fp, n in counts.items() if n >= needed and _removable(fp)}
    if not shared:
        return markdowns

    result = []
    for original, blocks, doc_prints in zip(markdowns, docs, prints):
        kept = [blocks[0]] + [b for b, fp in zip(blocks[1:], doc_prints[1:]) if fp not in shared]
        if len(kept) == len(blocks):
            result.append(original)
            continue
        while len(kept) > 1 and _RULE.match(kept[-1]):
            kept.pop()
        result.append("\n\n".join(kept))
    return result
