from scripts.tracememo_contacts import parse_contacts, fetch_recent_contacts


def test_parse_contacts_prefers_remark_and_detects_groups() -> None:
    payload = {
        "count": 2,
        "contacts": [
            {
                "m_nsUsrName": "wxid-a",
                "m_nsNickName": "昵称 A",
                "remark": "备注 A",
                "type": "user",
            },
            {
                "m_nsUsrName": "room@chatroom",
                "m_nsNickName": "项目组",
                "type": "group",
                "isMuted": 1,
            },
        ],
    }

    result = parse_contacts(payload)

    assert result[0]["talker"] == "wxid-a"
    assert result[0]["name"] == "备注 A"
    assert result[0]["aliases"] == ["备注 A", "昵称 A"]
    assert result[0]["isGroup"] is False
    assert result[1]["talker"] == "room@chatroom"
    assert result[1]["isGroup"] is True
    assert result[1]["isMuted"] is True


def test_parse_contacts_deduplicates_talker_and_falls_back_to_id() -> None:
    payload = {
        "data": [
            {"m_nsUsrName": "wxid-a", "m_nsNickName": "A"},
            {"m_nsUsrName": "wxid-a", "m_nsNickName": "A (旧)"},
            {"m_nsUsrName": "wxid-empty"},
        ]
    }

    result = parse_contacts(payload)

    assert [item["talker"] for item in result] == ["wxid-a", "wxid-empty"]
    assert result[1]["name"] == "wxid-empty"


def test_parse_contacts_can_preserve_recent_chat_order() -> None:
    payload = {
        "items": [
            {"m_nsUsrName": "wxid-recent", "m_nsNickName": "最近联系人"},
            {"m_nsUsrName": "room@chatroom", "m_nsNickName": "最近群", "type": "group"},
        ]
    }

    result = parse_contacts(payload, preserve_order=True)

    assert [item["talker"] for item in result] == ["wxid-recent", "room@chatroom"]
