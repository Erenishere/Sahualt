from dataclasses import replace
from uuid import UUID

import pytest

from sahulat_api.identity import ExternalImageReference, resolve_canonical_matches
from sahulat_visual.domain import ProductMatch

pytestmark = pytest.mark.unit


def references():
    return [
        ExternalImageReference("synthetic-v1", "A", "a1", UUID(int=200), UUID(int=1)),
        ExternalImageReference("synthetic-v1", "B", "b1", UUID(int=100), UUID(int=2)),
    ]


def matches():
    return [
        ProductMatch("A", 0.9, "a1", "private/a1.png"),
        ProductMatch("B", 0.9, "b1", "private/b1.png"),
    ]


def test_resolution_preserves_ranking_not_uuid_order():
    resolved = resolve_canonical_matches("synthetic-v1", matches(), reversed(references()))
    assert [r.product_id for r in resolved] == [UUID(int=200), UUID(int=100)]
    assert [r.score for r in resolved] == [0.9, 0.9]
    assert resolved[0].external_product_id == "A" and resolved[0].external_image_id == "a1"
    assert resolved[0].matched_image_id == UUID(int=1)
    assert "private" not in repr(resolved)


@pytest.mark.parametrize(
    "fault",
    [
        "namespace",
        "missing",
        "cross_product",
        "duplicate_image",
        "conflicting_product",
        "non_uuid",
        "empty_id",
        "canonical_collision",
    ],
)
def test_resolution_fails_closed(fault):
    refs = references()
    if fault == "namespace":
        refs[0] = replace(refs[0], source_system="wrong-v1")
    elif fault == "missing":
        refs.pop()
    elif fault == "cross_product":
        refs[0] = replace(refs[0], external_product_id="B")
    elif fault == "duplicate_image":
        refs.append(refs[0])
    elif fault == "conflicting_product":
        refs.append(replace(refs[0], external_image_id="a2", product_id=UUID(int=201)))
    elif fault == "non_uuid":
        refs[0] = replace(refs[0], product_id="A")
    elif fault == "empty_id":
        refs[0] = replace(refs[0], external_product_id=" ")
    else:
        refs[1] = replace(refs[1], product_id=refs[0].product_id)
    with pytest.raises(ValueError):
        resolve_canonical_matches("synthetic-v1", matches(), refs)
