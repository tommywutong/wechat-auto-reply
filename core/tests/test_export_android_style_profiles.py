from scripts.export_android_style_profiles import build_export


def test_export_keeps_only_display_names_and_minimal_profile_fields() -> None:
    payload = build_export(
        {
            "wxid-private": {
                "summary": "短句",
                "sample_count": 3,
                "updated_at": 1234567890,
                "examples": [
                    {"incoming": "在吗", "reply": "在"},
                    {"reply": "没有 incoming 时也不会进来"},
                ],
            }
        },
        [{"talker": "wxid-private", "name": "小王"}],
    )

    assert payload == {
        "version": 1,
        "profiles": [
            {
                "displayName": "小王",
                "summary": "短句",
                "sampleCount": 3,
                "examples": [{"them": "在吗", "me": "在"}],
            }
        ],
    }
    assert "wxid-private" not in str(payload)
    assert "updated_at" not in str(payload)


def test_export_skips_profiles_without_current_contact_mapping() -> None:
    payload = build_export(
        {"wxid-old": {"summary": "短句", "sample_count": 1, "examples": []}},
        [{"talker": "wxid-current", "name": "小王"}],
    )
    assert payload == {"version": 1, "profiles": []}
