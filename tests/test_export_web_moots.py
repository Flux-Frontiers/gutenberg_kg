"""Moot packs for the web forest: shape, ids, the index and the command."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner
from test_entmoot import A, B, FakeClient, FakeSynth

from gutenberg_kg.export_web_moots import (
    PACK_VERSION,
    MootPackError,
    index_entry,
    moot_id,
    moot_pack,
    write_moots,
)
from gutenberg_kg.serve.entmoot import run_moot


def _transcript(topic="jealousy", started="2026-10-21T12:00:00-04:00", reply=None):
    synth = FakeSynth([reply or 'Hear me: "jealousy is a dredful thing" [s1].'])
    data = run_moot(FakeClient(), synth, [A, B], topic, 2).to_dict()
    data["run"] = {"started": started, "backend": "omlx"}
    return data


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


def test_a_pack_carries_what_the_reader_sees():
    pack = moot_pack(_transcript())
    assert pack["version"] == PACK_VERSION
    assert pack["date"] == "2026-10-21"
    assert pack["backend"] == "omlx"
    assert [t["key"] for t in pack["trees"]] == [A, B]
    first, second = pack["turns"]
    assert (first["turn"], first["speaker"], second["speaker"]) == (1, 0, 1)
    assert first["text"] == 'Hear me: "jealousy is a dreadful thing" [s1].'  # snapped
    assert first["cites"] == [{"tag": "s1", "label": "chunk:0001", "node_id": f"{A}#1"}]
    assert first["snaps"][0] == {
        "text": "jealousy is a dredful thing",
        "action": "snapped",
        "to": "jealousy is a dreadful thing",
        "reason": None,
    }
    assert "raw_text" not in json.dumps(pack)
    assert "query" not in first


def test_the_id_is_both_books_and_the_topic():
    assert moot_id(_transcript()) == "thus-spake-zarathustra-the-diary-of-somebody-jealousy"
    assert moot_id(_transcript(topic=None)) == "thus-spake-zarathustra-the-diary-of-somebody"


def test_a_transcript_without_a_run_has_no_date():
    data = _transcript()
    del data["run"]
    assert moot_pack(data)["date"] == ""


def test_index_entry_titles_the_moot():
    entry = index_entry(moot_pack(_transcript()))
    assert entry["title"] == "Thus Spake Zarathustra and The Diary of Somebody on jealousy"
    assert (entry["turns"], entry["trees"]) == (2, [A, B])
    assert index_entry(moot_pack(_transcript(topic=None)))["title"] == (
        "Thus Spake Zarathustra and The Diary of Somebody"
    )


def test_write_moots_merges_the_index_by_id(tmp_path):
    out = tmp_path / "moots"
    first = _write(tmp_path, "a.json", _transcript(started="2026-10-20T09:00:00"))
    other = _write(tmp_path, "b.json", _transcript(topic="death", started="2026-10-21T09:00:00"))
    assert write_moots([first, other], out) == [
        "thus-spake-zarathustra-the-diary-of-somebody-jealousy",
        "thus-spake-zarathustra-the-diary-of-somebody-death",
    ]
    again = _write(
        tmp_path, "c.json", _transcript(started="2026-10-22T09:00:00", reply="Again [s1].")
    )
    write_moots([again], out)
    index = json.loads((out / "index.json").read_text())
    assert [e["id"] for e in index] == [  # newest first, the re-run replacing its entry
        "thus-spake-zarathustra-the-diary-of-somebody-jealousy",
        "thus-spake-zarathustra-the-diary-of-somebody-death",
    ]
    assert index[0]["date"] == "2026-10-22"
    pack = json.loads((out / f"{index[0]['id']}.json").read_text())
    assert pack["turns"][0]["text"] == "Again [s1]."


def test_a_file_that_is_not_a_transcript_is_a_clean_error(tmp_path):
    bad = _write(tmp_path, "bad.json", {"trees": []})
    with pytest.raises(MootPackError, match="bad.json"):
        write_moots([bad], tmp_path / "moots")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    with pytest.raises(MootPackError, match="broken.json"):
        write_moots([broken], tmp_path / "moots")


def test_the_command_writes_packs(tmp_path):
    pytest.importorskip("kg_rag", reason="kg_rag not installed")
    from gutenberg_kg.cli.main import cli

    src = _write(tmp_path, "moot.json", _transcript())
    out = tmp_path / "moots"
    result = CliRunner().invoke(cli, ["export-web-moots", str(src), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "wrote 1 moot pack(s)" in result.output
    assert (out / "thus-spake-zarathustra-the-diary-of-somebody-jealousy.json").is_file()
    bad = _write(tmp_path, "bad.json", {"trees": []})
    result = CliRunner().invoke(cli, ["export-web-moots", str(bad), "--out", str(out)])
    assert result.exit_code == 1
    assert "not a converse transcript" in result.output
