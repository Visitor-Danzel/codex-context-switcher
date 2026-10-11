"""Read only the approved configuration/catalog; never infer chat adoption."""
import json
import os
from pathlib import Path
import stat
import sys
import tomllib


def bounded_read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 16 * 1024 * 1024:
            raise ValueError('unsafe input')
        data = b''
        while chunk := os.read(fd, 65536):
            data += chunk
            if len(data) > 16 * 1024 * 1024:
                raise ValueError('oversized input')
        after = os.fstat(fd)
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('input changed')
        return data
    finally:
        os.close(fd)


def readout(config, catalog, official):
    result = {'activation': 'unknown', 'chat_verified': False}
    try:
        config, catalog, official = map(Path, (config, catalog, official))
        raw_config = bounded_read(config)
        settings = tomllib.loads(raw_config.decode())
        if settings.get('profile') or any(k in settings for k in ('model_context_window', 'model_auto_compact_token_limit')):
            return dict(result, activation='override_unverified')
        selected = settings.get('model_catalog_json')
        if selected is None:
            return dict(result, activation='not_configured')
        # Do not follow arbitrary configured paths, even to determine status.
        if not isinstance(selected, str) or selected != str(catalog):
            return dict(result, activation='other_catalog')
        actual = json.loads(bounded_read(catalog))
        baseline = json.loads(bounded_read(official))
        if not isinstance(actual, dict) or not isinstance(baseline, dict):
            return result
        models = actual.get('models')
        reference = baseline.get('models')
        if not isinstance(models, list) or not isinstance(reference, list) or len(models) != len(reference):
            return dict(result, activation='stale_catalog')
        contexts = {}
        for current, default in zip(models, reference):
            if not isinstance(current, dict) or not isinstance(default, dict):
                return dict(result, activation='stale_catalog')
            slug = default.get('slug')
            value = current.get('context_window')
            low, high = default.get('context_window'), default.get('max_context_window')
            if not isinstance(slug, str) or slug in contexts or type(value) is not int or value not in (low, high):
                return dict(result, activation='stale_catalog')
            if {k: v for k, v in current.items() if k != 'context_window'} != {k: v for k, v in default.items() if k != 'context_window'}:
                return dict(result, activation='stale_catalog')
            contexts[slug] = value
        # Root cache metadata may legitimately be present; model metadata must match.
        if bounded_read(config) != raw_config:
            return result
        return dict(result, activation='configured', contexts=contexts)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        return result


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit(2)
    print(json.dumps(readout(*sys.argv[1:]), separators=(',', ':')))
