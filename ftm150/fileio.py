"""Safe file output: atomic writes and the single "don't clobber the input" rule."""
import contextlib
import os
import secrets
from collections.abc import Sequence


def atomic_write(path: str | os.PathLike[str], data: bytes) -> None:
    """Write ``data`` to ``path`` via a same-directory temp file and os.replace.

    Symlinks are written through (the link survives). An existing target keeps
    its file mode; a new file gets the umask default, applied by the kernel.
    On any failure the temp file is removed and the target is left untouched.
    Atomic replace yields a new inode: hard links to the old file are detached
    and ownership/ACLs are not preserved.
    """
    target = os.path.realpath(os.fspath(path))
    directory, name = os.path.split(target)
    mode: int | None
    try:
        mode = os.stat(target).st_mode & 0o7777
    except FileNotFoundError:
        mode = None
    while True:
        tmp = os.path.join(directory, f".{name}.{secrets.token_hex(6)}.tmp")
        try:
            # Existing target: start private (0600) and set its mode before any
            # data is written. New target: 0666 so the kernel applies the umask.
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                         0o600 if mode is not None else 0o666)
            break
        except FileExistsError:
            continue
    owned = False    # True once os.fdopen owns (and will close) the raw fd
    try:
        if mode is not None:
            os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as fh:
            owned = True
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        if not owned:
            with contextlib.suppress(OSError):
                os.close(fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _same(a: str, b: str) -> bool:
    if os.path.realpath(a) == os.path.realpath(b):
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def resolve_output(primary: str, out: str | None, *, others: Sequence[str] = (),
                   in_place: bool = False, same_kind: bool = True) -> str:
    """Return the path to write, refusing to overwrite any input by accident."""
    if out is None:
        if not in_place:
            raise ValueError("an output path is required (or --in-place)")
        out = primary
    if any(_same(out, o) for o in others):
        raise ValueError("out must differ from every input")
    if _same(out, primary):
        if not same_kind:   # no --in-place for this command: don't suggest it
            raise ValueError("out must differ from the input "
                             "(--in-place is not allowed for this command)")
        if not in_place:
            raise ValueError("out must differ from the input; pass --in-place to overwrite it")
    return out
