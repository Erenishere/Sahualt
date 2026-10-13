import pytest

from sahulat_voice.benchmark.dataset import _metadata_selection
from sahulat_voice.benchmark.metadata import FleursRow, read_metadata, select_rows
from sahulat_voice.benchmark.protocol import scoring_text
from sahulat_voice.errors import VoiceError


def row(identifier=1, filename="100.wav", raw="Human published script.", frames=1600):
    return f"{identifier}\t{filename}\t{raw}\t{raw}\tunused\t{frames}\tother\n".encode()


def test_source_text_preserved_exactly():
    raw = '  Café, "Original" متن!  '
    rows, excluded = read_metadata(row(raw=raw))
    assert rows[0].raw_transcription == raw
    assert excluded == []


@pytest.mark.parametrize("raw", ["", "  ", "\x00", "!" * 2049])
def test_unusable_reference_exclusion(raw):
    rows, excluded = read_metadata(row(raw=raw))
    assert rows == []
    assert len(excluded) == 1


@pytest.mark.parametrize("frames", [0, 1599, 480001])
def test_duration_exclusion(frames):
    rows, excluded = read_metadata(row(frames=frames))
    assert not rows
    assert excluded[0]["reason"] == "outside-runtime-duration"


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff",
        b"one\ttwo\n",
        row(filename="../1.wav"),
        row(identifier="x"),
        row(frames="0" * 100),
        row() + row(),
    ],
)
def test_corrupt_tsv_fails_closed(payload):
    with pytest.raises(VoiceError):
        read_metadata(payload)


def test_selection_order_independent_and_unique_sentence_ids():
    rows = [
        FleursRow(i, f"{100 + i}.wav", f"Reference {i}", f"reference {i}", 1600, i + 1)
        for i in range(60)
    ]
    duplicate = FleursRow(0, "999.wav", "Reference 0", "reference 0", 1600, 61)
    selected, exclusions = select_rows(rows + [duplicate], "en_us")
    again, _ = select_rows(list(reversed(rows + [duplicate])), "en_us")
    assert selected == again
    assert len(selected) == len({item.sentence_id for item in selected}) == 50
    assert len(exclusions) == 11
    assert selected == sorted(selected, key=lambda item: item.selection_key("en_us"))


def test_conflicting_sentence_references_quarantine_whole_group():
    rows = [
        FleursRow(i, f"{i + 100}.wav", f"Reference {i}", "script", 1600, i + 1) for i in range(51)
    ]
    rows.append(FleursRow(0, "999.wav", "Conflicting reference", "script", 1600, 52))
    selected, exclusions = select_rows(rows, "ur_pk")
    assert 0 not in {item.sentence_id for item in selected}
    assert sum(item["reason"] == "conflicting-sentence-reference" for item in exclusions) == 2


def test_insufficient_distinct_sentences_blocks_selection():
    records, _ = read_metadata(row() + row(filename="101.wav"))
    with pytest.raises(VoiceError):
        select_rows(records, "en_us", count=2)


def test_physical_metadata_row_count_checked():
    with pytest.raises(VoiceError):
        _metadata_selection(row(), "en_us", 2)


def test_primary_scoring_view_does_not_rewrite_script():
    raw = "  CAFÉ,\x00  متن!\t ا‌ ب  "
    assert scoring_text(raw) == "café متن ا‌ ب"
    assert raw.startswith("  CAFÉ,")
