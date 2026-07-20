# gum.py

from __future__ import annotations

import asyncio
import json
import logging
import os
from uuid import uuid4
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Callable, List
from .models import observation_proposition
import traceback

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, update, func

from .db_utils import (
    get_related_observations,
    search_propositions_bm25,
    get_recent_propositions,
    get_recent_observations,
)
from .models import Observation, Proposition, init_db
from .observers import Observer
from .schemas import (
    PropositionItem,
    PropositionSchema,
    RelationSchema,
    Update,
    get_schema,
    AuditSchema
)
from gum.prompts.gum import AUDIT_PROMPT, PROPOSE_PROMPT, REVISE_PROMPT, SIMILAR_PROMPT
from .batcher import ObservationBatcher

class gum:
    """A class for managing general user models.

    This class provides functionality for observing user behavior, generating and managing
    propositions about user behavior, and maintaining relationships between observations
    and propositions.

    Args:
        user_name (str): The name of the user being modeled.
        *observers (Observer): Variable number of observer instances to track user behavior.
        propose_prompt (str, optional): Custom prompt for proposition generation.
        similar_prompt (str, optional): Custom prompt for similarity analysis.
        revise_prompt (str, optional): Custom prompt for proposition revision.
        audit_prompt (str, optional): Custom prompt for auditing.
        data_directory (str, optional): Directory for storing data. Defaults to "~/.cache/gum".
        db_name (str, optional): Name of the database file. Defaults to "gum.db".

        verbosity (int, optional): Logging verbosity level. Defaults to logging.INFO.
        audit_enabled (bool, optional): Whether to enable auditing. Defaults to False.
    """

    def __init__(
        self,
        user_name: str,
        model: str,
        *observers: Observer,
        propose_prompt: str | None = None,
        similar_prompt: str | None = None,
        revise_prompt: str | None = None,
        audit_prompt: str | None = None,
        data_directory: str = "~/.cache/gum",
        db_name: str = "gum.db",
        verbosity: int = logging.INFO,
        audit_enabled: bool = False,
        api_base: str | None = None,
        api_key: str | None = None,
        min_batch_size: int = 5,
        max_batch_size: int = 50,
        max_wait_seconds: float = 30.0,
    ):
        # basic paths
        data_directory = os.path.expanduser(data_directory)
        os.makedirs(data_directory, exist_ok=True)

        # runtime
        self.user_name = user_name
        self.observers: list[Observer] = list(observers)
        self.model = model
        self.audit_enabled = audit_enabled

        # batching configuration
        self.min_batch_size = min_batch_size
        self.max_batch_size = max_batch_size
        self.max_wait_seconds = max_wait_seconds

        # logging
        self.logger = logging.getLogger("gum")
        self.logger.setLevel(verbosity)
        if not self.logger.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            self.logger.addHandler(h)

        # prompts
        self.propose_prompt = propose_prompt or PROPOSE_PROMPT
        self.similar_prompt = similar_prompt or SIMILAR_PROMPT
        self.revise_prompt = revise_prompt or REVISE_PROMPT
        self.audit_prompt = audit_prompt or AUDIT_PROMPT

        self.client = AsyncOpenAI(
            base_url=api_base or os.getenv("GUM_LM_API_BASE"), 
            api_key=api_key or os.getenv("GUM_LM_API_KEY") or os.getenv("OPENAI_API_KEY") or "None"
        )

        self.engine = None
        self.Session = None
        self._db_name        = db_name
        self._data_directory = data_directory

        # Initialize batcher if enabled
        self.batcher = ObservationBatcher(
            data_directory=data_directory,
            min_batch_size=min_batch_size,
            max_batch_size=max_batch_size,
            max_wait_seconds=max_wait_seconds,
        )

        self._loop_task: asyncio.Task | None = None
        self._batch_task: asyncio.Task | None = None
        self._batch_processing_lock = asyncio.Lock()
        self.update_handlers: list[Callable[[Observer, Update], None]] = [self._default_handler]

    def start_update_loop(self):
        """Start the asynchronous update loop for processing observer updates."""
        if self._loop_task is None:
            self._loop_task = asyncio.create_task(self._update_loop())
            
        # Start batch processing if enabled
        if self._batch_task is None:
            self._batch_task = asyncio.create_task(self._batch_processing_loop())

    async def stop_update_loop(self):
        """Stop the asynchronous update loop and clean up resources."""
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
            
        # Stop batch processing if enabled
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
            self._batch_task = None
            
        if self.batcher:
            await self.batcher.stop()

    async def connect_db(self):
        """Initialize the database connection if not already connected."""
        if self.engine is None:
            self.engine, self.Session = await init_db(
                self._db_name, self._data_directory
            )

    async def __aenter__(self):
        """Async context manager entry point.
        
        Returns:
            gum: The instance of the gum class.
        """
        await self.connect_db()
        self.start_update_loop()
        
        # Start batcher if enabled
        if self.batcher:
            await self.batcher.start()
            
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Async context manager exit point.
        
        Args:
            exc_type: The type of exception if any.
            exc: The exception instance if any.
            tb: The traceback if any.
        """
        await self.stop_update_loop()

        # stop observers
        for obs in self.observers:
            await obs.stop()

    async def _update_loop(self):
        """Efficiently wait for any observer to produce an Update and dispatch it.
        
        This method continuously monitors all observers for updates and processes them
        through the semaphore-guarded handler.
        """
        if not self.observers:
            # If no native observers, sleep forever. 
            # External updates will be pushed directly to the batcher.
            await asyncio.Future()
            return
            
        while True:
            gets = {
                asyncio.create_task(obs.update_queue.get()): obs
                for obs in self.observers
            }

            done, _ = await asyncio.wait(
                gets.keys(), return_when=asyncio.FIRST_COMPLETED
            )

            for fut in done:
                upd: Update = fut.result()
                obs = gets[fut]

                for handler in self.update_handlers:
                    asyncio.create_task(handler(obs, upd))

    async def _batch_processing_loop(self):
        """Process batched observations when minimum batch size is reached."""
        while True:
            # Process full batches immediately, but do not leave a small
            # durable queue waiting forever for more observations.
            try:
                await asyncio.wait_for(
                    self.batcher.wait_for_batch_ready(),
                    timeout=self.batcher.max_wait_seconds,
                )
            except asyncio.TimeoutError:
                if self.batcher.size() == 0:
                    continue
            
            # Use lock to ensure batch processing runs synchronously
            async with self._batch_processing_lock:
                batch = self.batcher.pop_batch()
                observer_names = [obs.get('observer_name', 'Unknown') for obs in batch]
                # self.logger.info(f"Processing batch of {len(batch)} observations from observers: {', '.join(observer_names)}")
                self.logger.debug(f"Processing batch of {len(batch)} observations from observers: {', '.join(observer_names)}")
                await self._process_batch(batch)

    async def flush_pending_observations(self) -> int:
        """Process a partial durable batch at an explicit session boundary."""
        async with self._batch_processing_lock:
            batch = self.batcher.pop_batch()
            if not batch:
                return 0
            try:
                await self._process_batch(batch)
            except Exception:
                self.batcher.restore_batch(batch)
                raise
            return len(batch)

    async def _process_batch(self, batched_observations):
        """Process a batch of observations together to reduce API calls."""
        try:
            async with self._session() as session:
                # Create observations in database
                observations = []
                for obs in batched_observations:
                    observation = Observation(
                        observer_name=obs['observer_name'],
                        content=obs['content'],
                        content_type=obs['content_type'],
                        user_id=obs.get('user_id', 'default_user')
                    )
                    session.add(observation)
                    observations.append(observation)
                
                await session.flush()
                
                # Process the batched observations directly to support multimodality
                pool = await self._generate_and_search(session, batched_observations)
                identical, similar, different = await self._filter_propositions(pool)

                # self.logger.info("Applying proposition updates for batch...")
                self.logger.debug("Applying proposition updates for batch...")
                await self._handle_identical(session, identical, observations)
                await self._handle_similar(session, similar, observations)
                await self._handle_different(session, different, observations)
                
                # Observations are already removed from queue by pop_batch()
                # self.logger.info(f"Completed processing batch of {len(batched_observations)} observations")
                self.logger.debug(f"Completed processing batch of {len(batched_observations)} observations")
                
        except Exception as e:
            self.logger.error(f"Error processing batch: {e}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            self.logger.error(f"Batch size: {len(batched_observations)}")
            if batched_observations:
                self.logger.error(f"First observation type: {type(batched_observations[0])}")
                self.logger.error(f"First observation: {batched_observations[0]}")
            
            import openai
            import sqlite3
            import sqlalchemy.exc
            
            err_msg_lower = str(e).lower()
            if isinstance(e, openai.AuthenticationError):
                self.logger.error("Authentication Error encountered! Discarding batch to prevent infinite loop.")
            elif isinstance(e, (sqlite3.OperationalError, sqlalchemy.exc.OperationalError)) and ("disk i/o error" in err_msg_lower or "i/o error" in err_msg_lower):
                self.logger.error("Caught Disk I/O Error in background loop. Disposing engine and DROPPING batch to prevent infinite loop...")
                try:
                    if hasattr(self, "engine") and self.engine:
                        await self.engine.dispose()
                except Exception as ex:
                    self.logger.error(f"Failed to dispose engine: {ex}")
                # We DO NOT requeue here! We drop it to break the loop.
            else:
                # Put failed items back in queue for retry
                for obs in batched_observations:
                    self.batcher.push(obs['observer_name'], obs['content'], obs['content_type'])

    async def _construct_propositions(self, batched_observations: list[dict]) -> list[PropositionItem]:
        """Generate propositions from batched observations, supporting multimodal inputs.
        
        Args:
            batched_observations (list[dict]): The batched observations.
            
        Returns:
            list[PropositionItem]: List of generated propositions.
        """
        # Build text part of the prompt
        text_contents = []
        image_contents = []
        for obs in batched_observations:
            if obs['content_type'] == 'input_image':
                self.logger.info(f"[Image Debug] Got image observation. String length: {len(obs['content'])}")
                self.logger.info(f"[Image Debug] Image preview (first 100 chars): {obs['content'][:100]}")
                # Check if it has lots of AAAAA which indicates empty image
                a_count = obs['content'].count('A')
                self.logger.info(f"[Image Debug] 'A' character count in string: {a_count} ({(a_count/len(obs['content'])*100):.1f}% of total). High percentage means blank image.")
                
                # Base64 image
                image_contents.append({
                    "type": "image_url",
                    "image_url": {
                        "url": obs['content']
                    }
                })
            else:
                text_contents.append(f"[{obs['observer_name']}] {obs['content']}")
                
        combined_text = "\n\n".join(text_contents)
        
        prompt_text = (
            self.propose_prompt.replace("{user_name}", self.user_name)
            .replace("{inputs}", combined_text)
        )
        
        if image_contents:
            prompt_text += "\n\nPlease analyze the attached screen capture images to infer what the user is currently doing."
            message_content = [{"type": "text", "text": prompt_text}] + image_contents
        else:
            message_content = prompt_text

        schema = PropositionSchema.model_json_schema()
        rsp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": message_content}],
            response_format=get_schema(schema),
        )

        try:
            return json.loads(rsp.choices[0].message.content)["propositions"]
        except json.JSONDecodeError:
            fallback_text = combined_text[:1200]
            return [{
                "proposition": fallback_text,
                "reasoning": "Fallback proposition created because the model returned malformed JSON.",
                "context_scope": "system_observation",
                "event_types": ["observation"],
                "target": self.user_name,
                "functional_type_seeds": ["memory"],
                "confidence": 1,
                "decay": 5,
            }]

    async def _build_relation_prompt(self, all_props) -> str:
        """Build a prompt for analyzing relationships between propositions.
        
        Args:
            all_props: List of propositions to analyze.
            
        Returns:
            str: The formatted prompt for relationship analysis.
        """
        blocks = [
            f"[id={p['id']}] {p['proposition']}\n    Reasoning: {p['reasoning']}"
            for p in all_props
        ]
        body = "\n\n".join(blocks)
        return self.similar_prompt.replace("{body}", body)

    async def _filter_propositions(
        self, rel_props: list[Proposition]
    ) -> tuple[list[Proposition], list[Proposition], list[Proposition]]:
        """Filter propositions into identical, similar, and unrelated groups.
        
        Args:
            rel_props (list[Proposition]): List of propositions to filter.
            
        Returns:
            tuple[list[Proposition], list[Proposition], list[Proposition]]: Three lists containing
                identical, similar, and unrelated propositions respectively.
        """
        if not rel_props:
            return [], [], []

        payload = [
            {"id": p.id, "proposition": p.text, "reasoning": p.reasoning or ""}
            for p in rel_props
        ]
        prompt_text = await self._build_relation_prompt(payload)

        rsp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt_text}],
            response_format=get_schema(RelationSchema.model_json_schema()),
        )

        data = RelationSchema.model_validate_json(rsp.choices[0].message.content)

        id_to_prop = {p.id: p for p in rel_props}
        ident, sim, unrel = set(), set(), set()

        for r in data.relations:
            if r.label == "IDENTICAL":
                ident.add(r.source)
                ident.update(r.target or [])
            elif r.label == "SIMILAR":
                sim.add(r.source)
                sim.update(r.target or [])
            else:
                unrel.add(r.source)

        # only keep IDs we actually know about
        valid_ids = set(id_to_prop.keys())
        ident &= valid_ids
        sim &= valid_ids
        unrel &= valid_ids

        return (
            [id_to_prop[i] for i in ident],
            [id_to_prop[i] for i in sim - ident],
            [id_to_prop[i] for i in unrel - ident - sim],
        )

    async def _build_revision_body(
        self, similar: List[Proposition], related_obs: List[Observation]
    ) -> str:
        """Build the body text for proposition revision.
        
        Args:
            similar (List[Proposition]): List of similar propositions.
            related_obs (List[Observation]): List of related observations.
            
        Returns:
            str: The formatted body text for revision.
        """
        blocks = [
            f"Proposition {idx}: {p.text}\nReasoning: {p.reasoning}"
            for idx, p in enumerate(similar, 1)
        ]
        if related_obs:
            blocks.append("\nSupporting observations:")
            blocks.extend(f"- {o.content}" for o in related_obs[:10])
        return "\n".join(blocks)

    async def _revise_propositions(
        self,
        related_obs: list[Observation],
        similar_cluster: list[Proposition],
    ) -> list[dict]:
        """Revise propositions based on related observations and similar propositions.
        
        Args:
            related_obs (list[Observation]): List of related observations.
            similar_cluster (list[Proposition]): List of similar propositions.
            
        Returns:
            list[dict]: List of revised propositions.
        """
        body = await self._build_revision_body(similar_cluster, related_obs)
        prompt = self.revise_prompt.replace("{body}", body).replace("{user_name}", self.user_name)
        rsp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format=get_schema(PropositionSchema.model_json_schema()), 
        )
        try:
            return json.loads(rsp.choices[0].message.content)["propositions"]
        except json.JSONDecodeError:
            fallback_text = " ".join(o.content for o in related_obs[:10])[:1200]
            return [{
                "proposition": fallback_text,
                "reasoning": "Fallback revision created because the model returned malformed JSON.",
                "context_scope": "system_observation",
                "event_types": ["observation"],
                "target": self.user_name,
                "functional_type_seeds": ["memory"],
                "confidence": 1,
                "decay": 5,
            }]

    async def _generate_and_search(
        self, session: AsyncSession, batched_observations: list[dict]
    ) -> list[Proposition]:

        drafts_raw = await self._construct_propositions(batched_observations)
        batch_user_id = batched_observations[0].get("user_id", self.user_name) if batched_observations else self.user_name
        drafts: list[Proposition] = []
        pool: dict[int, Proposition] = {}

        for itm in drafts_raw:
            draft = Proposition(
                text=itm["proposition"],
                reasoning=itm["reasoning"],
                context_scope=itm.get("context_scope"),
                event_types=json.dumps(itm.get("event_types", [])) if itm.get("event_types") else None,
                target=itm.get("target"),
                functional_type_seeds=json.dumps(itm.get("functional_type_seeds", [])) if itm.get("functional_type_seeds") else None,
                confidence=itm.get("confidence"),
                decay=itm.get("decay"),
                user_id=batch_user_id,
                revision_group=str(uuid4()),
                version=1,
            )
            drafts.append(draft)

            # search existing persisted props
            with session.no_autoflush:
                hits = await search_propositions_bm25(
                    session, f"{draft.text}\n{draft.reasoning}", mode="OR",
                    include_observations=False,
                    enable_mmr=False,
                    enable_decay=True,
                    include_deleted=True,
                    user_id=batch_user_id,
                )
                
            for prop, _score in hits:
                pool[prop.id] = prop

        session.add_all(drafts)
        await session.flush()

        for draft in drafts:
            pool[draft.id] = draft

        return list(pool.values())

    async def _handle_identical(
        self, session, identical: list[Proposition], observations: list[Observation]
    ) -> None:
        from datetime import datetime, timezone, timedelta
        for p in identical:
            if p.status == 'deleted':
                try:
                    if isinstance(p.updated_at, str):
                        try:
                            dt = datetime.fromisoformat(p.updated_at.replace('Z', '+00:00'))
                        except ValueError:
                            dt = datetime.strptime(p.updated_at, "%Y-%m-%d %H:%M:%S")
                            dt = dt.replace(tzinfo=timezone.utc)
                    elif isinstance(p.updated_at, datetime):
                        dt = p.updated_at
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = datetime.min.replace(tzinfo=timezone.utc)
                        
                    if (datetime.now(timezone.utc) - dt) > timedelta(minutes=5):
                        p.status = 'active'
                except Exception as e:
                    self.logger.warning(f"Could not parse updated_at {p.updated_at}: {e}")
                    p.status = 'active'
                    
            for obs in observations:
                await self._attach_obs_if_missing(p, obs, session)

    async def _handle_similar(
        self,
        session: AsyncSession,
        similar: list[Proposition],
        observations: list[Observation],
    ) -> None:

        if not similar:
            return

        # Collect all observations from similar propositions
        rel_obs = {
            o
            for p in similar
            for o in await get_related_observations(session, p.id)
        }
        # Add all the batched observations
        rel_obs.update(observations)

        # Generate revised propositions
        revised_items = await self._revise_propositions(list(rel_obs), similar)
        
        # Delete all old similar propositions
        for prop in similar:
            await session.delete(prop)
        
        # Create new propositions to replace them
        revision_group = str(uuid4())
        batch_user_id = observations[0].user_id if observations else self.user_name
        for item in revised_items:
            new_prop = Proposition(
                text=item["proposition"],
                reasoning=item["reasoning"],
                context_scope=item.get("context_scope"),
                event_types=json.dumps(item.get("event_types", [])) if item.get("event_types") else None,
                target=item.get("target"),
                functional_type_seeds=json.dumps(item.get("functional_type_seeds", [])) if item.get("functional_type_seeds") else None,
                confidence=item.get("confidence"),
                decay=item.get("decay"),
                user_id=batch_user_id,
                version=1,  # Start fresh with version 1
                revision_group=revision_group,
                observations=set(rel_obs),
            )
            session.add(new_prop)

        await session.flush()

    async def _handle_different(
        self, session, different: list[Proposition], observations: list[Observation]
    ) -> None:
        for p in different:
            for obs in observations:
                await self._attach_obs_if_missing(p, obs, session)

    async def _handle_audit(self, obs: Observation) -> bool:
        if not self.audit_enabled:
            return False

        hits = await self.query(obs.content, limit=10, mode="OR")

        if not hits:
            past_interaction = "*None*"
        else:
            ctx_chunks: list[str] = []
            async with self._session() as session:
                for prop, score in hits:
                    chunk = [f"• {prop.text}"]
                    if prop.reasoning:
                        chunk.append(f"  Reasoning: {prop.reasoning}")
                    if prop.confidence is not None:
                        chunk.append(f"  Confidence: {prop.confidence}")
                    chunk.append(f"  Relevance Score: {score:.2f}")

                    obs_list = await get_related_observations(session, prop.id)
                    if obs_list:
                        chunk.append("  Supporting Observations:")
                        for rel_obs in obs_list:
                            preview = rel_obs.content.replace("\n", " ")[:120]
                            chunk.append(f"    - [{rel_obs.observer_name}] {preview}")

                    ctx_chunks.append("\n".join(chunk))

            past_interaction = "\n\n".join(ctx_chunks)

        prompt = (
            self.audit_prompt
            .replace("{past_interaction}", past_interaction)
            .replace("{user_input}", obs.content)
            .replace("{user_name}", self.user_name)
        )

        rsp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format=get_schema(AuditSchema.model_json_schema()),
            temperature=0.0,
        )
        decision = json.loads(rsp.choices[0].message.content)

        if not decision["transmit_data"]:
            self.logger.warning(
                "Audit blocked transmission (data_type=%s, subject=%s)",
                decision["data_type"],
                decision["subject"],
            )
            return True

        return False

    async def _default_handler(self, observer: Observer, update: Update) -> None:
        self.logger.info(f"Processing update from {observer.name}")

        # add to batch
        observation_id = self.batcher.push(
            observer_name=observer.name,
            content=update.content,
            content_type=update.content_type,
            user_id=update.user_id
        )
        self.logger.info(f"Added observation {observation_id} to queue (size: {self.batcher.size()})")

    @asynccontextmanager
    async def _session(self):
        async with self.Session() as s:
            async with s.begin():
                yield s

    @staticmethod
    async def _attach_obs_if_missing(prop: Proposition, obs: Observation, session):
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        bind = session.bind or session.sync_session.bind
        is_pg = getattr(bind.dialect, "name", "") == "postgresql" if bind else True

        if is_pg:
            stmt = pg_insert(observation_proposition).values(observation_id=obs.id, proposition_id=prop.id).on_conflict_do_nothing()
        else:
            stmt = sqlite_insert(observation_proposition).prefix_with("OR IGNORE").values(observation_id=obs.id, proposition_id=prop.id)
            
        await session.execute(stmt)
        await session.execute(
            update(Proposition)
            .where(Proposition.id == prop.id)
            .values(updated_at=func.now())
        )

    def add_observer(self, observer: Observer):
        """Add an observer to track user behavior.
        
        Args:
            observer (Observer): The observer to add.
        """
        self.observers.append(observer)

    def remove_observer(self, observer: Observer):
        """Remove an observer from tracking.
        
        Args:
            observer (Observer): The observer to remove.
        """
        if observer in self.observers:
            self.observers.remove(observer)

    def register_update_handler(self, fn: Callable[[Observer, Update], None]):
        """Register a custom update handler function.
        
        Args:
            fn (Callable[[Observer, Update], None]): The handler function to register.
        """
        self.update_handlers.append(fn)

    async def query(
        self,
        user_query: str,
        *,
        user_id: str = "default_user",
        limit: int = 3,
        mode: str = "OR",
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[tuple[Proposition, float]]:
        """Query the database for propositions matching the user query.
        
        Args:
            user_query (str): The query string to search for.
            limit (int, optional): Maximum number of results to return. Defaults to 3.
            mode (str, optional): Search mode ("OR" or "AND"). Defaults to "OR".
            start_time (datetime, optional): Start time for filtering results. Defaults to None.
            end_time (datetime, optional): End time for filtering results. Defaults to None.
            
        Returns:
            list[tuple[Proposition, float]]: List of tuples containing propositions and their relevance scores.
        """
        from sqlalchemy import select
        from .schemas import IntentPredictionSchema
        from gum.prompts.gum import INTENT_SELECTION_PROMPT

        async with self._session() as session:
            # 1. Collect unique label candidates from existing propositions
            stmt = select(
                Proposition.context_scope, 
                Proposition.event_types, 
                Proposition.target, 
                Proposition.functional_type_seeds
            ).where(Proposition.status == 'active', Proposition.user_id == user_id).order_by(Proposition.created_at.desc()).limit(200)
            
            result = await session.execute(stmt)
            rows = result.fetchall()
            
            context_scopes = set()
            event_types = set()
            targets = set()
            functional_type_seeds = set()
            
            for row in rows:
                if row.context_scope: context_scopes.add(row.context_scope)
                if row.target: targets.add(row.target)
                if row.event_types:
                    try:
                        for et in json.loads(row.event_types):
                            event_types.add(et)
                    except Exception: pass
                if row.functional_type_seeds:
                    try:
                        for ft in json.loads(row.functional_type_seeds):
                            functional_type_seeds.add(ft)
                    except Exception: pass

            # 2. Call LLM for intent prediction if we have candidates
            selected_labels = None
            if any([context_scopes, event_types, targets, functional_type_seeds]):
                if not hasattr(self, '_intent_cache'):
                    from collections import OrderedDict
                    class SimpleLRU:
                        def __init__(self, size=100):
                            self.cache = OrderedDict()
                            self.size = size
                        def get(self, key):
                            if key in self.cache:
                                self.cache.move_to_end(key)
                                return self.cache[key]
                            return None
                        def put(self, key, val):
                            self.cache[key] = val
                            self.cache.move_to_end(key)
                            if len(self.cache) > self.size:
                                self.cache.popitem(last=False)
                    self._intent_cache = SimpleLRU()

                selected_labels = self._intent_cache.get(user_query)
                if selected_labels is None:
                    # self.logger.info("[STITCH] Intent Cache Miss. Querying LLM for intent prediction...")
                    self.logger.debug("[STITCH] Intent Cache Miss. Querying LLM for intent prediction...")
                    prompt = INTENT_SELECTION_PROMPT.format(
                        user_query=user_query,
                        context_scope_candidates=json.dumps(list(context_scopes)[:50], ensure_ascii=False),
                        event_type_candidates=json.dumps(list(event_types)[:50], ensure_ascii=False),
                        target_candidates=json.dumps(list(targets)[:50], ensure_ascii=False),
                        functional_type_seeds_candidates=json.dumps(list(functional_type_seeds)[:50], ensure_ascii=False)
                    )
                    
                    rsp = await self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        response_format=get_schema(IntentPredictionSchema.model_json_schema()),
                    )
                    selected_labels = json.loads(rsp.choices[0].message.content)
                    self._intent_cache.put(user_query, selected_labels)
                    # self.logger.info(f"[STITCH] Predicted Labels: {json.dumps(selected_labels, ensure_ascii=False)}")
                    self.logger.debug(f"[STITCH] Predicted Labels: {json.dumps(selected_labels, ensure_ascii=False)}")
                else:
                    # self.logger.info(f"[STITCH] Intent Cache Hit. Using cached labels for query: '{user_query}'")
                    self.logger.debug(f"[STITCH] Intent Cache Hit. Using cached labels for query: '{user_query}'")

            # 3. Perform BM25 search with Density Ranking
            return await search_propositions_bm25(
                session,
                user_query,
                user_id=user_id,
                selected_labels=selected_labels,
                limit=limit,
                mode=mode,
                start_time=start_time,
                end_time=end_time,
            )

    async def recent(
        self,
        *,
        user_id: str = "default_user",
        limit: int = 10,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        include_observations: bool = False,
    ) -> list[Proposition]:
        """Return the most recent propositions ordered by created_at descending."""
        async with self._session() as session:
            return await get_recent_propositions(
                session,
                user_id=user_id,
                limit=limit,
                start_time=start_time,
                end_time=end_time,
                include_observations=include_observations,
            )

    async def recent_observations(
        self,
        *,
        user_id: str = "default_user",
        limit: int = 10,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[Observation]:
        """Return the most recent observations ordered by created_at descending."""
        async with self._session() as session:
            return await get_recent_observations(
                session,
                user_id=user_id,
                limit=limit,
                start_time=start_time,
                end_time=end_time,
            )

    async def update_status(self, proposition_id: int, status: str):
        """Update the status of a proposition (e.g. active, superseded, archived)."""
        async with self._session() as session:
            await session.execute(
                update(Proposition)
                .where(Proposition.id == proposition_id)
                .values(status=status, updated_at=func.now())
            )
            await session.commit()

    async def update_text(self, proposition_id: int, new_text: str):
        """Update the text of a proposition."""
        async with self._session() as session:
            await session.execute(
                update(Proposition)
                .where(Proposition.id == proposition_id)
                .values(text=new_text, updated_at=func.now())
            )
            await session.commit()

    async def update_observation_status(self, observation_id: int, status: str):
        """Update the status of an observation."""
        async with self._session() as session:
            await session.execute(
                update(Observation)
                .where(Observation.id == observation_id)
                .values(status=status, updated_at=func.now())
            )
