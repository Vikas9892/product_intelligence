"""Unit tests for the API-key crypto helpers."""

from app.services.enterprise import api_keys


class TestApiKeys:
    def test_generated_keys_are_prefixed_and_unique(self) -> None:
        a = api_keys.generate_raw_key()
        b = api_keys.generate_raw_key()

        assert a.startswith("pik_")
        assert a != b

    def test_prefix_is_the_leading_segment(self) -> None:
        raw = api_keys.generate_raw_key()

        assert api_keys.key_prefix(raw) == raw[:12]

    def test_verify_accepts_the_matching_key(self) -> None:
        raw = api_keys.generate_raw_key()
        hashed = api_keys.hash_key(raw)

        assert api_keys.verify_key(raw, hashed) is True

    def test_verify_rejects_a_different_key(self) -> None:
        hashed = api_keys.hash_key(api_keys.generate_raw_key())

        assert api_keys.verify_key(api_keys.generate_raw_key(), hashed) is False

    def test_hash_is_deterministic(self) -> None:
        raw = api_keys.generate_raw_key()

        assert api_keys.hash_key(raw) == api_keys.hash_key(raw)
