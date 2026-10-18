"""Bounded snapshot source excerpts and honest served-range accounting.

Line semantics: snapshot files are read as raw bytes (bounded by the ingestion
``max_file_bytes`` cap, plus one byte to detect an oversized artifact) and
decoded as UTF-8 with replacement; indexed files already passed a strict UTF-8
decode, so replacement only ever marks a byte-boundary cut. Source lines are
delimited by LF only, matching Python's AST line numbers: CR (including CRLF),
U+2028 and U+2029 are valid characters *within* a line, and ``splitlines()``
must not be used because it would invent line numbers the parser never saw.
A trailing LF belongs to the line it terminates and never starts a new one,
so a file ending in "\\n" has no phantom empty final line.
"""

import hashlib
import os
import re
import stat
from pathlib import Path, PurePosixPath

from api.config import settings
from api.ingestion.sources import SourceError

LINE_WINDOW = 200  # maximum source lines served by one evidence read
CONTEXT_LINES = 3  # lines of padding around an entity's own range
CHAR_BUDGET = 12000  # maximum excerpt characters served by one source read

_TREE_HASH = re.compile(r"[0-9a-f]{64}\Z")
_NOFOLLOW_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_NOFOLLOW_LEAF = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


def snapshot_root(repo):
    """The retained snapshot tree for a repository view, or SourceError.

    ``tree_hash`` identifies the immutable extracted tree. It comes from
    pinned snapshot/branch stats and is validated before joining storage.
    Every component under the owned data directory (``snapshots``, the
    repository directory and the tree directory itself) must be a real
    directory — a symlink anywhere in that prefix is rejected before reads.
    """
    tree_hash = (getattr(repo, "stats", None) or {}).get("tree_hash")
    if not isinstance(tree_hash, str) or not _TREE_HASH.fullmatch(tree_hash):
        raise SourceError("No retained source snapshot is recorded for this revision")
    probe = settings().data_dir.resolve()
    for part in ("snapshots", str(repo.id), tree_hash):
        probe = probe / part
        if probe.is_symlink() or (probe.exists() and not probe.is_dir()):
            raise SourceError("Source artifact is unavailable")
    if not probe.is_dir():
        raise SourceError("Source artifact is unavailable")
    return probe


def open_snapshot_file(root, relpath):
    """Open an approved snapshot member without following any symlink.

    Path components are validated first; traversal then walks real directory
    descriptors with O_NOFOLLOW on every component, and the leaf is
    fstat-verified as a regular file (O_NONBLOCK so a replaced FIFO cannot
    block the open). When ``root`` sits under the owned data directory the
    walk starts at the data directory itself, so symlinked ancestors of the
    snapshot tree are rejected instead of followed. Descriptor-relative opens
    keep the read rooted in owned storage even under a concurrent rename.
    Returns an open fd.
    """
    rel = PurePosixPath(relpath or "")
    parts = rel.parts
    if (
        rel.is_absolute()
        or not parts
        or any(part in {"", ".", ".."} or "\\" in part for part in parts)
    ):
        raise SourceError("Unsafe snapshot path")
    # Derive the ORIGINAL lexical prefix below the owned data root — never a
    # resolved path, which would erase symlinked components before the walk.
    # Every original component is then opened with O_NOFOLLOW from the owned
    # data-root descriptor, so a symlink anywhere in the prefix (including
    # ``snapshots`` itself or the per-repository directory) is rejected.
    root_path = Path(root)
    data_root = Path(settings().data_dir).resolve()
    try:
        tail = root_path.relative_to(data_root).parts
    except ValueError:
        base, tail = root_path, ()
    else:
        if not tail or any(part in {"", ".", ".."} for part in tail):
            raise SourceError("Source artifact is unavailable")
        base = data_root
    try:
        fd = os.open(str(base), _NOFOLLOW_DIR)
    except OSError as exc:
        raise SourceError("Source artifact is unavailable") from exc
    try:
        for part in (*tail, *parts[:-1]):
            next_fd = os.open(part, _NOFOLLOW_DIR, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        leaf = os.open(parts[-1], _NOFOLLOW_LEAF, dir_fd=fd)
    except OSError as exc:
        raise SourceError("Source artifact is unavailable") from exc
    finally:
        os.close(fd)
    try:
        if not stat.S_ISREG(os.fstat(leaf).st_mode):
            raise SourceError("Source artifact is unavailable")
    except BaseException:
        os.close(leaf)
        raise
    return leaf


def read_snapshot_bytes(root, relpath, limit):
    """Return ``(raw, hit_cap)`` — at most ``limit`` bytes of a snapshot file."""
    fd = open_snapshot_file(root, relpath)
    try:
        chunks, remaining = [], limit + 1
        while remaining > 0:
            chunk = os.read(fd, min(remaining, 262144))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    return raw[:limit], len(raw) > limit


def _read_lines(root, relpath, content_hash=None):
    """Return ``(lines, hit_cap)`` for an approved snapshot file.

    The read is bounded: at most ``max_file_bytes`` bytes are decoded and the
    boolean reports whether the file was longer. When the byte cap landed
    mid-line the incomplete tail segment is dropped rather than served as a
    falsely complete line. ``content_hash`` pins the raw bytes to the
    manifest's recorded digest — a retained file that was modified, replaced
    or truncated after indexing fails verification instead of being served
    under the immutable snapshot identity.
    """
    limit = settings().max_file_bytes
    raw, hit_cap = read_snapshot_bytes(root, relpath, limit)
    if content_hash and (hit_cap or hashlib.sha256(raw).hexdigest() != content_hash):
        raise SourceError("Retained source failed integrity verification")
    text = raw.decode("utf-8", errors="replace")
    if not text:
        return [], hit_cap
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    elif hit_cap:
        lines.pop()
    return lines, hit_cap


def read_source_range(
    root,
    relpath,
    start_line,
    end_line=None,
    *,
    context=0,
    max_lines=LINE_WINDOW,
    max_chars=CHAR_BUDGET,
    content_hash=None,
    column=None,
    end_column=None,
):
    """Read a bounded line window from an approved snapshot file.

    With ``context`` (entity-anchored excerpts) the declared span is the
    entity's own ``[start_line, end_line]``, padded on both sides; an absent
    ``end_line`` means only the padded start. ``truncated`` then means the
    entity's declared span extends beyond the served window — including when
    the file itself is shorter than the declaration.

    With ``context=0`` (explicit range reads) the requested span is
    ``[start_line, end_line or EOF]``; ``truncated`` means the bounded window
    stopped while requested or unserved content remained, including content
    hidden behind the byte cap.

    ``max_chars`` bounds the served excerpt. Without a ``column`` anchor the
    cap cuts the tail and ``end_line_partial`` reports a mid-line final line.
    With ``column``/``end_column`` (a match or selected span on the anchor
    line) lines after the anchor are dropped first, then earlier padding, so
    the anchor is always served; an anchor line that alone exceeds the budget
    is served as a bounded column-windowed segment and ``line_excerpt``
    discloses the exact character span instead of silently omitting the match.
    """
    lines, hit_cap = _read_lines(root, relpath, content_hash)
    last_known = len(lines)
    start = max(1, start_line - context)
    if context:
        declared = start if end_line is None else end_line
        wanted = declared + context
        end = min(last_known, wanted, start + max_lines - 1)
        truncated = end < (end_line or 0)
    else:
        wanted = end_line if end_line is not None else last_known + (1 if hit_cap else 0)
        end = min(last_known, wanted, start + max_lines - 1)
        truncated = end < wanted
    if hit_cap and end >= last_known and wanted >= last_known:
        truncated = True  # more bytes exist beyond what the cap served
    end = max(end, start - 1)
    window = lines[start - 1 : end] if end >= start else []
    line_excerpt = None
    if column is not None and window and max_chars is not None:
        # Character bound keeps the anchored match in view: padding lines are
        # dropped (after the anchor first, then before it) before the anchor
        # line itself is windowed around the reported columns.
        anchor_idx = min(max(start_line - start, 0), len(window) - 1)
        head, tail = window[:anchor_idx], window[anchor_idx + 1 :]
        anchor = window[anchor_idx]

        def kept():
            return len(anchor) + sum(len(line) + 1 for line in head + tail)

        while tail and kept() > max_chars:
            tail.pop()
        while head and kept() > max_chars:
            head.pop(0)
        if len(anchor) > max_chars:
            # The anchored line alone exceeds the budget: serve a bounded
            # character window containing the reported match columns and
            # disclose the exact span instead of omitting the hit.
            lo = min(max(column - 1, 0), len(anchor) - 1)
            hi = min(max(lo + 1, (end_column or column + 1) - 1), len(anchor))
            margin = max(0, (max_chars - (hi - lo)) // 2)
            col_start = max(1, lo - margin + 1)
            col_end = min(len(anchor), col_start - 1 + max_chars)
            col_start = max(1, col_end - max_chars + 1)
            line_excerpt = {
                "line": start + anchor_idx,
                "start_column": col_start,
                "end_column": col_end,
                "line_length": len(anchor),
                "partial": True,
            }
            anchor = anchor[col_start - 1 : col_end]
            truncated = True
        dropped = (anchor_idx - len(head)) + (len(window) - anchor_idx - 1 - len(tail))
        # A column-windowed anchor line whose suffix was omitted means the
        # final served line is partial — disclose it, don't claim completeness.
        end_partial = bool(
            line_excerpt
            and line_excerpt["partial"]
            and line_excerpt["end_column"] < line_excerpt["line_length"]
        )
        return {
            "content": "\n".join([*head, anchor, *tail]),
            "start_line": start + anchor_idx - len(head),
            "end_line": start + anchor_idx + len(tail),
            "truncated": truncated or dropped > 0,
            "end_line_partial": end_partial,
            "line_excerpt": line_excerpt,
            "content_hash": content_hash,
        }
    excerpt = "\n".join(window)
    if max_chars is not None and len(excerpt) > max_chars:
        sliced = bounded_slice(excerpt, start, end, max_chars, upstream_truncated=truncated)
        sliced["line_excerpt"] = None
        sliced["content_hash"] = content_hash
        return sliced
    return {
        "content": excerpt,
        "start_line": start,
        "end_line": end,
        "truncated": truncated,
        "end_line_partial": False,
        "line_excerpt": line_excerpt,
        "content_hash": content_hash,
    }


def bounded_slice(
    text, start_line, end_line, limit, upstream_truncated=False, upstream_partial=None
):
    """Slice ``text`` to ``limit`` characters and describe what is served.

    ``start_line``/``end_line`` describe the LF-delimited source range ``text``
    covers; pass None for non-source text to keep null ranges. ``truncated``
    is true whenever the excerpt was cut by ``limit``; otherwise it preserves
    ``upstream_truncated`` verbatim — False for complete, None for unknown —
    so absent upstream metadata is never silently upgraded to "complete".
    An empty excerpt cut from a nonempty selection is still truncated.
    ``end_line_partial`` marks a final served line cut mid-line: a slice that
    ends at, or immediately before, an LF serves that line completely. When no
    local cut happened, ``upstream_partial`` (for example a column-windowed
    line that omitted its suffix) is preserved instead of being reported
    complete.
    """
    excerpt = text[: max(limit, 0)]
    cut = len(excerpt) < len(text)
    truncated = True if cut else upstream_truncated
    if start_line is None:
        return {
            "content": excerpt,
            "start_line": None,
            "end_line": None,
            "truncated": truncated,
            "end_line_partial": upstream_partial if not cut else None,
        }
    if not excerpt:
        return {
            "content": "",
            "start_line": start_line,
            "end_line": start_line - 1,
            "truncated": truncated,
            "end_line_partial": False if cut else upstream_partial,
        }
    served = excerpt.count("\n")
    if not excerpt.endswith("\n"):
        served += 1  # the trailing partial-or-complete line still counts
    end = start_line + served - 1
    if end_line is not None:
        end = min(end, end_line)
    partial = bool(cut and excerpt[-1] != "\n" and text[len(excerpt)] != "\n")
    if not cut:
        # No local cut: preserve upstream partial-final-line disclosure; when
        # upstream declared nothing, a fully served final line is complete.
        partial = upstream_partial if upstream_partial is not None else False
    return {
        "content": excerpt,
        "start_line": start_line,
        "end_line": end,
        "truncated": truncated,
        "end_line_partial": partial,
    }
