from app.core.logging import MASK, mask


def test_mask_hides_sensitive_keys_recursively() -> None:
    data = {
        "password": "p",
        "username": "ali",
        "nested": {"new_password": "n", "session_token": "t", "ok": 1},
        "items": [{"totp_secret": "s"}, {"inn": "305"}],
        "status_code": 200,
        "code": "123456",
    }
    assert mask(data) == {
        "password": MASK,
        "username": "ali",
        "nested": {"new_password": MASK, "session_token": MASK, "ok": 1},
        "items": [{"totp_secret": MASK}, {"inn": MASK}],
        "status_code": 200,
        "code": MASK,
    }


def test_mask_leaves_scalars() -> None:
    assert mask("plain") == "plain"
    assert mask(5, "user_id") == 5
