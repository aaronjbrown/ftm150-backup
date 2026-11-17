import itertools
from pathlib import Path

import pytest

from ftm150.engine import partial as P  # noqa: N812
from ftm150.engine.image import CloneImage, MemoryImage, SetupImage
from ftm150.engine.partial import Kind
from ftm150.ops import load_image, save_image
from tests.files import ALL_A, ALL_B, MEMORY_B, SETUP_B, load


def read(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def test_detect_kind_by_size() -> None:
    kinds = [P.detect_kind(read(p)) for p in (ALL_B, MEMORY_B, SETUP_B)]
    assert kinds == [Kind.ALL, Kind.MEMORY, Kind.SETUP]


def test_detect_kind_rejects_unknown_size() -> None:
    with pytest.raises(ValueError, match=r"98304.*41472.*1024"):
        P.detect_kind(b"\x00" * 720)


@pytest.mark.parametrize("path,kind", [(MEMORY_B, Kind.MEMORY), (SETUP_B, Kind.SETUP)])
def test_partial_equals_its_cln_blocks(path: str, kind: str) -> None:
    assert P.extract(read(ALL_B), kind) == read(path)


@pytest.mark.parametrize(
    "path,kind", [(MEMORY_B, Kind.MEMORY), (SETUP_B, Kind.SETUP), (ALL_B, Kind.ALL)])
def test_expand_extract_round_trip(path: str, kind: str) -> None:
    buf = P.expand(read(path), kind)
    assert len(buf) == 0x18000 and P.extract(buf, kind) == read(path)


def test_expand_fills_uncovered_with_ff() -> None:
    assert set(P.expand(read(SETUP_B), Kind.SETUP)[0x800:0x4670]) == {0xFF}


def test_covers() -> None:
    assert P.covers(Kind.MEMORY, 0x800, 0x4670) and not P.covers(Kind.MEMORY, 0x100, 0x150)
    assert P.covers(Kind.SETUP, 0xA0, 0x100) and not P.covers(Kind.SETUP, 0x1F0, 0x240)
    assert P.covers(Kind.MEMORY, 0x180, 0x280) and P.covers(Kind.ALL, 0, 0x18000)


def test_merge_ranges_owner_masked() -> None:
    mem, setup = P.merge_ranges(Kind.MEMORY), P.merge_ranges(Kind.SETUP)

    def owns(rs: list[tuple[int, int]], i: int) -> bool:
        return any(lo <= i < hi for lo, hi in rs)

    assert not owns(mem, 0x180) and owns(mem, 0x1A0) and owns(mem, 0x1F0) and owns(mem, 0x200)
    assert owns(setup, 0x180) and not owns(setup, 0x1A0) and not owns(setup, 0x1F0)
    assert not owns(mem, 0x00) and not owns(setup, 0x7F)
    for rs in (mem, setup):
        assert rs == sorted(rs) and all(a[1] < b[0] for a, b in itertools.pairwise(rs))


@pytest.mark.parametrize(
    "path,kind", [(ALL_B, Kind.ALL), (MEMORY_B, Kind.MEMORY), (SETUP_B, Kind.SETUP)])
def test_load_image_round_trips(path: str, kind: str) -> None:
    img = load_image(path)
    assert img.kind == kind and img.to_bytes() == read(path)


def test_clone_views_share_buffer() -> None:
    clone = load(CloneImage, ALL_B)
    clone.memory.channels[1].power = "LOW"
    assert CloneImage(clone.to_bytes()).memory.channels[1].power == "LOW"
    assert not hasattr(clone, "channels") and not hasattr(clone, "settings")


def test_partial_values_match_clone() -> None:
    clone = load(CloneImage, ALL_B)
    mem, setup = load(MemoryImage, MEMORY_B), load(SetupImage, SETUP_B)
    for (n, got), want in zip(mem.channels.items(), clone.memory.channels, strict=True):
        assert got.raw == want.raw and got.name == want.name, n
        if want.enabled:
            assert got.to_record() == want.to_record(), n
    for (n, got_pair), want_pair in zip(mem.pms.items(), clone.memory.pms, strict=True):
        assert (got_pair.lower.raw, got_pair.upper.raw) == (
            want_pair.lower.raw, want_pair.upper.raw), n
    bands = range(5)  # each VFO/Home block is 0x50 bytes: 5 slots of BAND_STRIDE
    for name, part, full in (("home_a", mem.home_a, clone.memory.home_a),
                             ("home_b", mem.home_b, clone.memory.home_b),
                             ("vfo_a", setup.vfo_a, clone.setup.vfo_a),
                             ("vfo_b", setup.vfo_b, clone.setup.vfo_b)):
        for b in bands:
            assert part[b].raw == full[b].raw, (name, b)
    for setting in ("apo", "scan_resume_a", "scan_resume_b"):
        assert getattr(setup.settings, setting) == getattr(clone.setup.settings, setting)


def test_exposure_list_spec_2b() -> None:
    """Spec 2b exposure list, from the measured restore behaviour."""
    mem, setup = load(MemoryImage, MEMORY_B), load(SetupImage, SETUP_B)
    assert hasattr(mem, "home_a") and hasattr(mem, "home_b")
    assert not hasattr(setup, "home_a")
    for name in ("channels", "pms", "home_a", "home_b"):
        assert hasattr(mem, name), name
    for name in ("settings", "vfo_a", "vfo_b"):
        assert hasattr(setup, name), name
    for name in ("settings", "vfo_a", "vfo_b"):
        assert not hasattr(mem, name), name
    for name in ("channels", "pms", "home_a", "home_b"):
        assert not hasattr(setup, name), name


def test_edit_and_save_memory_keeps_memory_format(tmp_path: Path) -> None:
    img = load(MemoryImage, MEMORY_B)
    img.channels[999].name = "TEST999"
    out = tmp_path / "MEMFTM15001.dat"
    save_image(img, out)
    assert out.stat().st_size == 0xA200
    back = load(MemoryImage, out)
    assert back.channels[999].name == "TEST999"
    diff = [i for i, (a, b) in
            enumerate(zip(read(MEMORY_B), read(str(out)), strict=True)) if a != b]
    assert diff and all(0x9A60 <= i < 0x9A70 or 0x4E7C <= i < 0x4E7E for i in diff)


def test_save_setup_and_clone_sizes(tmp_path: Path) -> None:
    s, c = tmp_path / "s.dat", tmp_path / "c.dat"
    save_image(load(SetupImage, SETUP_B), s)
    save_image(load(CloneImage, ALL_B), c)
    assert read(str(s)) == read(SETUP_B) and read(str(c)) == read(ALL_B)


def test_magic_ok_all_kinds() -> None:
    assert all(load_image(p).magic_ok for p in (ALL_B, MEMORY_B, SETUP_B))


def test_wrong_kind_rejected() -> None:
    with pytest.raises(ValueError):
        load(MemoryImage, SETUP_B)
    with pytest.raises(ValueError):
        SetupImage.from_bytes(read(MEMORY_B))
    with pytest.raises(ValueError, match=r"98304.*41472.*1024"):
        CloneImage(read(MEMORY_B))


def test_merge_ranges_refuses_all() -> None:
    with pytest.raises(ValueError, match="not a partial"):
        P.merge_ranges(Kind.ALL)


def test_merge_ranges_exact() -> None:
    assert P.merge_ranges(Kind.MEMORY) == [
        (0x1A0, 0x280), (0x480, 0x500), (0x800, 0x6200), (0x10000, 0x14600)]
    assert P.merge_ranges(Kind.SETUP) == [(0x80, 0x1A0), (0x280, 0x300), (0x500, 0x580)]


def test_merge_both_applies_owner_precedence() -> None:
    base = load(CloneImage, ALL_A)
    before = base.to_bytes()
    mem, setup = load(MemoryImage, MEMORY_B), load(SetupImage, SETUP_B)
    setup._buf[0x1A0] ^= 0x01
    mem._buf[0x180] ^= 0x01  # make shared-block copies disagree
    base.merge(memory=mem, setup=setup)
    after = base.to_bytes()
    assert after[0x180:0x1A0] == bytes(setup._buf[0x180:0x1A0])
    assert after[0x1A0:0x200] == bytes(mem._buf[0x1A0:0x200])
    allowed = P.merge_ranges(Kind.MEMORY) + P.merge_ranges(Kind.SETUP)
    assert all(any(lo <= i < hi for lo, hi in allowed)
               for i in range(len(after)) if after[i] != before[i])


def test_merge_single_partial_leaves_other_owners_bytes() -> None:
    base = load(CloneImage, ALL_A)
    before = base.to_bytes()
    mem = load(MemoryImage, MEMORY_B)
    mem._buf[0x180] ^= 0x01       # inside the SETUP owner's slice of the MEMORY backup
    base.merge(memory=mem)
    assert base.to_bytes()[0x180:0x1A0] == before[0x180:0x1A0]
    base2 = load(CloneImage, ALL_A)
    setup = load(SetupImage, SETUP_B)
    setup._buf[0x1A0] ^= 0x01     # inside the MEMORY owner's slice of the SETUP backup
    base2.merge(setup=setup)
    assert base2.to_bytes()[0x1A0:0x200] == before[0x1A0:0x200]


def test_split_then_merge_reproduces_clone() -> None:
    full = load(CloneImage, ALL_B)
    base = load(CloneImage, ALL_A)
    base.merge(memory=MemoryImage.from_bytes(full.memory.to_bytes()),
               setup=SetupImage.from_bytes(full.setup.to_bytes()))
    assert base.memory.to_bytes() == read(MEMORY_B) and base.setup.to_bytes() == read(SETUP_B)


def test_merge_rejects_header_mismatch() -> None:
    mem = load(MemoryImage, MEMORY_B)
    mem._buf[0x10] ^= 0xFF
    with pytest.raises(ValueError, match="header block differs"):
        load(CloneImage, ALL_A).merge(memory=mem)


def test_merge_rejects_bad_args() -> None:
    with pytest.raises(ValueError):
        load(CloneImage, ALL_A).merge()
    with pytest.raises(ValueError):
        load(CloneImage, ALL_A).merge(memory=load(SetupImage, SETUP_B))  # type: ignore[arg-type]


def test_merge_validates_before_writing() -> None:
    base = load(CloneImage, ALL_A)
    before = base.to_bytes()
    mem = load(MemoryImage, MEMORY_B)
    mem._buf[0x800] ^= 0xFF
    setup = load(SetupImage, SETUP_B)
    setup._buf[0x10] ^= 0xFF
    with pytest.raises(ValueError, match="SETUP"):
        base.merge(memory=mem, setup=setup)
    assert base.to_bytes() == before


def test_merge_writes_in_place_visible_to_live_channel() -> None:
    base = load(CloneImage, ALL_A)
    ch = base.memory.channels[1]  # obtained BEFORE the merge
    mem = load(MemoryImage, MEMORY_B)
    mem._buf[0x800] ^= 0x01
    assert ch.raw != mem.channels[1].raw
    base.merge(memory=mem)
    assert ch.raw == mem.channels[1].raw


def test_owns_partition_shared_exactly() -> None:
    mem, setup = P.LAYOUTS[Kind.MEMORY].owns, P.LAYOUTS[Kind.SETUP].owns
    assert mem is not None and setup is not None and P.LAYOUTS[Kind.ALL].owns is None
    first, second = sorted((mem, setup))
    assert first.hi == second.lo and (first.lo, second.hi) == (P.SHARED.lo, P.SHARED.hi)
    assert set(range(*mem)).isdisjoint(range(*setup))
    assert set(range(*mem)) | set(range(*setup)) == set(range(*P.SHARED))


@pytest.mark.parametrize("kind", [Kind.MEMORY, Kind.SETUP])
def test_block_cln_inside_mapped_coverage(kind: P.Kind) -> None:
    layout = P.LAYOUTS[kind]
    for b in layout.blocks:
        assert b.cln == P.Span(b.cln_off, b.cln_off + b.length)
        assert P.covers(kind, b.cln.lo, b.cln.hi)
        assert b.file_off + b.length <= layout.size
    assert P.HEADER == (0x00, 0x80)
