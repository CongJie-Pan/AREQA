"""Topic Finder topic card: model rules, storage (SQLite), extraction, prompt, and API."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.conversation import topic_card
from services.conversation.topic_card import (
    COMPLETED_STAGE, MAX_PROMPT_CHARS, CardPatch, DiscardedTopic, OperationalTerm, TopicCard,
    TopicCardState, TopicCardStore, TopicCardUnavailable, apply_patch, confirm_stage,
    extract_card_patch, load_card_prompt, refresh_pending_card, render_card_prompt, with_pending,
)

PRIVATE = "我的私密痛點內容"


@pytest_asyncio.fixture
async def storage(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cards.db'}", hide_parameters=True)
    owner, other, conversation = str(uuid4()), str(uuid4()), str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE conversations (id TEXT PRIMARY KEY, user_id TEXT)"))
        await connection.execute(text("""CREATE TABLE research_topic_cards (
            user_id TEXT, conversation_id TEXT, stage INTEGER, version INTEGER,
            card TEXT, pending TEXT, history TEXT, updated_at INTEGER,
            PRIMARY KEY (user_id, conversation_id))"""))
        await connection.execute(text("INSERT INTO conversations VALUES (:id, :user)"), {"id": conversation, "user": owner})
    yield TopicCardStore(engine), owner, other, conversation
    await engine.dispose()


def _patch(**kwargs):
    return CardPatch(change_note="更新", **kwargs)


# --- Unit: patch validation ----------------------------------------------------------------


def test_card_patch_accepts_valid_proposal():
    patch_ = CardPatch.model_validate({
        "pain_point": "系統和 Gemini 差不多", "candidates": ["A", "B"],
        "operationalization": [{"term": "思辨", "measure": ""}],
        "discarded_add": [{"topic": "記憶", "filter": 1, "reason": "技術會解決", "can_return": True}],
        "objections_add": ["一直被問會煩"], "change_note": "加入痛點",
    })
    assert patch_.discarded_add[0].filter == 1


@pytest.mark.parametrize("payload", [
    {"unknown": 1},
    {"pain_point": "x" * 301},
    {"candidates": "not a list"},
    {"discarded_add": [{"topic": "x", "filter": 9}]},
    {"operationalization": [{"term": ""}]},
    {"objections_add": ["x"] * 6},
])
def test_card_patch_rejects_invalid_proposals(payload):
    with pytest.raises(ValidationError):
        CardPatch.model_validate(payload)


# --- Unit: confirm logic --------------------------------------------------------------------


def test_proposals_never_change_stage_or_version():
    state = with_pending(TopicCardState(), _patch(pain_point=PRIVATE))
    state = with_pending(state, _patch(candidates=["題目 A"]))

    assert (state.stage, state.version) == (0, 0)
    assert state.card == TopicCard()
    assert state.pending.card.pain_point == PRIVATE
    assert state.pending.card.candidates == ["題目 A"]
    assert state.pending.notes == ["更新", "更新"]


def test_empty_proposal_keeps_state():
    state = TopicCardState()
    assert with_pending(state, CardPatch(change_note="nothing")) is state


def test_confirm_adopts_draft_advances_and_records_history():
    state = with_pending(TopicCardState(), _patch(pain_point=PRIVATE))
    confirmed = confirm_stage(state, now=100)

    assert (confirmed.stage, confirmed.version) == (1, 1)
    assert confirmed.card.pain_point == PRIVATE
    assert confirmed.pending is None
    assert confirmed.history[-1].model_dump() == {"version": 1, "stage": 1, "note": "更新", "confirmed_at": 100}


def test_confirm_does_not_go_past_completion():
    state = TopicCardState()
    for _ in range(COMPLETED_STAGE):
        state = confirm_stage(state)
    assert state.stage == COMPLETED_STAGE
    assert confirm_stage(state) is state


def test_apply_patch_dedupes_and_bounds_lists():
    card = TopicCard(discarded=[DiscardedTopic(topic="記憶", filter=1)], objections=["a"])
    result = apply_patch(card, CardPatch(
        discarded_add=[DiscardedTopic(topic="記憶", filter=2), DiscardedTopic(topic="沉默期", filter=1)],
        objections_add=["a", "b"], candidates=[" X ", "X", "Y"],
    ))
    assert [item.topic for item in result.discarded] == ["記憶", "沉默期"]
    assert result.discarded[0].filter == 1
    assert result.objections == ["a", "b"]
    assert result.candidates == ["X", "Y"]


# --- Unit: prompt and stage rules ------------------------------------------------------------


@pytest.mark.parametrize("stage", range(0, COMPLETED_STAGE + 1))
def test_prompt_shows_only_the_current_stage_focus(stage):
    prompt = render_card_prompt(TopicCardState(stage=stage))
    assert topic_card.STAGE_FOCUS[stage] in prompt
    for other, focus in topic_card.STAGE_FOCUS.items():
        if other != stage:
            assert focus not in prompt
    assert "你不能宣告過關" in prompt


def test_prompt_marks_missing_measures_and_is_bounded():
    card = TopicCard(
        pain_point="p" * 300, mother_question="q" * 400, candidates=["c" * 200] * 8,
        operationalization=[OperationalTerm(term=f"t{i}", measure="") for i in range(12)],
        discarded=[DiscardedTopic(topic="d" * 200, filter=1, reason="r" * 300) for _ in range(20)],
        objections=["o" * 300] * 20,
    )
    prompt = render_card_prompt(TopicCardState(stage=4, card=card))
    assert len(prompt) <= MAX_PROMPT_CHARS
    assert render_card_prompt(None) == ""
    assert "❗尚未填" in render_card_prompt(TopicCardState(card=TopicCard(operationalization=[OperationalTerm(term="x")])))


def test_prompt_uses_pending_draft():
    state = with_pending(TopicCardState(), _patch(pain_point="草稿痛點"))
    assert "草稿痛點" in render_card_prompt(state)


# --- Unit: extraction -----------------------------------------------------------------------


def _client(content=None, error=None):
    create = AsyncMock(side_effect=error) if error else AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.mark.asyncio
async def test_extraction_returns_validated_patch_with_bounded_context():
    client = _client(json.dumps({"pain_point": PRIVATE, "change_note": "痛點"}))
    messages = [{"role": "user", "content": "x" * 5000}, {"role": "user", "content": [{"type": "file"}]}]

    patch_ = await extract_card_patch(client, "m", TopicCard(), messages, "answer")

    assert patch_.pain_point == PRIVATE
    sent = json.loads(client.chat.completions.create.call_args.kwargs["messages"][1]["content"])
    assert all(len(turn["content"]) <= 1500 for turn in sent["turns"])
    assert client.chat.completions.create.call_args.kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
@pytest.mark.parametrize("client", [
    _client(error=TimeoutError()),
    _client(content="not json " + PRIVATE),
    _client(content=json.dumps({"stage": 6})),
])
async def test_extraction_failure_returns_none_and_logs_safely(client, caplog):
    with caplog.at_level(logging.INFO):
        assert await extract_card_patch(client, "m", TopicCard(), [{"role": "user", "content": PRIVATE}], "a") is None
    assert "topic_card.extraction_failed" in caplog.text
    assert PRIVATE not in caplog.text


# --- Integration: storage ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_round_trip_propose_and_confirm(storage):
    store, owner, _other, conversation = storage

    assert await store.load(owner, conversation) == TopicCardState()
    await store.propose(owner, conversation, _patch(pain_point=PRIVATE))
    loaded = await store.load(owner, conversation)
    assert (loaded.stage, loaded.version, loaded.pending.card.pain_point) == (0, 0, PRIVATE)

    state, advanced = await store.confirm(owner, conversation, expected_version=0)
    assert advanced and (state.stage, state.version, state.card.pain_point) == (1, 1, PRIVATE)
    again, advanced_again = await store.confirm(owner, conversation, expected_version=0)
    assert not advanced_again and (again.stage, again.version) == (1, 1)
    assert (await store.load(owner, conversation)).history[-1].version == 1


@pytest.mark.asyncio
async def test_store_isolates_owners_and_rejects_bad_ids(storage):
    store, owner, other, conversation = storage
    await store.propose(owner, conversation, _patch(pain_point=PRIVATE))

    assert await store.load(other, conversation) is None
    assert await store.propose(other, conversation, _patch(pain_point="x")) is None
    assert await store.confirm(other, conversation, 0) is None
    assert await store.load(owner, "not-a-uuid") is None
    assert await store.load(f"guest:{uuid4()}", conversation) is None
    assert (await store.load(owner, conversation)).pending.card.pain_point == PRIVATE


@pytest.mark.asyncio
async def test_missing_schema_raises_unavailable_and_hides_private_data(tmp_path, caplog):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}", hide_parameters=True)
    store = TopicCardStore(engine)
    owner, conversation = str(uuid4()), str(uuid4())
    try:
        with pytest.raises(TopicCardUnavailable):
            await store.propose(owner, conversation, _patch(pain_point=PRIVATE))
        with pytest.raises(TopicCardUnavailable):
            await store.load(owner, conversation)
        assert "topic_card.storage_unavailable operation=propose error_type=OperationalError" in caplog.text
        assert PRIVATE not in caplog.text and owner not in caplog.text
        assert await load_card_prompt(owner, conversation, store) == ""
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_refresh_pending_card_stores_proposal_without_advancing(storage, caplog):
    store, owner, _other, conversation = storage
    client = _client(json.dumps({"candidates": ["AI 回覆如何影響思辨"], "change_note": "候選"}))

    with caplog.at_level(logging.INFO):
        await refresh_pending_card(client=client, model="m", user_id=owner, conversation_id=conversation,
                                   messages=[{"role": "user", "content": PRIVATE}], answer="答覆", store=store)

    state = await store.load(owner, conversation)
    assert state.pending.card.candidates == ["AI 回覆如何影響思辨"]
    assert (state.stage, state.version) == (0, 0)
    assert "topic_card.pending_updated" in caplog.text and PRIVATE not in caplog.text


@pytest.mark.asyncio
async def test_refresh_skips_unowned_conversation_and_failed_extraction(storage):
    store, owner, other, conversation = storage
    client = _client(json.dumps({"pain_point": "x", "change_note": "x"}))
    await refresh_pending_card(client=client, model="m", user_id=other, conversation_id=conversation,
                               messages=[], answer="a", store=store)
    client.chat.completions.create.assert_not_called()

    await refresh_pending_card(client=_client(error=RuntimeError()), model="m", user_id=owner,
                               conversation_id=conversation, messages=[], answer="a", store=store)
    assert (await store.load(owner, conversation)).pending is None


@pytest.mark.asyncio
async def test_card_prompt_reflects_confirmed_stage(storage):
    store, owner, _other, conversation = storage
    await store.confirm(owner, conversation, 0)
    await store.confirm(owner, conversation, 1)

    prompt = await load_card_prompt(owner, conversation, store)
    assert "篩子 2/5：最簡方案" in prompt
    assert topic_card.STAGE_FOCUS[2] in prompt


# --- Integration: context builder and completion hook -------------------------------------


@pytest.mark.asyncio
async def test_coach_context_includes_card_prompt_and_chat_does_not():
    from backend.services.conversation_context_service import ConversationContextService

    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(allow_long_term_query=False)
    service = ConversationContextService(memory_policy=memory_policy, memory_query_tool=AsyncMock())

    async def build(profile):
        result = await service.build_conversation_context(
            user_id="u", conversation_id="c", messages=[{"role": "user", "content": "hi"}],
            use_rag=False, use_web_search=False, force_think=False, context_results_obj=None,
            last_user_msg="hi", context_prompt="", client=None, snapshot_loader=AsyncMock(return_value=""),
            store=None, chat_avatar_key="k", tutor_profile=profile,
        )
        return result.messages[0]["content"]

    loader = AsyncMock(return_value="\n【選題題目卡（測試）】")
    with patch("services.conversation.context.load_card_prompt", loader):
        coach, chat = await build("research_coach"), await build("general")
    assert "【選題題目卡（測試）】" in coach
    assert "選題題目卡" not in chat
    loader.assert_awaited_once_with("u", "c")


async def _complete(topic_finder):
    from services.orchestration.completion import complete_answer

    async def no_events(*_args, **_kwargs):
        return
        yield

    service = SimpleNamespace(client=object(), _node_post_generation=no_events)
    session = SimpleNamespace(context=SimpleNamespace(run_id="r"), state=SimpleNamespace(),
                              transport=SimpleNamespace(encode_legacy=lambda event, _run: event))
    with patch("services.conversation.topic_card.schedule_card_refresh") as scheduled:
        events = [event async for event in complete_answer(
            service, user_id="u", conversation_id="c", last_user_msg="q", messages=[{"role": "user", "content": "q"}],
            answer_content_accumulator="answer", generated_blocks=[{"type": "text"}], planned_image_slots=[],
            response_policy=None, preverified_image_blocks=None, context_results_obj=None, use_rag=False,
            use_web_search=False, interface_language="zh-TW", session=session,
            trace=SimpleNamespace(mark=lambda _name: None), isolated_context=True,
            **({"topic_finder": True} if topic_finder else {}),
        )]
    return scheduled, events


@pytest.mark.asyncio
async def test_completion_schedules_card_refresh_only_for_topic_finder():
    scheduled, events = await _complete(topic_finder=True)
    assert any("answer_complete" in event for event in events)
    assert scheduled.call_args.kwargs["answer"] == "answer"
    assert scheduled.call_args.kwargs["conversation_id"] == "c"

    scheduled, _events = await _complete(topic_finder=False)
    scheduled.assert_not_called()


# --- Integration: API ----------------------------------------------------------------------


@pytest_asyncio.fixture
async def api(storage):
    from backend.main import app, get_current_user

    store, owner, other, conversation = storage
    current = {"user": owner}
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    with patch("app.routes.research_coach.topic_card_store", store), \
         patch("backend.app.routes.research_coach.topic_card_store", store, create=True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, current, owner, other, conversation, store
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_api_reads_and_confirms_with_version_check(api):
    client, _current, owner, _other, conversation, store = api
    await store.propose(owner, conversation, _patch(pain_point=PRIVATE))

    card = (await client.get(f"/api/v1/research-coach/{conversation}/card")).json()
    assert card["pending"]["card"]["pain_point"] == PRIVATE and card["stage"] == 0

    first = await client.post(f"/api/v1/research-coach/{conversation}/confirm", json={"version": 0})
    second = await client.post(f"/api/v1/research-coach/{conversation}/confirm", json={"version": 0})
    assert first.json()["advanced"] is True and first.json()["state"]["stage"] == 1
    assert second.json()["advanced"] is False and second.json()["state"]["version"] == 1


@pytest.mark.asyncio
async def test_api_hides_other_users_cards_and_validates_input(api):
    client, current, _owner, other, conversation, _store = api
    current["user"] = other
    assert (await client.get(f"/api/v1/research-coach/{conversation}/card")).status_code == 404
    assert (await client.post(f"/api/v1/research-coach/{conversation}/confirm", json={"version": 0})).status_code == 404
    assert (await client.post(f"/api/v1/research-coach/{conversation}/confirm", json={"version": -1})).status_code == 422


@pytest.mark.asyncio
async def test_api_requires_sign_in():
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/research-coach/{uuid4()}/card")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_api_reports_unavailable_storage(api):
    client, _current, _owner, _other, conversation, store = api
    with patch.object(store, "load", AsyncMock(side_effect=TopicCardUnavailable("x"))):
        response = await client.get(f"/api/v1/research-coach/{conversation}/card")
    assert response.status_code == 503
    assert response.json() == {"detail": "Topic card unavailable"}
