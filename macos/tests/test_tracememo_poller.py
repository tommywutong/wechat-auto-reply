from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
import threading


MODULE_PATH = Path(__file__).parents[1] / "tracememo_poller.py"
SPEC = importlib.util.spec_from_file_location("tracememo_poller", MODULE_PATH)
assert SPEC and SPEC.loader
poller = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = poller
SPEC.loader.exec_module(poller)


def test_parse_conversations_uses_stable_talker_and_display_name() -> None:
    payload = {
        "data": {
            "items": [
                {
                    "m_nsUsrName": "room@chatroom",
                    "m_nsNickName": "iOS群",
                    "remark": "",
                    "wechatNickname": "备用群名",
                }
            ]
        }
    }

    assert poller.parse_conversations(payload) == [
        poller.Conversation(talker="room@chatroom", name="iOS群", is_group=True)
    ]


def test_parse_messages_skips_messages_with_unknown_direction() -> None:
    conversation = poller.Conversation(talker="wxid-a", name="Loky", is_group=False)
    payload = {
        "data": [
            {
                "serverId": "incoming",
                "content": "你好",
                "isSender": 0,
                "type": 1,
                "createTime": 1_700_000_000,
            },
            {
                "serverId": "outgoing",
                "content": "收到",
                "isSender": 1,
                "type": 1,
                "createTime": 1_700_000_001,
            },
            {
                "serverId": "image",
                "content": "图片说明也不应回复",
                "isSender": 0,
                "type": 3,
                "createTime": 1_700_000_002,
            },
            {"serverId": "unknown", "content": "不要猜方向", "type": 1, "createTime": 1_700_000_003},
        ]
    }

    messages = poller.parse_messages(payload, conversation)

    assert [message.message_id for message in messages] == ["incoming", "outgoing"]
    assert messages[0].outgoing is False
    assert messages[1].outgoing is True


def test_poll_state_keeps_only_recent_message_ids(tmp_path: Path) -> None:
    state = poller.PollState(tmp_path / "state.json")
    for index in range(205):
        state.mark_seen("wxid-a", str(index))

    assert state.seen_ids["wxid-a"] == [str(index) for index in range(5, 205)]


def test_text_type_filter_rejects_non_text_messages() -> None:
    assert poller._is_text_message({"type": 1}) is True
    assert poller._is_text_message({"type": "text"}) is True
    assert poller._is_text_message({"type": "普通文本"}) is True
    assert poller._is_text_message({"type": 3}) is False


def test_parse_messages_detects_configured_group_mention() -> None:
    conversation = poller.Conversation(
        talker="room@chatroom",
        name="测试群",
        is_group=True,
    )
    payload = {
        "data": [
            {
                "serverId": "mention",
                "content": "@Northern Lights 你看看这个",
                "isSender": 0,
                "type": "普通文本",
                "createTime": 1_700_000_000,
            },
            {
                "serverId": "lookalike",
                "content": "@Northern Lights2 不是我",
                "isSender": 0,
                "type": "普通文本",
                "createTime": 1_700_000_001,
            },
        ]
    }

    messages = poller.parse_messages(payload, conversation, ["Northern Lights"])

    assert messages[0].mentioned_me is True
    assert messages[1].mentioned_me is False


def test_timestamp_accepts_tracememo_datetime_field() -> None:
    parsed = poller._timestamp({"datetime": "2026-08-24 20:14:30"})
    assert parsed > 1_700_000_000


def test_parse_messages_keeps_image_and_sticker_metadata() -> None:
    conversation = poller.Conversation("wxid-a", "Loky", False)
    payload = {
        "data": [
            {
                "serverId": "image-1",
                "content": "",
                "isSender": 0,
                "type": "图片",
                "contentData": {
                    "url": "https://example.test/image.jpg",
                    "md5": "a" * 32,
                },
                "createTime": 1_700_000_000,
            },
            {
                "serverId": "sticker-1",
                "content": "",
                "isSender": 0,
                "type": "表情包",
                "contentData": {"encryptUrl": "https://example.test/sticker.gif"},
                "createTime": 1_700_000_001,
            },
        ]
    }

    messages = poller.parse_messages(payload, conversation)

    assert [message.message_type for message in messages] == ["image", "sticker"]
    assert messages[0].media_url.endswith("image.jpg")
    assert messages[1].text == "【表情包】"


def test_media_recognizer_adds_ocr_text(monkeypatch, tmp_path: Path) -> None:
    recognizer = poller.MediaRecognizer(repo_dir=tmp_path)
    monkeypatch.setattr(recognizer, "_download", lambda url, path: True)
    monkeypatch.setattr(recognizer, "_ocr", lambda path: "会议改到三点")
    message = poller.ChatMessage(
        "image-1",
        "wxid-a",
        "Loky",
        "【图片】",
        1_700_000_000,
        "Loky",
        False,
        False,
        message_type="image",
        media_url="https://example.test/image.jpg",
    )

    enriched = recognizer.enrich(message)

    assert enriched.ocr_text == "会议改到三点"
    assert enriched.text == "【图片】图片文字：会议改到三点"


def test_media_recognizer_keeps_image_as_base64_for_vision(monkeypatch, tmp_path: Path) -> None:
    recognizer = poller.MediaRecognizer(repo_dir=tmp_path)

    def download(_url, path):
        path.write_bytes(b"\x89PNG\r\n\x1a\nimage")
        return True

    monkeypatch.setattr(recognizer, "_download", download)
    monkeypatch.setattr(recognizer, "_ocr", lambda path: "图片文字")
    message = poller.ChatMessage(
        "image-1", "wxid-a", "Loky", "【图片】", 1_700_000_000, "Loky", False, False,
        message_type="image", media_url="https://example.test/image.png",
    )

    enriched = recognizer.enrich(message)

    assert enriched.media_mime_type == "image/png"
    assert enriched.media_data == "iVBORw0KGgppbWFnZQ=="


def test_engine_client_sends_media_fields(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"should_reply": False, "reason": "test"}

    captured = {}

    class Session:
        def post(self, url, **kwargs):
            captured.update(kwargs)
            return Response()

    client = poller.EngineClient("http://127.0.0.1:8848", "token")
    client._session = Session()
    client.draft(
        poller.ChatMessage(
            "m", "wxid-a", "Loky", "【图片】", 1_700_000_000, "Loky", False, False,
            message_type="image", media_data="abc", media_mime_type="image/png",
        )
    )

    assert captured["json"]["media_data"] == "abc"
    assert captured["json"]["media_mime_type"] == "image/png"


class _CapturingEngine:
    def __init__(self) -> None:
        self.messages: list[poller.ChatMessage] = []

    def draft(self, message, style_context=""):
        self.messages.append(message)
        return {"should_reply": False, "reason": "test"}


def test_poller_batches_continuous_messages_for_one_engine_decision(tmp_path: Path) -> None:
    now = 1_800_000_000
    messages = [
        poller.ChatMessage("m1", "biscoffee-id", "Biscoffee", "你在吗", now, "Biscoffee", False, False),
        poller.ChatMessage("m2", "biscoffee-id", "Biscoffee", "有个问题想问", now + 2, "Biscoffee", False, False),
    ]
    engine = _CapturingEngine()
    state = poller.PollState(tmp_path / "state.json")
    state.ready_talkers.add("biscoffee-id")
    state.last_polled_at = now - 10
    instance = poller.Poller(
        _FakeTraceMemo(messages),
        engine,
        {"biscoffee"},
        state,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
        replay_offline=True,
    )
    original_time = poller.time.time
    poller.time.time = lambda: now
    try:
        stats = instance.tick()
    finally:
        poller.time.time = original_time

    assert stats.new_messages == 2
    assert len(engine.messages) == 1
    assert engine.messages[0].batch_size == 2
    assert "你在吗" in engine.messages[0].text and "有个问题想问" in engine.messages[0].text


def test_poller_fetches_conversations_in_parallel_but_keeps_order(tmp_path: Path) -> None:
    now = 1_800_000_000
    conversations = [
        poller.Conversation("slow", "Slow", False),
        poller.Conversation("fast", "Fast", False),
    ]
    state = poller.PollState(tmp_path / "state.json")
    engine = _CapturingEngine()
    instance = poller.Poller(
        _FakeTraceMemo([]),
        engine,
        {"slow", "fast"},
        state,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
        fetch_workers=2,
    )
    started: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def fetch(item):
        conversation, _start, _end = item
        with lock:
            started.append(conversation.talker)
        barrier.wait(timeout=1)
        return conversation, [], None

    instance._fetch_conversation = fetch
    result = instance._fetch_conversations(conversations, 0, now)

    assert set(started) == {"slow", "fast"}
    assert [item[0].talker for item in result] == ["slow", "fast"]


def test_poller_fetch_failure_isolated_from_other_conversations(tmp_path: Path) -> None:
    state = poller.PollState(tmp_path / "state.json")
    instance = poller.Poller(
        _FakeTraceMemo([]),
        _CapturingEngine(),
        {"slow", "fast"},
        state,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
        fetch_workers=2,
    )
    conversations = [
        poller.Conversation("slow", "Slow", False),
        poller.Conversation("fast", "Fast", False),
    ]

    def fetch(item):
        conversation, _start, _end = item
        if conversation.talker == "slow":
            return conversation, None, poller.TraceMemoError("暂时不可用")
        return conversation, [], None

    instance._fetch_conversation = fetch
    result = instance._fetch_conversations(conversations, 0, 1)

    assert result[0][2] is not None
    assert result[1][1] == []


def test_poller_splits_messages_outside_merge_window(tmp_path: Path) -> None:
    now = 1_800_000_000
    messages = [
        poller.ChatMessage("m1", "biscoffee-id", "Biscoffee", "第一条", now, "Biscoffee", False, False),
        poller.ChatMessage("m2", "biscoffee-id", "Biscoffee", "第二条", now + 20, "Biscoffee", False, False),
    ]
    engine = _CapturingEngine()
    state = poller.PollState(tmp_path / "state.json")
    state.ready_talkers.add("biscoffee-id")
    state.last_polled_at = now - 10
    instance = poller.Poller(
        _FakeTraceMemo(messages),
        engine,
        {"biscoffee"},
        state,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
        replay_offline=True,
    )
    original_time = poller.time.time
    poller.time.time = lambda: now + 20
    try:
        instance.tick()
    finally:
        poller.time.time = original_time

    assert len(engine.messages) == 2


def test_poller_skips_history_on_start_by_default(tmp_path: Path) -> None:
    now = 1_800_000_000
    messages = [
        poller.ChatMessage("old", "biscoffee-id", "Biscoffee", "停机期间的消息", now - 30, "Biscoffee", False, False),
    ]
    engine = _CapturingEngine()
    state = poller.PollState(tmp_path / "state.json")
    state.ready_talkers.add("biscoffee-id")
    state.last_polled_at = now - 120
    instance = poller.Poller(
        _FakeTraceMemo(messages),
        engine,
        {"biscoffee"},
        state,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
    )
    original_time = poller.time.time
    poller.time.time = lambda: now
    try:
        stats = instance.tick()
    finally:
        poller.time.time = original_time

    assert stats.new_messages == 0
    assert engine.messages == []
    assert state.last_polled_at == now


def test_poller_replays_history_only_when_enabled(tmp_path: Path) -> None:
    now = 1_800_000_000
    messages = [
        poller.ChatMessage("old", "biscoffee-id", "Biscoffee", "停机期间的消息", now - 30, "Biscoffee", False, False),
    ]
    engine = _CapturingEngine()
    state = poller.PollState(tmp_path / "state.json")
    state.ready_talkers.add("biscoffee-id")
    state.last_polled_at = now - 120
    instance = poller.Poller(
        _FakeTraceMemo(messages),
        engine,
        {"biscoffee"},
        state,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
        replay_offline=True,
    )
    original_time = poller.time.time
    poller.time.time = lambda: now
    try:
        stats = instance.tick()
    finally:
        poller.time.time = original_time

    assert stats.new_messages == 1
    assert len(engine.messages) == 1


def test_poller_replay_mode_handles_first_seen_conversation(tmp_path: Path) -> None:
    now = 1_800_000_000
    messages = [
        poller.ChatMessage("old", "new-id", "新会话", "停机期间的消息", now - 30, "新会话", False, False),
    ]
    engine = _CapturingEngine()
    state = poller.PollState(tmp_path / "state.json")
    state.last_polled_at = now - 120
    instance = poller.Poller(
        _FakeTraceMemo(messages, conversations=[poller.Conversation("new-id", "新会话", False)]),
        engine,
        {"新会话"},
        state,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
        replay_offline=True,
    )
    original_time = poller.time.time
    poller.time.time = lambda: now
    try:
        stats = instance.tick()
    finally:
        poller.time.time = original_time

    assert stats.new_messages == 1
    assert len(engine.messages) == 1


def test_poll_state_save_without_cursor_advance_persists_claim(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = poller.PollState(path)
    state.last_polled_at = 123.0
    state.mark_seen("wxid-a", "message-1")
    state.save()

    loaded = poller.PollState(path)

    assert loaded.last_polled_at == 123.0
    assert loaded.has_seen("wxid-a", "message-1")


class _FakeTraceMemo:
    def __init__(self, messages: list[poller.ChatMessage], conversations=None) -> None:
        self.messages = messages
        self.conversations = conversations

    def recent_conversations(self) -> list[poller.Conversation]:
        if self.conversations is not None:
            return self.conversations
        return [
            poller.Conversation("biscoffee-id", "Biscoffee", False),
            poller.Conversation("loky-id", "Loky", False),
        ]

    def chatlog(self, conversation, start_time, end_time):
        return [message for message in self.messages if message.talker == conversation.talker]


class _FakeEngine:
    def draft(self, message):
        return {"should_reply": True, "text": "收到", "reason": "test", "delay_seconds": 0}


class _FakeSender:
    def __init__(self) -> None:
        self.calls = []
        self.group_flags = []

    def send(self, target_name, text, *, is_group=False):
        self.calls.append((target_name, text))
        self.group_flags.append(is_group)


class _RetryingSender:
    def __init__(self) -> None:
        self.calls = []

    def send(self, target_name, text, *, is_group=False):
        self.calls.append((target_name, text))
        if len(self.calls) == 1:
            raise RuntimeError("输入区未确认")


class _DeferredSender:
    def __init__(self) -> None:
        self.calls = []
        self.busy = True

    def send(self, target_name, text, *, is_group=False):
        self.calls.append((target_name, text))
        if self.busy:
            error = RuntimeError("用户正在操作电脑")
            error.defer_retry = True
            error.retry_after = 15.0
            error.send_attempted = False
            raise error


def test_poller_send_mode_can_be_limited_to_biscoffee(tmp_path: Path) -> None:
    now = 1_800_000_000
    messages = [
        poller.ChatMessage("m1", "biscoffee-id", "Biscoffee", "你好", now, "Biscoffee", False, False),
        poller.ChatMessage("m2", "loky-id", "Loky", "你好", now, "Loky", False, False),
    ]
    sender = _FakeSender()
    state = poller.PollState(tmp_path / "state.json")
    state.ready_talkers.update({"biscoffee-id", "loky-id"})
    state.last_polled_at = now - 10
    poller_instance = poller.Poller(
        _FakeTraceMemo(messages),
        _FakeEngine(),
        {"biscoffee", "loky"},
        state,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
        sender=sender,
        send_name="Biscoffee",
        replay_offline=True,
    )
    original_time = poller.time.time
    poller.time.time = lambda: now
    try:
        poller_instance.tick()
    finally:
        poller.time.time = original_time

    assert sender.calls == [("Biscoffee", "收到")]


def test_poller_allows_stable_talker_id_when_display_name_changes(tmp_path: Path) -> None:
    now = 1_800_000_000
    conversation = poller.Conversation("wxid-stable", "新备注", False, ("旧昵称",))
    messages = [
        poller.ChatMessage("m1", "wxid-stable", "新备注", "你好", now, "新备注", False, False),
    ]
    sender = _FakeSender()
    state = poller.PollState(tmp_path / "state.json")
    state.ready_talkers.add("wxid-stable")
    state.last_polled_at = now - 10
    poller_instance = poller.Poller(
        _FakeTraceMemo(messages, conversations=[conversation]),
        _FakeEngine(),
        set(),
        state,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
        allowed_talkers={"wxid-stable"},
        sender=sender,
        send_name="新备注",
        replay_offline=True,
    )
    original_time = poller.time.time
    poller.time.time = lambda: now
    try:
        poller_instance.tick()
    finally:
        poller.time.time = original_time

    assert sender.calls == [("新备注", "收到")]


def test_poller_send_all_sends_only_allowed_private_messages(tmp_path: Path) -> None:
    now = 1_800_000_000
    messages = [
        poller.ChatMessage("m1", "biscoffee-id", "Biscoffee", "你好", now, "Biscoffee", False, False),
        poller.ChatMessage("m2", "loky-id", "Loky", "你好", now, "Loky", False, False),
    ]
    sender = _FakeSender()
    state = poller.PollState(tmp_path / "state.json")
    state.ready_talkers.update({"biscoffee-id", "loky-id"})
    state.last_polled_at = now - 10
    poller_instance = poller.Poller(
        _FakeTraceMemo(messages),
        _FakeEngine(),
        {"biscoffee", "loky"},
        state,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
        sender=sender,
        send_name="Biscoffee",
        send_all=True,
        replay_offline=True,
    )
    original_time = poller.time.time
    poller.time.time = lambda: now
    try:
        poller_instance.tick()
    finally:
        poller.time.time = original_time

    assert sender.calls == [("Biscoffee", "收到"), ("Loky", "收到")]
    assert sender.group_flags == [False, False]


def test_poller_passes_group_flag_to_sender(tmp_path: Path) -> None:
    now = 1_800_000_000
    messages = [
        poller.ChatMessage("m1", "room-id", "测试群", "你好", now, "群友", True, False, True),
    ]
    sender = _FakeSender()
    state = poller.PollState(tmp_path / "state.json")
    state.ready_talkers.add("room-id")
    state.last_polled_at = now - 10
    poller_instance = poller.Poller(
        _FakeTraceMemo(messages, [poller.Conversation("room-id", "测试群", True)]),
        _FakeEngine(),
        {"测试群"},
        state,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
        sender=sender,
        send_name="测试群",
        replay_offline=True,
    )
    original_time = poller.time.time
    poller.time.time = lambda: now
    try:
        poller_instance.tick()
    finally:
        poller.time.time = original_time

    assert sender.calls == [("测试群", "收到")]
    assert sender.group_flags == [True]


def test_poller_retries_only_unattempted_send_failure(tmp_path: Path) -> None:
    now = 1_800_000_000
    messages = [
        poller.ChatMessage("m1", "biscoffee-id", "Biscoffee", "你好", now, "Biscoffee", False, False),
    ]
    sender = _RetryingSender()
    state = poller.PollState(tmp_path / "state.json")
    state.ready_talkers.add("biscoffee-id")
    state.last_polled_at = now - 10
    poller_instance = poller.Poller(
        _FakeTraceMemo(messages),
        _FakeEngine(),
        {"biscoffee"},
        state,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
        sender=sender,
        send_name="Biscoffee",
        replay_offline=True,
    )
    original_time = poller.time.time
    poller.time.time = lambda: now
    try:
        poller_instance.tick()
        assert state.retry_attempts("biscoffee-id", "m1") == 1
        state.retry_state["biscoffee-id"]["m1"]["next_at"] = now - 1
        poller_instance.tick()
    finally:
        poller.time.time = original_time

    assert sender.calls == [("Biscoffee", "收到"), ("Biscoffee", "收到")]
    assert state.retry_attempts("biscoffee-id", "m1") == 0


def test_user_activity_keeps_persistent_queue_without_consuming_retries(tmp_path: Path) -> None:
    now = 1_800_000_000
    message = poller.ChatMessage(
        "m1", "biscoffee-id", "Biscoffee", "你好", now, "Biscoffee", False, False
    )
    sender = _DeferredSender()
    state_path = tmp_path / "state.json"
    state = poller.PollState(state_path)
    state.ready_talkers.add("biscoffee-id")
    state.last_polled_at = now - 10
    instance = poller.Poller(
        _FakeTraceMemo([message]),
        _FakeEngine(),
        {"biscoffee"},
        state,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
        sender=sender,
        send_name="Biscoffee",
        replay_offline=True,
    )
    original_time = poller.time.time
    poller.time.time = lambda: now
    try:
        stats = instance.tick()
    finally:
        poller.time.time = original_time

    assert stats.deferred == 1
    assert stats.send_failures == 0
    assert state.has_retry("biscoffee-id", "m1")
    assert state.retry_attempts("biscoffee-id", "m1") == 0

    reloaded = poller.PollState(state_path)
    reloaded.retry_state["biscoffee-id"]["m1"]["next_at"] = now - 1
    reloaded.save()
    sender.busy = False
    resumed = poller.Poller(
        _FakeTraceMemo([message]),
        _FakeEngine(),
        {"biscoffee"},
        reloaded,
        poller.DraftWriter(tmp_path / "drafts.jsonl"),
        sender=sender,
        send_name="Biscoffee",
        replay_offline=True,
    )
    poller.time.time = lambda: now
    try:
        resumed.tick()
    finally:
        poller.time.time = original_time

    assert sender.calls == [("Biscoffee", "收到"), ("Biscoffee", "收到")]
    assert not reloaded.has_retry("biscoffee-id", "m1")
