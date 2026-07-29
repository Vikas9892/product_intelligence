"""Unit tests for `ModelVersion`."""

import pytest
from pydantic import BaseModel, ValidationError

from app.models.model_version import ModelVersion


class _Holder(BaseModel):
    version: ModelVersion


class TestModelVersion:
    def test_accepts_a_well_formed_semantic_version(self) -> None:
        holder = _Holder(version="1.0.0")

        assert holder.version == "1.0.0"

    def test_accepts_multi_digit_components(self) -> None:
        holder = _Holder(version="12.34.56")

        assert holder.version == "12.34.56"

    def test_rejects_a_two_part_version(self) -> None:
        with pytest.raises(ValidationError):
            _Holder(version="1.0")

    def test_rejects_a_non_numeric_component(self) -> None:
        with pytest.raises(ValidationError):
            _Holder(version="1.0.beta")

    def test_rejects_a_leading_v_prefix(self) -> None:
        with pytest.raises(ValidationError):
            _Holder(version="v1.0.0")
