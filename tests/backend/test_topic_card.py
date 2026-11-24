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
    COMPLETED_STAGE, MAX_PROMPT_CHARS, CardPatch, DiscardedTopic, FeasibilityItem, OperationalTerm, TopicCard,
    TopicCardState, TopicCardStore, TopicCardUnavailable, adopt_draft, apply_patch,
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
        await connection.execute(text("""CREATE TABLE research_topic_card_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, conversation_id TEXT, event TEXT, source TEXT,
            stage INTEGER, version INTEGER, focus_kind TEXT, state TEXT, created_at INTEGER)"""))
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


# --- Unit: adopt logic ----------------------------------------------------------------------


def test_new_cards_start_at_stage_one_and_old_zero_stages_read_as_one():
    assert TopicCardState().stage == 1
    old = TopicCardState.model_validate({"stage": 0, "history": [{"version": 1, "stage": 0, "confirmed_at": 1}]})
    assert old.stage == 1 and old.history[0].stage == 1


def test_proposals_never_change_stage_or_version():
    state = with_pending(TopicCardState(), _patch(pain_point=PRIVATE))
    state = with_pending(state, _patch(candidates=["題目 A"]))

    assert (state.stage, state.version) == (1, 0)
    assert state.card == TopicCard()
    assert state.pending.card.pain_point == PRIVATE
    assert state.pending.card.candidates == ["題目 A"]
    assert state.pending.notes == ["更新", "更新"]


def test_empty_proposal_keeps_state():
    state = TopicCardState()
    assert with_pending(state, CardPatch(change_note="nothing")) is state


def test_adopt_merges_draft_keeps_stage_and_records_history():
    state = with_pending(TopicCardState(stage=3), _patch(pain_point=PRIVATE))
    adopted = adopt_draft(state, now=100)

    assert (adopted.stage, adopted.version) == (3, 1)
    assert adopted.card.pain_point == PRIVATE
    assert adopted.pending is None
    assert adopted.history[-1].model_dump() == {"version": 1, "stage": 3, "note": "更新", "confirmed_at": 100}


def test_adopt_without_draft_changes_nothing():
    state = TopicCardState()
    assert adopt_draft(state) is state


def test_suggestions_update_directly_without_a_draft_or_version():
    state = with_pending(TopicCardState(), CardPatch(keywords=["韓國 外交", " 韓國 外交 "], gaps=["缺口？"], related=["日韓"]))
    assert state.pending is None and state.version == 0
    assert state.suggestions.keywords == ["韓國 外交"]
    assert (state.suggestions.gaps, state.suggestions.related) == (["缺口？"], ["日韓"])
    # A later turn replaces only the lists it sends.
    state = with_pending(state, CardPatch(keywords=["South Korea hedging"]))
    assert state.suggestions.keywords == ["South Korea hedging"] and state.suggestions.gaps == ["缺口？"]


def test_feasibility_merges_by_key_in_fixed_order():
    card = TopicCard(feasibility=[FeasibilityItem(key="data", status="unsure")])
    result = apply_patch(card, CardPatch(feasibility=[
        FeasibilityItem(key="data", status="blocked", note="韓文資料讀不懂"), FeasibilityItem(key="time", status="ok"),
    ]))
    assert [(item.key, item.status) for item in result.feasibility] == [("time", "ok"), ("data", "blocked")]


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


def test_ai_candidates_track_origin_and_follow_the_candidate_list():
    card = apply_patch(TopicCard(), CardPatch(candidates=["AI 題目", "我的題目"], ai_candidates=["AI 題目", "不在清單"]))
    assert card.ai_candidates == ["AI 題目"]
    # The learner rephrases the AI candidate; it drops out of both lists.
    card = apply_patch(card, CardPatch(candidates=["我改寫的題目", "我的題目"]))
    assert card.ai_candidates == []
    assert "AI 題目（AI 提議）" in render_card_prompt(TopicCardState(card=TopicCard(candidates=["AI 題目"], ai_candidates=["AI 題目"])))


def test_feasibility_includes_research_ethics():
    card = apply_patch(TopicCard(), CardPatch(feasibility=[FeasibilityItem(key="ethics", status="unsure", note="要訪談官員")]))
    assert card.feasibility[0].key == "ethics"
    assert "研究倫理→還不確定（要訪談官員）" in render_card_prompt(TopicCardState(stage=5, card=card))
    assert "研究倫理" in topic_card.STAGE_FOCUS[5]


# --- Unit: prompt and stage rules ------------------------------------------------------------


@pytest.mark.parametrize("stage", range(1, COMPLETED_STAGE + 1))
def test_prompt_shows_only_the_current_stage_focus(stage):
    prompt = render_card_prompt(TopicCardState(stage=stage))
    assert topic_card.STAGE_FOCUS[stage] in prompt
    for other, focus in topic_card.STAGE_FOCUS.items():
        if other != stage:
            assert focus not in prompt
    assert "可以跳著走" in prompt and "不能替他切換" in prompt


def test_stage_two_focus_sends_the_learner_outside_and_asks_about_obsolescence():
    focus = topic_card.STAGE_FOCUS[2]
    assert "會不會過幾年就被新技術或局勢自己解決" in focus
    assert "網路搜尋" in focus and "Google Scholar" in focus
    assert "關" not in focus.replace("關鍵字", "")


def test_prompt_lists_feasibility_answers():
    card = TopicCard(feasibility=[FeasibilityItem(key="data", status="blocked", note="韓文")])
    assert "資料與場域→有困難（韓文）" in render_card_prompt(TopicCardState(stage=5, card=card))


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
    assert (loaded.stage, loaded.version, loaded.pending.card.pain_point) == (1, 0, PRIVATE)

    state, adopted = await store.adopt(owner, conversation, expected_version=0)
    assert adopted and (state.stage, state.version, state.card.pain_point) == (1, 1, PRIVATE)
    again, adopted_again = await store.adopt(owner, conversation, expected_version=0)
    assert not adopted_again and (again.stage, again.version) == (1, 1)
    assert (await store.load(owner, conversation)).history[-1].version == 1


@pytest.mark.asyncio
async def test_store_sets_any_stage_and_keeps_suggestions(storage):
    store, owner, _other, conversation = storage
    await store.propose(owner, conversation, CardPatch(keywords=["韓國 避險"], gaps=["缺口？"]))

    assert (await store.set_stage(owner, conversation, 4)).stage == 4
    assert (await store.set_stage(owner, conversation, 2)).stage == 2
    assert await store.set_stage(owner, conversation, 0) is None
    loaded = await store.load(owner, conversation)
    assert (loaded.stage, loaded.version) == (2, 0)
    assert loaded.suggestions.keywords == ["韓國 避險"] and loaded.card == TopicCard()


@pytest.mark.asyncio
async def test_store_isolates_owners_and_rejects_bad_ids(storage):
    store, owner, other, conversation = storage
    await store.propose(owner, conversation, _patch(pain_point=PRIVATE))

    assert await store.load(other, conversation) is None
    assert await store.propose(other, conversation, _patch(pain_point="x")) is None
    assert await store.adopt(other, conversation, 0) is None
    assert await store.set_stage(other, conversation, 3) is None
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
    assert (state.stage, state.version) == (1, 0)
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
async def test_card_prompt_reflects_chosen_stage(storage):
    store, owner, _other, conversation = storage
    await store.set_stage(owner, conversation, 2)

    prompt = await load_card_prompt(owner, conversation, store)
    assert "第 2 階段／共 5 階段" in prompt
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
    assert "選題題目卡" not in chat
    loader.assert_awaited_once_with("u", "c", last_user_msg="hi")
    # The coach block and card come last, after every general style rule, and the
    # per-turn depth overlay that produced report-length answers is not applied.
    assert coach.rstrip().endswith("【選題題目卡（測試）】")
    assert coach.index("Topic Finder／選題（最後且優先的回答規則）") > coach.index("【記憶使用規則】")
    assert "【本回合回答策略】" not in coach and "【本回合回答策略】" in chat


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
async def test_api_reads_and_adopts_with_version_check(api):
    client, _current, owner, _other, conversation, store = api
    await store.propose(owner, conversation, _patch(pain_point=PRIVATE))

    card = (await client.get(f"/api/v1/research-coach/{conversation}/card")).json()
    assert card["pending"]["card"]["pain_point"] == PRIVATE and card["stage"] == 1

    first = await client.post(f"/api/v1/research-coach/{conversation}/confirm", json={"version": 0})
    second = await client.post(f"/api/v1/research-coach/{conversation}/confirm", json={"version": 0})
    assert first.json()["adopted"] is True and first.json()["state"]["stage"] == 1
    assert second.json()["adopted"] is False and second.json()["state"]["version"] == 1


@pytest.mark.asyncio
async def test_api_sets_stage_forward_and_back(api):
    client, _current, _owner, _other, conversation, _store = api
    assert (await client.post(f"/api/v1/research-coach/{conversation}/stage", json={"stage": 5})).json()["stage"] == 5
    assert (await client.post(f"/api/v1/research-coach/{conversation}/stage", json={"stage": 2})).json()["stage"] == 2
    assert (await client.post(f"/api/v1/research-coach/{conversation}/stage", json={"stage": 7})).status_code == 422


@pytest.mark.asyncio
async def test_api_hides_other_users_cards_and_validates_input(api):
    client, current, _owner, other, conversation, _store = api
    current["user"] = other
    assert (await client.get(f"/api/v1/research-coach/{conversation}/card")).status_code == 404
    assert (await client.post(f"/api/v1/research-coach/{conversation}/confirm", json={"version": 0})).status_code == 404
    assert (await client.post(f"/api/v1/research-coach/{conversation}/stage", json={"stage": 2})).status_code == 404
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


# --- Unit: stage-aware field limits (redesign) -------------------------------------------------


@pytest.mark.parametrize(("stage", "opened"), [
    (1, {"keywords"}),
    (2, {"keywords"}),
    (3, {"mother_question"}),
    (4, {"mother_question", "operationalization"}),
    (5, {"mother_question", "operationalization", "feasibility"}),
    (6, {"mother_question", "operationalization", "feasibility"}),
])
def test_fields_open_at_the_stage_that_asks_about_them(stage, opened):
    from services.conversation.topic_card import restrict_patch

    patch_ = CardPatch(pain_point="p", mother_question="m", candidates=["c"],
                       operationalization=[OperationalTerm(term="t", measure="x")],
                       feasibility=[FeasibilityItem(key="time")], keywords=["k"], gaps=["g"], related=["r"],
                       change_note="n")
    result = restrict_patch(patch_, stage)
    assert result.pain_point == "p" and result.candidates == ["c"]
    optional = {"mother_question", "operationalization", "feasibility", "keywords", "gaps", "related"}
    assert {name for name in optional if getattr(result, name) is not None} == opened


@pytest.mark.asyncio
async def test_extraction_drops_fields_from_later_steps_and_sends_allowed_keys():
    client = _client(json.dumps({
        "pain_point": "痛點", "mother_question": "如何運用聯盟理論分析時事",
        "operationalization": [{"term": "聯盟形成動機", "measure": "制衡與扈從"}], "change_note": "整理",
    }))
    patch_ = await extract_card_patch(client, "m", TopicCard(), [{"role": "user", "content": "q"}], "a", stage=1)

    assert patch_.pain_point == "痛點"
    assert patch_.mother_question is None and patch_.operationalization is None
    sent = json.loads(client.chat.completions.create.call_args.kwargs["messages"][1]["content"])
    assert sent["stage"] == 1
    assert "operationalization" not in sent["allowed_keys"] and "mother_question" not in sent["allowed_keys"]
    rules = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "Theories, concepts, or examples the tutor explained are NOT" in rules


def test_notes_do_not_double_punctuation():
    state = with_pending(TopicCardState(), CardPatch(pain_point="a", change_note="確立了研究的核心問題。"))
    state = with_pending(state, CardPatch(candidates=["b"], change_note="擴充影響因素；"))
    assert state.pending.notes == ["確立了研究的核心問題", "擴充影響因素"]
    assert "。；" not in adopt_draft(state).history[-1].note


# --- Reasoning–revision loop: revision review and card-gap focus ---------------------------


def _worked_state(stage=3, **card):
    """A card where stage 2 has an adopted version and stage 4 has measures."""

    base = {"pain_point": "讀論文很慢", "candidates": ["AI 摘要與判斷重點"], "mother_question": "工具代勞會不會削弱篩選能力",
            "operationalization": [OperationalTerm(term="篩選能力", measure="")]}
    return TopicCardState(stage=stage, version=2, card=TopicCard(**{**base, **card}),
                          history=[topic_card.HistoryEntry(version=1, stage=2, note="", confirmed_at=1)])


def test_revision_review_targets_worked_stages_touched_by_the_change():
    before = _worked_state()
    after = before.card.model_copy(update={"mother_question": "人還會發展自己的篩選能力嗎"})

    review = topic_card.revision_review(before, after, 3, now=10.0)

    assert review.changed == ["mother_question"]
    # Stage 3 is where the change happened; stage 5 has no work yet.
    assert review.stages == [2, 4] and review.version == 3 and review.created_at == 10.0


@pytest.mark.parametrize("change", [
    {},  # nothing changed
    {"objections": ["我自己的反問"]},  # objections never trigger a review
])
def test_revision_review_ignores_changes_outside_reviewed_fields(change):
    before = _worked_state()
    assert topic_card.revision_review(before, before.card.model_copy(update=change), 3) is None


def test_revision_review_skips_first_fills_and_unworked_stages():
    # First mother question is a fill, not a revision.
    before = _worked_state(mother_question="")
    assert topic_card.revision_review(before, before.card.model_copy(update={"mother_question": "新"}), 3) is None
    # Early divergence: changing candidates with no later work asks nothing.
    early = TopicCardState(card=TopicCard(candidates=["A"]))
    assert topic_card.revision_review(early, TopicCard(candidates=["A", "B"]), 1) is None


def test_adopt_sets_review_and_keeps_an_unasked_one():
    state = _worked_state()
    state = with_pending(state, _patch(mother_question="改過的母問題"))
    adopted = adopt_draft(state, now=100)
    assert adopted.review.stages == [2, 4] and adopted.review.version == 3

    # A later adopt that needs no review keeps the one not asked yet.
    again = adopt_draft(with_pending(adopted, _patch(objections_add=["反問"])), now=200)
    assert again.review == adopted.review and again.version == 4


@pytest.mark.parametrize(("stage", "card", "kinds"), [
    (1, TopicCard(), ["pain_point", "candidates"]),
    (1, TopicCard(pain_point="p", candidates=["A"], ai_candidates=["A"]), ["own_candidate"]),
    (1, TopicCard(pain_point="p", candidates=["A", "B"], ai_candidates=["A"]), []),
    (2, TopicCard(), ["candidates"]),
    (3, TopicCard(), ["mother_question"]),
    (4, TopicCard(), ["operationalization"]),
    (4, TopicCard(operationalization=[OperationalTerm(term="甲", measure="m"), OperationalTerm(term="乙")]), ["measure"]),
    (5, TopicCard(feasibility=[FeasibilityItem(key=key, status="ok") for key in ("time", "data", "advisor", "prior_work")]
                  + [FeasibilityItem(key="ethics", status="unsure")]), ["feasibility_unsure"]),
    (COMPLETED_STAGE, TopicCard(), []),
])
def test_diagnose_gaps_by_stage(stage, card, kinds):
    assert [gap.kind for gap in topic_card.diagnose_gaps(stage, card)] == kinds


def test_feasibility_gaps_list_missing_items_before_unsure_ones():
    card = TopicCard(feasibility=[FeasibilityItem(key="time", status="unsure")])
    gaps = topic_card.diagnose_gaps(5, card)
    assert [gap.id for gap in gaps] == [
        "feasibility_missing:data", "feasibility_missing:advisor", "feasibility_missing:prior_work",
        "feasibility_missing:ethics", "feasibility_unsure:time"]


def test_focus_ids_never_carry_learner_text():
    card = TopicCard(operationalization=[OperationalTerm(term=PRIVATE)])
    [gap] = topic_card.diagnose_gaps(4, card)
    assert gap.term == PRIVATE and PRIVATE not in gap.id
    assert topic_card.FOCUS_ID_PATTERN.fullmatch(gap.id)
    assert gap.id == topic_card.diagnose_gaps(4, card)[0].id  # stable across calls


def test_current_focus_skips_set_aside_gaps_and_uses_the_draft():
    state = TopicCardState(stage=4, card=TopicCard(operationalization=[OperationalTerm(term="甲"), OperationalTerm(term="乙")]))
    first = topic_card.current_focus(state)
    assert first.term == "甲"

    skipped = topic_card.skip_focus(state, first.id)
    assert topic_card.current_focus(skipped).term == "乙"
    assert topic_card.skip_focus(skipped, first.id) is skipped  # repeat is harmless

    drafted = with_pending(state, _patch(operationalization=[OperationalTerm(term="甲", measure="問卷")]))
    assert topic_card.current_focus(drafted) is None


def test_skipped_focus_list_stays_bounded():
    state = TopicCardState()
    for index in range(topic_card.MAX_SKIPPED_FOCUS + 5):
        state = topic_card.skip_focus(state, f"measure:{index}")
    assert len(state.skipped_focus) == topic_card.MAX_SKIPPED_FOCUS
    assert state.skipped_focus[-1] == f"measure:{topic_card.MAX_SKIPPED_FOCUS + 4}"


def test_prompt_shows_focus_gap_as_one_question():
    state = TopicCardState(stage=4, card=TopicCard(operationalization=[OperationalTerm(term="篩選能力")]))
    prompt = render_card_prompt(state)
    assert "【本輪缺口（給你的內部指示，不要寫進回覆）】" in prompt
    assert "「篩選能力」" in prompt and "只針對這一個缺口問一題" in prompt
    assert "【回頭檢查】" not in prompt


def test_prompt_review_takes_the_turn_before_the_focus_gap():
    state = adopt_draft(with_pending(_worked_state(), _patch(mother_question="改過的母問題")), now=1)
    prompt = render_card_prompt(state)
    assert "【回頭檢查（給你的內部指示，不要寫進回覆）】學習者剛採用題目卡第 3 版，改了母問題" in prompt
    assert "這一輪回覆的第一個問題必須是" in prompt
    assert "第 2、4 階段" in prompt and "【本輪缺口】" not in prompt


def test_prompt_has_no_focus_when_every_gap_is_set_aside():
    state = TopicCardState(stage=3)
    state = topic_card.skip_focus(state, topic_card.current_focus(state).id)
    prompt = render_card_prompt(state)
    assert "【本輪缺口】" not in prompt and topic_card.STAGE_FOCUS[3] in prompt


@pytest.mark.asyncio
async def test_store_persists_review_and_skipped_focus_outside_card_fields(storage):
    store, owner, other, conversation = storage
    await store.set_stage(owner, conversation, 3)
    focus_id = topic_card.current_focus(await store.load(owner, conversation)).id

    assert await store.skip_focus(other, conversation, focus_id) is None
    assert await store.skip_focus(owner, conversation, "bad id!") is None
    state = await store.skip_focus(owner, conversation, focus_id)
    assert state.skipped_focus == [focus_id]

    loaded = await store.load(owner, conversation)
    assert loaded.skipped_focus == [focus_id] and loaded.card == TopicCard()
    assert topic_card.current_focus(loaded) is None


@pytest.mark.asyncio
async def test_store_clears_only_reviews_older_than_the_asking_turn(storage):
    store, owner, _other, conversation = storage
    await store.set_stage(owner, conversation, 4)
    await store.propose(owner, conversation, _patch(mother_question="母問題 A",
                                                    operationalization=[OperationalTerm(term="甲", measure="m")]))
    await store.adopt(owner, conversation, 0)
    await store.set_stage(owner, conversation, 3)
    await store.propose(owner, conversation, _patch(mother_question="母問題 B"))
    state, _ = await store.adopt(owner, conversation, 1)
    assert state.review.stages == [4]
    created = state.review.created_at

    # Adopted while the answer streamed: the turn started earlier, so the review waits.
    assert await store.clear_review(owner, conversation, asked_before=created - 5) is False
    assert (await store.load(owner, conversation)).review is not None
    assert await store.clear_review(owner, conversation, asked_before=created + 5) is True
    assert (await store.load(owner, conversation)).review is None


@pytest.mark.asyncio
async def test_refresh_clears_the_review_its_turn_asked(storage, caplog):
    store, owner, _other, conversation = storage
    await store.set_stage(owner, conversation, 4)
    await store.propose(owner, conversation, _patch(mother_question=PRIVATE,
                                                    operationalization=[OperationalTerm(term="甲", measure="m")]))
    await store.adopt(owner, conversation, 0)
    await store.set_stage(owner, conversation, 3)
    await store.propose(owner, conversation, _patch(mother_question="母問題 B"))
    state, _ = await store.adopt(owner, conversation, 1)
    client = _client(json.dumps({"change_note": ""}))

    await refresh_pending_card(client=client, model="m", user_id=owner, conversation_id=conversation, messages=[],
                               answer="a", turn_started_at=state.review.created_at - 1, store=store)
    assert (await store.load(owner, conversation)).review is not None

    with caplog.at_level(logging.INFO):
        await refresh_pending_card(client=client, model="m", user_id=owner, conversation_id=conversation, messages=[],
                                   answer="a", turn_started_at=state.review.created_at + 1, store=store)
    assert (await store.load(owner, conversation)).review is None
    assert "topic_card.review_asked" in caplog.text and "stages=4" in caplog.text
    assert PRIVATE not in caplog.text


@pytest.mark.asyncio
async def test_card_prompt_logs_steer_without_card_text(storage, caplog):
    store, owner, _other, conversation = storage
    await store.set_stage(owner, conversation, 4)
    await store.propose(owner, conversation, _patch(operationalization=[OperationalTerm(term=PRIVATE)]))

    with caplog.at_level(logging.INFO):
        prompt = await load_card_prompt(owner, conversation, store)
    assert f"「{PRIVATE}」" in prompt
    assert "steer=focus focus_kind=measure" in caplog.text and PRIVATE not in caplog.text


@pytest.mark.asyncio
async def test_completion_passes_turn_start_for_review_clearing():
    import time as time_module

    before = time_module.time()
    scheduled, _events = await _complete(topic_finder=True)
    assert before - 1 <= scheduled.call_args.kwargs["turn_started_at"] <= time_module.time()


@pytest.mark.asyncio
async def test_api_returns_focus_and_the_learner_sets_it_aside_in_chat(api, caplog):
    client, _current, owner, _other, conversation, store = api
    await store.set_stage(owner, conversation, 4)
    await store.propose(owner, conversation, _patch(operationalization=[OperationalTerm(term=PRIVATE),
                                                                         OperationalTerm(term="乙")]))
    focus = (await client.get(f"/api/v1/research-coach/{conversation}/card")).json()["focus"]
    assert focus["kind"] == "measure" and focus["term"] == PRIVATE

    # The learner says "這個先放著"; extraction flags it and the coach moves to the next gap.
    with caplog.at_level(logging.INFO):
        await refresh_pending_card(client=_client(json.dumps({"focus_set_aside": True, "change_note": ""})), model="m",
                                   user_id=owner, conversation_id=conversation,
                                   messages=[{"role": "user", "content": "這個先放著"}], answer="好", store=store)
    card = (await client.get(f"/api/v1/research-coach/{conversation}/card")).json()
    assert card["focus"]["term"] == "乙" and card["skipped_focus"] == [focus["id"]]
    assert "topic_card.focus_set_aside" in caplog.text and "focus_kind=measure" in caplog.text
    assert PRIVATE not in caplog.text
    events = await store.events(owner, conversation)
    assert (events[-1]["event"], events[-1]["source"], events[-1]["focus_kind"]) == ("focus_skipped", "background", "measure")

    # The old skip endpoint is gone; setting aside happens in the conversation.
    assert (await client.post(f"/api/v1/research-coach/{conversation}/focus/skip",
                              json={"gap_id": focus["id"]})).status_code in (404, 405)


@pytest.mark.asyncio
async def test_api_adopt_returns_review_and_logs_stages(api, caplog):
    client, _current, owner, _other, conversation, store = api
    await store.set_stage(owner, conversation, 4)
    await store.propose(owner, conversation, _patch(mother_question=PRIVATE,
                                                    operationalization=[OperationalTerm(term="甲", measure="m")]))
    await client.post(f"/api/v1/research-coach/{conversation}/confirm", json={"version": 0})
    await client.post(f"/api/v1/research-coach/{conversation}/stage", json={"stage": 3})
    await store.propose(owner, conversation, _patch(mother_question="母問題 B"))

    with caplog.at_level(logging.INFO):
        response = await client.post(f"/api/v1/research-coach/{conversation}/confirm", json={"version": 1})
    body = response.json()
    assert body["adopted"] is True and body["state"]["review"]["stages"] == [4]
    assert body["state"]["review"]["changed"] == ["mother_question"]
    assert "review_stages=4" in caplog.text and PRIVATE not in caplog.text


# --- Declining a draft ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_rejects_only_the_draft_the_learner_saw(storage):
    store, owner, other, conversation = storage
    await store.propose(owner, conversation, _patch(pain_point="確認過的痛點"))
    await store.adopt(owner, conversation, 0)
    await store.propose(owner, conversation, _patch(candidates=["AI 提的候選"], ai_candidates=["AI 提的候選"]))

    assert await store.reject(other, conversation, 1) is None
    stale, rejected = await store.reject(owner, conversation, 0)
    assert not rejected and stale.pending is not None

    state, rejected = await store.reject(owner, conversation, 1)
    assert rejected and state.pending is None
    assert (state.version, state.card.pain_point, state.card.candidates) == (1, "確認過的痛點", [])
    again, rejected_again = await store.reject(owner, conversation, 1)
    assert not rejected_again and again.version == 1
    assert (await store.load(owner, conversation)).pending is None


@pytest.mark.asyncio
async def test_api_rejects_draft_without_a_version_and_logs_safely(api, caplog):
    client, current, owner, other, conversation, store = api
    await store.propose(owner, conversation, _patch(pain_point=PRIVATE))

    with caplog.at_level(logging.INFO):
        response = await client.post(f"/api/v1/research-coach/{conversation}/reject", json={"version": 0})
    body = response.json()
    assert body["rejected"] is True and body["state"]["pending"] is None and body["state"]["version"] == 0
    assert "topic_card.draft_rejected" in caplog.text and PRIVATE not in caplog.text

    assert (await client.post(f"/api/v1/research-coach/{conversation}/reject", json={"version": -1})).status_code == 422
    current["user"] = other
    assert (await client.post(f"/api/v1/research-coach/{conversation}/reject", json={"version": 0})).status_code == 404


# --- A: tidier card records ------------------------------------------------------------------


def test_version_note_keeps_the_latest_distinct_short_notes():
    state = TopicCardState(pending=topic_card.PendingDraft(card=TopicCard(pain_point="p"), notes=[
        "確認研究方向為體制轉銜", "確認研究方向為體制轉銜。", "定義關鍵詞測量方式", "加入 BSRS-5"]))
    adopted = adopt_draft(state, now=1)
    assert adopted.history[-1].note == "定義關鍵詞測量方式；加入 BSRS-5"

    long = TopicCardState(pending=topic_card.PendingDraft(card=TopicCard(pain_point="p"), notes=["甲" * 70, "乙" * 70]))
    note = adopt_draft(long, now=1).history[-1].note
    assert len(note) == topic_card.MAX_VERSION_NOTE_CHARS and note.endswith("…")


def test_discarded_topics_are_recorded_once_despite_spacing_or_punctuation():
    card = TopicCard(discarded=[DiscardedTopic(topic="單純做一個 AI 分流 App", filter=2, reason="已有現成解法")])
    patch_ = CardPatch(discarded_add=[
        DiscardedTopic(topic="單純做一個AI分流App。", filter=2, reason="重複"),
        DiscardedTopic(topic="校園轉銜", filter=2, reason="新"),
        DiscardedTopic(topic="校園 轉銜", filter=2, reason="同一批重複"),
    ])
    assert [item.topic for item in apply_patch(card, patch_).discarded] == ["單純做一個 AI 分流 App", "校園轉銜"]


def test_extraction_rules_keep_tutor_material_off_the_card():
    rules = topic_card.EXTRACTION_RULES
    assert "asking a question is not agreement" in rules
    assert 'Feasibility status defaults to "unsure"' in rules
    assert "never add a reworded copy" in rules


@pytest.mark.parametrize(("stage", "phrase"), [
    (3, "學習者寫出的母問題就是之後的基準"),
    (4, "不要替他挑關鍵詞或寫好量測方式"),
    (5, "請他向學校的研究倫理審查單位確認"),
])
def test_stage_focus_keeps_the_learner_in_charge(stage, phrase):
    assert phrase in topic_card.STAGE_FOCUS[stage]


# --- B: card event log ------------------------------------------------------------------------


async def _events(store, owner, conversation):
    return [(item["event"], item["source"], item["stage"], item["version"]) for item in await store.events(owner, conversation)]


@pytest.mark.asyncio
async def test_every_card_write_appends_an_event_with_a_snapshot(storage):
    store, owner, _other, conversation = storage
    await store.set_stage(owner, conversation, 4)
    await store.propose(owner, conversation, _patch(mother_question="母問題 A",
                                                    operationalization=[OperationalTerm(term="甲", measure="m")]))
    await store.adopt(owner, conversation, 0)
    await store.set_stage(owner, conversation, 3, source="chat")
    await store.propose(owner, conversation, _patch(mother_question="母問題 B"))
    await store.adopt(owner, conversation, 1)
    await store.clear_review(owner, conversation, asked_before=time_now() + 5)
    await store.propose(owner, conversation, _patch(candidates=["C"]))
    await store.reject(owner, conversation, 2)
    await store.set_stage(owner, conversation, 4)
    await store.skip_focus(owner, conversation, "measure:abc123")

    events = await _events(store, owner, conversation)
    assert events[:9] == [
        ("stage_set", "api", 4, 0), ("proposed", "background", 4, 0), ("adopted", "api", 4, 1),
        ("stage_set", "chat", 3, 1), ("proposed", "background", 3, 1), ("adopted", "api", 3, 2),
        ("review_set", "api", 3, 2), ("review_cleared", "background", 3, 2), ("proposed", "background", 3, 2),
    ]
    assert events[9:] == [("rejected", "api", 3, 2), ("stage_set", "api", 4, 2), ("focus_skipped", "api", 4, 2)]
    assert (await store.events(owner, conversation))[-1]["focus_kind"] == "measure"
    snapshots = await store.events(owner, conversation)
    assert snapshots[2]["state"]["card"]["mother_question"] == "母問題 A"
    assert snapshots[6]["state"]["card"]["_review"]["stages"] == [4]
    assert snapshots[9]["state"]["pending"] is None


def time_now():
    import time

    return time.time()


@pytest.mark.asyncio
async def test_no_op_writes_log_nothing_and_other_users_see_nothing(storage):
    store, owner, other, conversation = storage
    await store.set_stage(owner, conversation, 1)  # already stage 1
    assert (await store.adopt(owner, conversation, 0))[1] is False
    assert (await store.reject(owner, conversation, 0))[1] is False
    assert await store.events(owner, conversation) == []

    assert await store.set_stage(other, conversation, 3) is None
    assert await store.events(other, conversation) is None
    assert await store.events(owner, conversation) == []


@pytest.mark.asyncio
async def test_event_log_failure_never_breaks_the_card_write(storage, caplog):
    store, owner, _other, conversation = storage
    async with store._engine.begin() as connection:
        await connection.execute(text("DROP TABLE research_topic_card_events"))

    with caplog.at_level(logging.WARNING):
        state = await store.set_stage(owner, conversation, 3)
    assert state.stage == 3 and (await store.load(owner, conversation)).stage == 3
    assert "topic_card.event_log_failed event=stage_set" in caplog.text


@pytest.mark.asyncio
async def test_event_log_keeps_the_newest_events_per_conversation(storage, monkeypatch):
    store, owner, _other, conversation = storage
    monkeypatch.setattr(topic_card, "MAX_EVENTS_PER_CONVERSATION", 3)
    for stage in (2, 3, 4, 5, 2):
        await store.set_stage(owner, conversation, stage)
    assert [item[2] for item in await _events(store, owner, conversation)] == [4, 5, 2]


@pytest.mark.asyncio
async def test_failed_extraction_is_logged_without_card_text(storage, caplog):
    store, owner, _other, conversation = storage
    with caplog.at_level(logging.INFO):
        await refresh_pending_card(client=_client(error=RuntimeError()), model="m", user_id=owner,
                                   conversation_id=conversation, messages=[{"role": "user", "content": PRIVATE}],
                                   answer="a", store=store)
    events = await store.events(owner, conversation)
    assert [(item["event"], item["state"]) for item in events] == [("extraction_failed", None)]
    assert PRIVATE not in caplog.text


@pytest.mark.asyncio
async def test_api_returns_the_owner_event_timeline(api, monkeypatch):
    client, current, owner, other, conversation, store = api
    await store.propose(owner, conversation, _patch(pain_point=PRIVATE))
    await client.post(f"/api/v1/research-coach/{conversation}/confirm", json={"version": 0})

    timeline = (await client.get(f"/api/v1/research-coach/{conversation}/card/log")).json()
    assert [item["event"] for item in timeline] == ["proposed", "adopted"]
    assert timeline[1]["state"]["card"]["pain_point"] == PRIVATE and timeline[1]["version"] == 1
    assert (await client.get(f"/api/v1/research-coach/{conversation}/card/log?limit=0")).status_code == 422

    from config import settings

    monkeypatch.setattr(settings, "enable_topic_card_event_log_api", False)
    assert (await client.get(f"/api/v1/research-coach/{conversation}/card/log")).status_code == 404
    monkeypatch.setattr(settings, "enable_topic_card_event_log_api", True)
    current["user"] = other
    assert (await client.get(f"/api/v1/research-coach/{conversation}/card/log")).status_code == 404


# --- C: stage guidance in the conversation ----------------------------------------------------


@pytest.mark.parametrize(("message", "current", "expected"), [
    ("我們到第五階段好了", 4, 5),
    ("好 目前我們到第階段4了 之後呢 ?", 3, 4),
    ("好，進下一階段", 2, 3),
    ("我想回到第 2 階段看看", 4, 2),
    ("Let's move to stage 3", 2, 3),
    ("好，五個階段都談完了，幫我整理最終題目", 5, 6),
    ("第 4 階段要做什麼？", 3, None),  # asking is not moving
    ("我想先進行第 3 階段的討論", 2, None),  # 進行 is not a move
    ("我們到第 3 階段", 3, None),  # already there
    ("整理最終題目", 2, None),  # only after stage 5
    ("", 1, None),
])
def test_requested_stage_needs_an_explicit_move(message, current, expected):
    assert topic_card.requested_stage(message, current) == expected


@pytest.mark.parametrize(("stage", "card", "history", "expected"), [
    (1, TopicCard(pain_point="p", candidates=["A"], ai_candidates=["A"]), [], None),
    (1, TopicCard(pain_point="p", candidates=["A", "我的題目"], ai_candidates=["A"]), [], 2),
    (2, TopicCard(candidates=["A"]), [], None),
    (2, TopicCard(candidates=["A"]), [topic_card.HistoryEntry(version=1, stage=2, confirmed_at=1)], 3),
    (3, TopicCard(mother_question="m"), [], 4),
    (4, TopicCard(operationalization=[OperationalTerm(term="甲", measure="m"), OperationalTerm(term="乙")]), [], None),
    (4, TopicCard(operationalization=[OperationalTerm(term="甲", measure="m")]), [], 5),
    (5, TopicCard(feasibility=[FeasibilityItem(key=key) for key in topic_card.FEASIBILITY_KEYS]), [], 6),
    (COMPLETED_STAGE, TopicCard(), [], None),
])
def test_ready_for_next_uses_only_adopted_content(stage, card, history, expected):
    assert topic_card.ready_for_next(TopicCardState(stage=stage, card=card, history=history)) == expected


def test_prompt_opens_a_new_stage_with_its_goal_and_where_to_look():
    state = TopicCardState(stage=4, stage_entered=topic_card.StageEntry(stage=4, created_at=1))
    prompt = render_card_prompt(state)
    assert "【進入新階段（給你的內部指示，不要寫進回覆）】" in prompt
    assert "「看得見的證據」那一欄的關鍵詞" in prompt and "然後再問這一階段的第一個問題" in prompt
    # An opening is not also a move-on offer.
    assert "【可以前進" not in prompt


def test_prompt_offers_the_next_stage_once():
    state = TopicCardState(stage=3, card=TopicCard(mother_question="m"))
    assert "【可以前進（給你的內部指示，不要寫進回覆）】" in render_card_prompt(state)
    assert "要不要進到第 4 階段「幫候選題目找看得見的證據」" in render_card_prompt(state)
    assert "【可以前進" not in render_card_prompt(state.model_copy(update={"offered_next": 3}))
    # A pending check-back takes the turn instead.
    reviewed = state.model_copy(update={"review": topic_card.RevisionReview(
        version=2, changed=["mother_question"], stages=[2], created_at=1)})
    assert "【可以前進" not in render_card_prompt(reviewed)


@pytest.mark.asyncio
async def test_finish_turn_clears_the_opening_then_remembers_the_offer(storage):
    store, owner, _other, conversation = storage
    state = await store.set_stage(owner, conversation, 3)
    entered_at = state.stage_entered.created_at

    await store.finish_turn(owner, conversation, asked_before=entered_at - 1)  # set while streaming
    assert (await store.load(owner, conversation)).stage_entered is not None
    await store.finish_turn(owner, conversation, asked_before=entered_at + 1)
    assert (await store.load(owner, conversation)).stage_entered is None

    await store.propose(owner, conversation, _patch(mother_question="母問題"))
    await store.adopt(owner, conversation, 0)
    await store.finish_turn(owner, conversation, asked_before=time_now())
    loaded = await store.load(owner, conversation)
    assert loaded.offered_next == 3 and loaded.card.mother_question == "母問題"


@pytest.mark.asyncio
async def test_chat_request_switches_stage_before_the_answer(storage, caplog):
    store, owner, _other, conversation = storage
    with caplog.at_level(logging.INFO):
        prompt = await load_card_prompt(owner, conversation, store, last_user_msg=f"{PRIVATE}，我們到第五階段好了")

    assert "目前階段：第 5 階段／共 5 階段" in prompt and "【進入新階段" in prompt
    events = await store.events(owner, conversation)
    assert [(item["event"], item["source"], item["stage"]) for item in events] == [("stage_set", "chat", 5)]
    assert "topic_card.stage_requested_in_chat" in caplog.text and PRIVATE not in caplog.text

    # Asking about a stage changes nothing.
    await load_card_prompt(owner, conversation, store, last_user_msg="第 2 階段要做什麼？")
    assert (await store.load(owner, conversation)).stage == 5


@pytest.mark.asyncio
async def test_refresh_finishes_the_turn_after_an_opening(storage):
    store, owner, _other, conversation = storage
    state = await store.set_stage(owner, conversation, 2)
    await refresh_pending_card(client=_client(json.dumps({"change_note": ""})), model="m", user_id=owner,
                               conversation_id=conversation, messages=[], answer="a",
                               turn_started_at=state.stage_entered.created_at + 1, store=store)
    assert (await store.load(owner, conversation)).stage_entered is None


@pytest.mark.asyncio
async def test_api_card_reports_the_next_stage_when_ready(api):
    client, _current, owner, _other, conversation, store = api
    await store.set_stage(owner, conversation, 3)
    assert (await client.get(f"/api/v1/research-coach/{conversation}/card")).json()["next_stage"] is None
    await store.propose(owner, conversation, _patch(mother_question="母問題"))
    await store.adopt(owner, conversation, 0)
    assert (await client.get(f"/api/v1/research-coach/{conversation}/card")).json()["next_stage"] == 4
