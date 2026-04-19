"""Retriever node: query → top-k hits → state patch."""

from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from ....services.retrieval import retrieve
from ..state import AgentState
from ._shared import node_timer


def retriever_node_factory(session: Session, top_k: int):
    def _node(state: AgentState) -> AgentState:
        with node_timer(state, "retriever") as ev:
            result = retrieve(session, state["query"], top_k=top_k, rerank=True)
            state["retrieved"] = [asdict(h) for h in result.hits]
            state["avg_top_score"] = result.avg_top_score
            ev["confidence"] = result.avg_top_score
            ev["meta"] = {"n_hits": len(result.hits), "top_k": top_k}
            ev["decision"] = "retrieved"
        return state

    return _node


# Backwards-compatible name for graph.py imports
retriever_node = retriever_node_factory
