from copy import deepcopy

from fastapi import APIRouter, Depends, Query
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

router = APIRouter(prefix="/api/repositories/{repository_id}", tags=["context"])


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


@router.post("/context")
def context(
    repository_id: str,
    body: Question,
    user: User = Depends(current_session),
    db: Session = Depends(db_session),
    repo: RepositoryView = Depends(read_repository),
):
    indexed(repo)
    result = retrieve(repo, body.question)
    citations = []
    # Exact source excerpts are bounded before crossing the model boundary.
    remaining = 24000
    for i, node in enumerate(result["results"][:8]):
        evidence = read_evidence(repo, node["id"])
        content = evidence["content"][: min(3000, remaining)]
        if node["type"] == "LogArtifact" and not content:
            result["warnings"].append(evidence.get("notice", "Log content is unavailable"))
        remaining -= len(content)
        citations.append(
            {
                "citation": f"E{i + 1}",
                "entity_id": node["id"],
                "name": node["name"],
                "type": node["type"],
                "path": node.get("path"),
                "start_line": evidence["start_line"],
                "end_line": evidence["end_line"],
                "commit": evidence["commit"],
                "content": content,
                "url": evidence["url"],
            }
        )
    synthesis = (
        synthesize(
            body.question,
            citations,
            result["relationships"],
            credential=for_synthesis(db, user.id),
        )
        if citations
        else {
            "mode": "graph",
            "answer": None,
            "citations": [],
            "notice": "The graph has insufficient evidence to answer this question.",
        }
    )
    result["diagnostics"]["graph_queries"] += len(citations)
    result["diagnostics"]["max_graph_queries"] = 15
    result["diagnostics"]["source_excerpts"] = len(citations)
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
