from app.auth import passwords
from app.auth.passwords import (
    STANDARD_PARAMS,
    generate_temporary_password,
    hash_password,
    needs_rehash,
    policy_problems,
    verify_password,
)

GOOD = "Kuchli-Maxfiy-2026!"


def test_standard_params_match_spec() -> None:
    assert STANDARD_PARAMS == (3, 65536, 4)


def test_hash_and_verify() -> None:
    h = hash_password(GOOD)
    assert h.startswith("$argon2id$")
    assert verify_password(GOOD, h)
    assert not verify_password("boshqa", h)
    assert not verify_password(GOOD, "not-a-hash")
    assert not needs_rehash(h)


def test_dummy_verify_does_not_raise() -> None:
    passwords.dummy_verify("anything")


def test_good_password_passes() -> None:
    assert policy_problems(GOOD, username="ali.valiyev") == []


def test_short_and_simple() -> None:
    assert "password_too_short" in policy_problems("Ab1!", username="u")
    assert "password_too_simple" in policy_problems("abcdefghijklmn", username="u")


def test_contains_username_case_insensitive() -> None:
    problems = policy_problems("XX-ALI.VALIYEV-2026", username="ali.valiyev")
    assert "password_contains_username" in problems


def test_common_and_context_words() -> None:
    assert "password_common" in policy_problems("Ugekazna-2026!", username="u")
    assert "password_common" in policy_problems("Qwerty-12345!", username="u")


def test_context_words_parol_variants() -> None:
    assert "password_common" in policy_problems("Mening-Parolim-2026!", username="u")
    assert "password_common" in policy_problems("Мой-Пароль-2026!x", username="u")


def test_reused_password() -> None:
    old = hash_password(GOOD)
    assert policy_problems(GOOD, username="u", previous_hashes=[old]) == ["password_reused"]


def test_temporary_passwords_satisfy_policy() -> None:
    samples = {generate_temporary_password() for _ in range(50)}
    assert len(samples) == 50
    assert all(len(p) == 16 and policy_problems(p, username="user") == [] for p in samples)
