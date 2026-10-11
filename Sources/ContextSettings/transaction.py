"""Bounded user-file transactions under an explicit exclusive-edit condition.

The lock coordinates this tool's instances only. It is not noncooperating CAS.
Prepared/uncertain records never cause automatic rollback on startup.
"""
import contextlib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid
from .attributes import restore
from .config_file import Refused, KEY, canonical, parse, patch_window, read_snapshot, public_snapshot, valid_window
from .preview import TTL, confirmation, json_data, make_preview

def _hash(raw):
    return hashlib.sha256(raw).hexdigest()

def _private_root(path, create=False):
    root = canonical(path)
    if create and not root.exists():
        root.mkdir(mode=0o700, parents=True, exist_ok=False)
    info = os.lstat(root)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise Refused('unsafe_journal')
    if sys.platform=='darwin':
        check=subprocess.run(['/bin/ls','-lde',str(root)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=2,env={'PATH':'/usr/bin:/bin'})
        if check.returncode or len(check.stdout.splitlines())!=1 or b'+' in check.stdout[:11]:
            raise Refused('unsafe_journal_acl')
    return root

def _load(root):
    path = root / 'active.json'
    if not path.exists() and not path.is_symlink():
        return None
    record = json_data(read_snapshot(path)['raw'])
    if type(record) is not dict or record.get('schema') != 1 or not re.fullmatch(r'[a-f0-9]{32}', str(record.get('id', ''))):
        raise Refused('invalid_recovery_record')
    if record.get('phase') not in ('prepared', 'saved', 'undone'):
        raise Refused('invalid_recovery_record')
    return record

def _write_private(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as out:
            out.write(raw); out.flush(); os.fsync(fd)
    finally:
        os.close(fd)

def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def _record(root, record):
    raw = json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    stage = root / ('.record-' + uuid.uuid4().hex + '.tmp')
    _write_private(stage, raw)
    os.replace(stage, root / 'active.json')
    _sync_directory(root)

@contextlib.contextmanager
def _lock(root):
    fd = os.open(root / 'lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise Refused('unsafe_journal_lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refused('transaction_busy') from None
        yield
    finally:
        os.close(fd)

def inspect(config_path, journal_dir):
    snapshot = read_snapshot(config_path)
    data=parse(snapshot['raw']);value=data.get(KEY)
    if KEY in data and not valid_window(value):
        raise Refused('invalid_existing_window')
    result = {'schema': 1, 'state': 'unmanaged', 'window_tokens': value,
              'file_sha256': snapshot['sha256'], 'session_verified': False, 'undo_available': False}
    try:
        root = _private_root(journal_dir)
    except FileNotFoundError:
        return result
    record = _load(root)
    if not record:
        return result
    if record.get('target') != snapshot['path']:
        raise Refused('journal_target_mismatch')
    if record['phase'] == 'prepared':
        result['state'] = 'uncertain'
    elif snapshot['sha256'] != record.get('committed_sha256'):
        result['state'] = 'external_change'
    else:
        result['state'] = record['phase']
        result['undo_available'] = record['phase'] == 'saved'
    return result

def _reverse(raw, record):
    if _hash(raw) != record.get('after_sha256'):
        raise Refused('external_change')
    try:
        offset = record['offset']
        before_span = bytes.fromhex(record['before_span'])
        after_span = bytes.fromhex(record['after_span'])
        if type(offset) is not int or not 0 <= offset <= len(raw) or raw[offset:offset + len(after_span)] != after_span:
            raise Refused('invalid_undo_span')
        candidate = raw[:offset] + before_span + raw[offset + len(after_span):]
    except (KeyError, ValueError, TypeError):
        raise Refused('invalid_undo_span') from None
    if _hash(candidate) != record.get('before_sha256'):
        raise Refused('invalid_undo_span')
    expected = dict(parse(raw))
    previous = parse(candidate).get(KEY)
    if previous is None:
        expected.pop(KEY, None)
    else:
        expected[KEY] = previous
    if parse(candidate) != expected:
        raise Refused('unrelated_semantic_change')
    return candidate

def preview_undo(config_path, journal_dir):
    root = _private_root(journal_dir)
    record = _load(root)
    if not record or record['phase'] != 'saved':
        raise Refused('undo_unavailable')
    snapshot = read_snapshot(config_path, attributes=True)
    if record.get('target') != snapshot['path']:
        raise Refused('journal_target_mismatch')
    candidate = _reverse(snapshot['raw'], record)
    now = time.time()
    result = {'schema': 1, 'action': 'undo', 'target': snapshot['path'], 'before': parse(snapshot['raw']).get(KEY),
              'after': parse(candidate).get(KEY), 'model': None, 'scope': 'shared_user_file',
              'candidate_sha256': _hash(candidate), 'sources': {'config': public_snapshot(snapshot)},
              'issued_at': now, 'expires_at': now + TTL, 'session_verified': False,
              'declaration_kind': None, 'record_id': record['id']}
    result['confirmation'] = confirmation(result)
    return result

def _gate(gate):
    state = gate()
    if type(state) is not dict or state.get('desktop_closed') is not True:
        raise Refused('codex_running_or_unknown')
    if state.get('exclusive_edit') is not True:
        raise Refused('exclusive_edit_not_confirmed')

def _fresh(preview, token):
    now = time.time()
    if type(preview) is not dict or preview.get('schema') != 1 or token != preview.get('confirmation') or token != confirmation(preview):
        raise Refused('invalid_confirmation')
    issued, expires = preview.get('issued_at'), preview.get('expires_at')
    if any(type(v) not in (float, int) or not math.isfinite(v) for v in (issued, expires)) or not issued <= now < expires or not 0 < expires - issued <= TTL:
        raise Refused('preview_expired')

def apply(preview, token, journal_dir, gate):
    _fresh(preview, token)
    _gate(gate)
    root = _private_root(journal_dir, create=True)
    with _lock(root):
        active = _load(root)
        if active and active['phase'] == 'prepared':
            raise Refused('uncertain_previous_transaction')
        sources = preview['sources']
        if preview['action'] == 'undo':
            fresh = preview_undo(preview['target'], root)
        else:
            fresh = make_preview(preview['target'], sources.get('catalog', {}).get('path'),
                sources.get('client', {}).get('path'), preview.get('model'), preview['action'])
        for key in ('action', 'target', 'before', 'after', 'model', 'scope', 'candidate_sha256', 'sources', 'record_id'):
            if fresh.get(key) != preview.get(key):
                raise Refused('preview_changed')
        snapshot = read_snapshot(preview['target'], attributes=True)
        candidate = _reverse(snapshot['raw'], active) if preview['action'] == 'undo' else patch_window(snapshot['raw'], preview['after'])
        if _hash(candidate) != preview['candidate_sha256']:
            raise Refused('candidate_changed')
        if candidate == snapshot['raw']:
            return {**inspect(preview['target'], root), 'state': 'unchanged'}
        record_id = uuid.uuid4().hex
        prefix = 0
        while prefix < min(len(snapshot['raw']), len(candidate)) and snapshot['raw'][prefix] == candidate[prefix]:
            prefix += 1
        suffix = 0
        while suffix < min(len(snapshot['raw']), len(candidate)) - prefix and snapshot['raw'][-suffix - 1] == candidate[-suffix - 1]:
            suffix += 1
        before_end, after_end = len(snapshot['raw']) - suffix, len(candidate) - suffix
        record = {'schema': 1, 'id': record_id, 'phase': 'prepared', 'target': snapshot['path'],
                  'before_sha256': snapshot['sha256'], 'after_sha256': _hash(candidate),
                  'offset': prefix, 'before_span': snapshot['raw'][prefix:before_end].hex(),
                  'after_span': candidate[prefix:after_end].hex(), 'attributes': snapshot['attributes']}
        _write_private(root / (record_id + '.before'), snapshot['raw'])
        _record(root, record)
        stage = Path(snapshot['path']).parent / ('.codex-context-' + record_id + '.tmp')
        fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        published = False
        try:
            with os.fdopen(fd, 'wb', closefd=False) as out:
                out.write(candidate); out.flush()
                os.fchown(fd, -1, snapshot['identity'][7])
                os.fchmod(fd, snapshot['identity'][5])
                restore(fd, snapshot['attributes']); os.fsync(fd)
            os.close(fd); fd = -1
            for name, source in sources.items():
                current = read_snapshot(source['path'], system_metadata=(name == 'client'))
                if public_snapshot(current) != source:
                    raise Refused('source_changed')
            if public_snapshot(read_snapshot(snapshot['path'], attributes=True)) != public_snapshot(snapshot):
                raise Refused('source_changed')
            _gate(gate)
            os.replace(stage, snapshot['path']); published = True
            _sync_directory(Path(snapshot['path']).parent)
            readback = read_snapshot(snapshot['path'], attributes=True)
            if readback['raw'] != candidate or readback['attributes'] != snapshot['attributes']:
                raise Refused('readback_uncertain')
            _gate(gate)
            record['phase'] = 'undone' if preview['action'] == 'undo' else 'saved'
            record['committed_sha256'] = readback['sha256']
            _record(root, record)
            return inspect(snapshot['path'], root)
        finally:
            if fd >= 0:
                os.close(fd)
            if not published and stage.exists():
                stage.unlink()
            # On any post-prepare failure retain the prepared journal and backup.
