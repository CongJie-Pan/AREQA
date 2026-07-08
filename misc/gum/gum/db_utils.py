# db_utils.py

from __future__ import annotations

import json
import math
import re
import logging
from datetime import datetime, timezone
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from sqlalchemy import (
    MetaData,
    Table,
    select,
    literal_column,
    text,
    func,
)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import (
    Observation,
    Proposition,
    observation_proposition,
)

# Constants
K_DECAY = 2.0      # decay rate for recency adjustment
LAMBDA = 0.5       # trade-off for MMR

def build_fts_query(raw: str, mode: str = "OR") -> str:
    import jieba
    
    # Use jieba to properly tokenize Chinese strings, 
    # and keep only tokens containing word characters (alphanumeric or Chinese)
    # to avoid syntax errors from punctuation in FTS MATCH query.
    words = jieba.lcut(raw.lower())
    tokens = [w for w in words if re.search(r'\w', w)]
    
    if not tokens:
        # Fallback to simple regex if jieba fails or returns nothing
        tokens = re.findall(r"\w+", raw.lower())
        
    if not tokens:
        return ""
        
    if mode == "PHRASE":
        return f'"{" ".join(tokens)}"'
    elif mode == "OR":
        return " OR ".join(tokens)
    else:  # implicit AND
        return " ".join(tokens)




async def search_propositions_bm25(
    session: AsyncSession,
    user_query: str,
    *,
    user_id: str = "default_user",
    selected_labels: dict | None = None,
    limit: int = 3,
    mode: str = "OR",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    include_observations: bool = True,
    enable_decay: bool = True,
    enable_mmr: bool = True,
    include_deleted: bool = False,
) -> list[tuple["Proposition", float]]:

    bind = session.bind or session.sync_session.bind
    is_pg = getattr(bind.dialect, "name", "") == "postgresql" if bind else True
    q = build_fts_query(user_query, mode) if not is_pg else user_query
    has_query = bool(q)

    # --------------------------------------------------------
    # 1  Build candidate list
    # --------------------------------------------------------
    candidate_pool = limit * 10 if enable_mmr else limit

    if has_query:
        fts_prop = Table("propositions_fts", MetaData())

        if include_observations:
            # --- 1-a-1  WITH observations --------------------
            if is_pg:
                bm25_p = literal_column("ts_rank(to_tsvector('english', propositions.text), plainto_tsquery('english', :q))").label("score")
                bm25_o = literal_column("ts_rank(to_tsvector('english', observations.content), plainto_tsquery('english', :q))").label("score")

                sub_p = (
                    select(Proposition.id.label("pid"), bm25_p)
                    .where(text("to_tsvector('english', propositions.text) @@ plainto_tsquery('english', :q)"))
                )

                sub_o = (
                    select(observation_proposition.c.proposition_id.label("pid"), bm25_o)
                    .select_from(
                        Observation
                        .join(
                            observation_proposition,
                            observation_proposition.c.observation_id == Observation.id,
                        )
                    )
                    .where(text("to_tsvector('english', observations.content) @@ plainto_tsquery('english', :q)"))
                )
            else:
                fts_obs  = Table("observations_fts", MetaData())

                bm25_p   = literal_column("bm25(propositions_fts)").label("score")
                bm25_o   = literal_column("bm25(observations_fts)").label("score")

                sub_p = (
                    select(Proposition.id.label("pid"), bm25_p)
                    .select_from(
                        fts_prop.join(
                            Proposition,
                            literal_column("propositions_fts.rowid") == Proposition.id,
                        )
                    )
                    .where(text("propositions_fts MATCH :q"))
                )

                sub_o = (
                    select(observation_proposition.c.proposition_id.label("pid"), bm25_o)
                    .select_from(
                        fts_obs
                        .join(
                            Observation,
                            literal_column("observations_fts.rowid") == Observation.id,
                        )
                        .join(
                            observation_proposition,
                            observation_proposition.c.observation_id == Observation.id,
                        )
                    )
                    .where(text("observations_fts MATCH :q"))
                )

            union_sub = sub_p.union_all(sub_o).subquery()

            best_scores = (
                select(
                    union_sub.c.pid,
                    func.max(union_sub.c.score).label("bm25") if is_pg else func.min(union_sub.c.score).label("bm25"),
                )
                .group_by(union_sub.c.pid)
                .subquery()
            )
        else:
            # --- 1-a-2  WITHOUT observations -----------------
            if is_pg:
                best_scores = (
                    select(
                        Proposition.id.label("pid"),
                        literal_column("ts_rank(to_tsvector('english', propositions.text), plainto_tsquery('english', :q))").label("bm25"),
                    )
                    .where(text("to_tsvector('english', propositions.text) @@ plainto_tsquery('english', :q)"))
                    .subquery()
                )
            else:
                best_scores = (
                    select(
                        Proposition.id.label("pid"),
                        literal_column("bm25(propositions_fts)").label("bm25"),
                    )
                    .select_from(
                        fts_prop.join(
                            Proposition,
                            literal_column("propositions_fts.rowid") == Proposition.id,
                        )
                    )
                    .where(text("propositions_fts MATCH :q"))
                    .subquery()
                )

        stmt = (
            select(Proposition, best_scores.c.bm25)
            .join(best_scores, best_scores.c.pid == Proposition.id)
            .where(Proposition.user_id == user_id)
        )
        if not include_deleted:
            stmt = stmt.where(Proposition.status == 'active')
        else:
            stmt = stmt.where(Proposition.status.in_(['active', 'deleted']))
        if is_pg:
            stmt = stmt.order_by(best_scores.c.bm25.desc())         # largest→best
        else:
            stmt = stmt.order_by(best_scores.c.bm25.asc())          # smallest→best
    else:
        # --- 1-b  No user query ------------------------------
        stmt = (
            select(Proposition, literal_column("0").label("bm25"))
            .where(Proposition.user_id == user_id)
        )
        if not include_deleted:
            stmt = stmt.where(Proposition.status == 'active')
        else:
            stmt = stmt.where(Proposition.status.in_(['active', 'deleted']))
        stmt = stmt.order_by(Proposition.created_at.desc())

    # --------------------------------------------------------
    # 2  Time filtering & eager-load
    # --------------------------------------------------------
    if end_time is None:
        end_time = datetime.now(timezone.utc)
    if start_time is not None and start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    if start_time is not None:
        stmt = stmt.where(Proposition.created_at >= start_time)
    stmt = stmt.where(Proposition.created_at <= end_time)

    if include_observations:
        stmt = stmt.options(selectinload(Proposition.observations))

    stmt = stmt.limit(candidate_pool)

    # --------------------------------------------------------
    # 3  Execute & score
    # --------------------------------------------------------
    bind = {"q": q} if has_query else {}
    rows = (await session.execute(stmt, bind)).all()
    if not rows:
        return []

    # STITCH Label Density Ranking Filter
    logger = logging.getLogger("gum")
    filtered_rows = []
    if selected_labels:
        sel_scopes = selected_labels.get("selected_context_scopes", [])
        sel_events = selected_labels.get("selected_event_types", [])
        sel_targets = selected_labels.get("selected_targets", [])
        sel_func = selected_labels.get("selected_functional_type_seeds", [])
        
        has_scope = bool(sel_scopes)
        has_target = bool(sel_targets)
        
        # 3-Tier Gate Logic for STITCH Fallback
        DOMAIN_SCOPES = ["《紅樓夢》", "中國古典文學", "古典詩詞", "四大名著", "《紅樓夢》人物分析", "《紅樓夢》情節", "《紅樓夢》文學細節"]
        
        trigger_stitch = False
        if has_scope and has_target:
            trigger_stitch = True  # Gate 1: Both exist -> High confidence STITCH
        elif has_scope and not has_target:
            # Gate 2: Only scope exists -> Check if it's in domain
            trigger_stitch = any(any(domain in scope for domain in DOMAIN_SCOPES) for scope in sel_scopes)
            
        if not trigger_stitch:
            # Gate 3: Neither exist (or scope out of domain) -> Fallback to pure BM25
            logger.info("[STITCH] No substantial entities/scopes selected. Fallback to pure BM25 search.")
            filtered_rows = [(prop, raw_score, 0) for prop, raw_score in rows]
        else:
            logger.info(f"[STITCH] Filtering {len(rows)} candidates using Label Density Ranking...")
            for prop, raw_score in rows:
                num_matches = 0
                
                # Count label matches
                if prop.context_scope and prop.context_scope in sel_scopes:
                    num_matches += 1
                if prop.event_types:
                    try:
                        et_list = json.loads(prop.event_types)
                        if any(et in sel_events for et in et_list):
                            num_matches += 1
                    except Exception: pass
                if prop.target and prop.target in sel_targets:
                    num_matches += 1
                if prop.functional_type_seeds:
                    try:
                        ft_list = json.loads(prop.functional_type_seeds)
                        if any(ft in sel_func for ft in ft_list):
                            num_matches += 1
                    except Exception: pass
                
                # STITCH logic: Only keep memory if num_matches > 0
                if num_matches > 0:
                    filtered_rows.append((prop, raw_score, num_matches))
                    
            logger.info(f"[STITCH] Filtered down to {len(filtered_rows)} candidates.")
            # Strict STITCH mode: if LLM selected labels but nothing matched, we return []
            if not filtered_rows:
                logger.warning("[STITCH] Strict mode: No candidates matched the predicted labels. Returning empty results.")
                return []
    else:
        filtered_rows = [(prop, raw_score, 0) for prop, raw_score in rows]

    # --- 3-a. Calculate initial scores ---
    initial_scores: list[float] = []
    now = datetime.now(timezone.utc)
    for prop, raw_score, num_matches in filtered_rows:
        relevance_score = float(raw_score) if is_pg else float(-raw_score) if has_query else 0.0
        gamma = 0.0
        if enable_decay:
            dt = prop.created_at.replace(tzinfo=timezone.utc)
            age_days = max((now - dt).total_seconds() / 86_400, 0.0)
            alpha = prop.decay if prop.decay is not None else 0.0
            gamma = -alpha * K_DECAY * age_days

        score = relevance_score * math.exp(gamma)
        
        # Apply Label Density boost (primary ranking factor)
        if selected_labels:
            score += num_matches * 50.0
            
        initial_scores.append(score)

    final_scores_np = np.array(initial_scores)
    min_score = np.min(final_scores_np)
    max_score = np.max(final_scores_np)
    
    if max_score > min_score:
        final_scores_np = (final_scores_np - min_score) / (max_score - min_score)
    else:
        final_scores_np = np.full_like(final_scores_np, 0.5)

    final_scores = final_scores_np.tolist()

    if enable_mmr and len(filtered_rows) > 1:
        docs: list[str] = []
        for p, _, _ in filtered_rows:
            doc_parts = [p.text, p.reasoning]
            if include_observations and p.observations:
                obs_concat = " ".join(o.content for o in list(p.observations)[:10])
                doc_parts.append(obs_concat)
            docs.append(" ".join(doc_parts))

        vecs = TfidfVectorizer().fit_transform(docs)
        
        selected_idxs = []
        mmr_scores = np.array(final_scores)

        while len(selected_idxs) < min(limit, len(filtered_rows)):
            if not selected_idxs:
                idx = int(np.argmax(mmr_scores))
            else:
                sims = cosine_similarity(vecs, vecs[selected_idxs]).max(axis=1)
                mmr = LAMBDA * mmr_scores - (1 - LAMBDA) * sims
                mmr[selected_idxs] = -np.inf 
                idx = int(np.argmax(mmr))

            selected_idxs.append(idx)
    else:
        idxs = np.argsort(final_scores)[::-1][:limit]
        selected_idxs = idxs.tolist()

    result = [(filtered_rows[i][0], final_scores[i]) for i in selected_idxs]    
    return result

async def get_related_observations(
    session: AsyncSession,
    proposition_id: int,
    *,  # Force keyword arguments for optional parameters
    limit: int = 5,
) -> List[Observation]:

    stmt = (
        select(Observation)
        .join(observation_proposition)
        .join(Proposition)
        .where(Proposition.id == proposition_id)
        .order_by(Observation.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_recent_propositions(
    session: AsyncSession,
    *,
    user_id: str = "default_user",
    limit: int = 10,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    include_observations: bool = False,
) -> List[Proposition]:
    """Fetch the most recent propositions ordered by created_at desc.

    Args:
        session: Active async DB session
        limit: Max number of propositions to return
        start_time: Optional lower bound for created_at
        end_time: Optional upper bound for created_at (defaults to now)
        include_observations: Whether to eager-load related observations

    Returns:
        List[Proposition]: Most recent propositions
    """

    if end_time is None:
        end_time = datetime.now(timezone.utc)
    if start_time is not None and start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    stmt = (
        select(Proposition)
        .where(Proposition.user_id == user_id)
        .where(Proposition.status == 'active')
        .where(Proposition.created_at <= end_time)
        .order_by(Proposition.created_at.desc())
        .limit(limit)
    )
    if start_time is not None:
        stmt = stmt.where(Proposition.created_at >= start_time)
    if include_observations:
        stmt = stmt.options(selectinload(Proposition.observations))

    result = await session.execute(stmt)
    return result.scalars().all()


async def get_recent_observations(
    session: AsyncSession,
    *,
    user_id: str = "default_user",
    limit: int = 10,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> List[Observation]:
    """Fetch the most recent observations ordered by created_at desc."""
    if end_time is None:
        end_time = datetime.now(timezone.utc)
    if start_time is not None and start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    stmt = (
        select(Observation)
        .where(Observation.user_id == user_id)
        .where(Observation.created_at <= end_time)
        .order_by(Observation.created_at.desc())
        .limit(limit)
    )
    if start_time is not None:
        stmt = stmt.where(Observation.created_at >= start_time)

    result = await session.execute(stmt)
    return result.scalars().all()