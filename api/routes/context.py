from copy import deepcopy

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.agent.synthesis import synthesize
from api.auth import current_session
from api.db import db_session
from api.model_credentials import for_synthesis
from api.models import Conversation, User
from api.routes.repositories import read_evidence
from api.search.retrieval import retrieve
from api.services.permissions import indexed
from api.services.revisions import RepositoryView, read_repository
from api.services.source_ranges import bounded_slice

router = APIRouter(prefix="/api/repositories/{repository_id}", tags=["context"])


class SelectedSource(BaseModel):
    """An exact source selection the asker wants cited, pinned to a node."""

    node_id: str = Field(min_length=1, max_length=300)
    start: int | None = Field(None, ge=1)
    end: int | None = Field(None, ge=1)
    around: int | None = Field(None, ge=1)
    column: int | None = Field(None, ge=1)
    end_column: int | None = Field(None, ge=1)


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    source: SelectedSource | None = None


@router.post("/context")
def context(
    repository_id: str,
    body: Question,
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
    repo: RepositoryView = Depends(read_repository),
):
    indexed(repo)
    recent = list(
        db.scalars(
            select(Conversation)
            .where(
                Conversation.repository_id == repo.id,
                Conversation.user_id == user.id,
                Conversation.branch == repo.branch,
                Conversation.snapshot_id == repo.snapshot_id,
            )
            .order_by(Conversation.created_at.desc())
            .limit(3)
        )
    )
    previous_question = next(
        (
            c.question
            for c in recent
            if not c.response.get("diagnostics", {}).get("used_previous_question")
        ),
        recent[0].question if recent else None,
    )
    result = retrieve(repo, body.question, previous_question=previous_question)
    history = [
        {"question": c.question[:1000], "answer": (c.response.get("answer") or "")[:2000]}
        for c in reversed(recent)
    ]
    citations = []
    served_spans = set()
    # Exact source excerpts are bounded before crossing the model boundary.
    # The remaining per-citation budget is passed INTO the evidence reader so
    # a column-anchored match window is recentered before slicing — the served
    # range/columns describe the actual text and always contain the match.
    remaining = 24000

    def span_key(node_id, evidence):
        excerpt = evidence.get("line_excerpt") or {}
        return (
            node_id,
            evidence.get("start_line"),
            evidence.get("end_line"),
            excerpt.get("start_column"),
            excerpt.get("end_column"),
        )

    def cite(node, evidence, pinned=False):
        nonlocal remaining
        excerpt = bounded_slice(
            evidence["content"],
            evidence["start_line"],
            evidence["end_line"],
            min(3000, remaining),
            upstream_truncated=evidence.get("truncated"),
            upstream_partial=evidence.get("end_line_partial"),
        )
        content = excerpt["content"]
        if node["type"] == "LogArtifact" and not content:
            result["warnings"].append(evidence.get("notice", "Log content is unavailable"))
        remaining -= len(content)
        citation = {
            "citation": f"E{len(citations) + 1}",
            "entity_id": node["id"],
            "name": node["name"],
            "type": node["type"],
            "path": node.get("path"),
            "start_line": excerpt["start_line"],
            "end_line": excerpt["end_line"],
            "truncated": excerpt["truncated"],
            "end_line_partial": excerpt["end_line_partial"],
            "line_excerpt": evidence.get("line_excerpt"),
            "content_hash": evidence.get("content_hash"),
            "commit": evidence["commit"],
            "content": content,
            "url": evidence["url"],
            "pinned": pinned,
            "match": node.get("match"),
        }
        citations.append(citation)
        served_spans.add(span_key(node["id"], evidence))

    graph_reads = 0
    if body.source is not None:
        sel = body.source
        if sel.start is not None and sel.end is not None and sel.end < sel.start:
            raise HTTPException(422, "source.end must be at least source.start")
        selected = read_evidence(
            repo,
            sel.node_id,
            start=sel.start,
            end=sel.end,
            around=sel.around,
            column=sel.column,
            end_column=sel.end_column,
            max_chars=min(3000, remaining),
        )
        graph_reads += selected.get("graph_queries", 1)
        cite(selected["node"], selected, pinned=True)

    # The pinned selection reserves a citation slot; retrieved evidence fills
    # the rest of the 8-item budget and skips an exact duplicate of it —
    # including served columns, so a different window of the same line is not
    # mistaken for a duplicate.
    for node in result["results"]:
        if len(citations) >= 8 or remaining <= 0:
            break
        match = node.get("match") or {}
        evidence = read_evidence(
            repo,
            node["id"],
            around=match.get("line"),
            column=match.get("column"),
            end_column=match.get("end_column"),
            max_chars=min(3000, remaining),
        )
        graph_reads += evidence.get("graph_queries", 1)
        if span_key(node["id"], evidence) in served_spans:
            continue
        cite(node, evidence)
    synthesis = (
        synthesize(
            body.question,
            citations,
            result["relationships"],
            credential=for_synthesis(db, user.id),
            history=history,
        )
        if citations
        else {
            "mode": "graph",
            "answer": None,
            "citations": [],
            "notice": "No source matched this question. Add a file name, function, or error message to narrow it down.",
        }
    )
    result["diagnostics"]["graph_queries"] += graph_reads
    result["diagnostics"]["max_graph_queries"] = 28
    result["diagnostics"]["source_excerpts"] = len(citations)
    result["diagnostics"]["conversation_turns"] = len(history)
    result["diagnostics"]["context_bytes"] = len(str(citations).encode())
    result.update(synthesis)
    result["evidence"] = citations
    result["snapshot_id"] = repo.snapshot_id
    result["historical"] = repo.historical
    saved = deepcopy(result)
    for citation in saved["evidence"]:
        if citation["type"] == "LogArtifact":
            citation["content"] = "Open the linked log artifact to read retained evidence."
    row = Conversation(
        user_id=user.id,
        repository_id=repo.id,
        branch=repo.branch,
        snapshot_id=repo.snapshot_id,
        question=body.question,
        response=saved,
    )
    db.add(row)
    db.commit()
    return result | {"conversation_id": row.id}


@router.get("/conversations")
def conversations(
    repository_id: str,
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
    repo: RepositoryView = Depends(read_repository),
):
    return [
        {
            "id": c.id,
            "question": c.question,
            "response": c.response,
            "branch": c.branch,
            "snapshot_id": c.snapshot_id,
            "created_at": c.created_at,
        }
        for c in db.scalars(
            select(Conversation)
            .where(
                Conversation.repository_id == repo.id,
                Conversation.user_id == user.id,
                Conversation.branch == repo.branch,
                Conversation.snapshot_id == repo.snapshot_id if repo.historical else True,
            )
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
    ]
