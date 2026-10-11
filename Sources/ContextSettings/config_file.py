"""Conservative single-key editing. No native service, auth or history access."""
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tomllib

KEY = 'model_context_window'
MAX_BYTES = 4 * 1024 * 1024

class Refused(Exception):
    """Only public reason codes; never include source bytes or exception text."""

def parse(raw):
    try:
        return tomllib.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('unsupported_config') from None

def valid_window(value):
    return type(value) is int and 0 < value <= 9007199254740991

def patch_window(raw: bytes, value: int | None) -> bytes:
    if value is not None and not valid_window(value):
        raise Refused('invalid_window')
    before = parse(raw)
    old = before.get(KEY)
    if KEY in before and not valid_window(old):
        raise Refused('invalid_existing_window')
    if old == value:
        return raw
    expected = dict(before)
    if value is None:
        expected.pop(KEY, None)
    else:
        expected[KEY] = value
    if KEY not in before:
        if value is None:
            return raw
        newline = b'\r\n' if b'\r\n' in raw else b'\n'
        candidate = KEY.encode() + b' = ' + str(value).encode() + newline + raw
    else:
        offset, candidates = 0, []
        pattern = re.compile(rb'([ \t]*model_context_window[ \t]*=[ \t]*)(\+?[0-9][0-9_]*)([ \t]*)(#[^\r\n]*)?(\r?\n)?')
        for line in raw.splitlines(keepends=True):
            match = pattern.fullmatch(line)
            if match:
                try:
                    prefix = parse(raw[:offset])
                    after_line = parse(raw[:offset + len(line)])
                    if KEY not in prefix and after_line.get(KEY) == old:
                        candidates.append((offset, len(line), match))
                except Refused:
                    pass  # Inside an unfinished multiline string is not a key.
            offset += len(line)
        if len(candidates) != 1:
            raise Refused('unsupported_target_format')
        offset, length, match = candidates[0]
        replacement = (match[1] + str(value).encode() + match[3] +
                       (match[4] or b'') + (match[5] or b'')) if value is not None else (
                           (match[4] + (match[5] or b'')) if match[4] else b'')
        candidate = raw[:offset] + replacement + raw[offset + length:]
    if parse(candidate) != expected:
        raise Refused('unrelated_semantic_change')
    return candidate

def identity(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid]

def canonical(path):
    path = Path(path)
    if not path.is_absolute() or len(str(path)) > 4096 or any(ord(c) < 32 for c in str(path)):
        raise Refused('invalid_path')
    return Path(os.path.realpath(path.parent)) / path.name

def read_snapshot(path, max_bytes=MAX_BYTES, *, attributes=False, system_metadata=False):
    path = canonical(path)
    if type(max_bytes) is not int or not 0 < max_bytes <= MAX_BYTES:
        raise Refused('invalid_bound')
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(fd)
        owners = {os.getuid(), 0} if system_metadata else {os.getuid()}
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid not in owners or before.st_size > max_bytes:
            raise Refused('unsafe_file')
        chunks, total = [], 0
        while total <= max_bytes:
            chunk = os.read(fd, min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk); total += len(chunk)
        if total > max_bytes:
            raise Refused('file_too_large')
        file_attributes = {}
        if attributes:
            if getattr(before, 'st_flags', 0):
                raise Refused('unsupported_file_attributes')
            if sys.platform == 'darwin':
                from .attributes import capture
                file_attributes = capture(fd)
                check = subprocess.run(['/bin/ls', '-lde', str(path)], stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2,
                    env={'PATH': '/usr/bin:/bin'}, check=False)
                if check.returncode or len(check.stdout.splitlines()) != 1 or b'+' in check.stdout[:11]:
                    raise Refused('unsupported_file_acl')
            elif not hasattr(os, 'listxattr') or os.listxattr(path, follow_symlinks=False):
                raise Refused('unsupported_file_attributes')
        if identity(before) != identity(os.fstat(fd)) or identity(before) != identity(os.stat(path, follow_symlinks=False)):
            raise Refused('source_changed')
        raw = b''.join(chunks)
        return {'path': str(path), 'raw': raw, 'identity': identity(before),
                'sha256': hashlib.sha256(raw).hexdigest(),
                'parent_identity': identity(os.stat(path.parent, follow_symlinks=False))[:2],
                'attributes': file_attributes}
    except (OSError, subprocess.SubprocessError):
        raise Refused('unavailable_file') from None
    finally:
        if fd >= 0:
            os.close(fd)

def public_snapshot(snapshot):
    return {k: snapshot[k] for k in ('path', 'identity', 'sha256', 'parent_identity')}
