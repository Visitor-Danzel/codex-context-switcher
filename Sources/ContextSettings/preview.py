"""Fresh local declaration previews; neither catalog trust nor session attestation."""
import datetime
import hashlib
import json
import re
import time
from .config_file import Refused, KEY, parse, patch_window, read_snapshot, public_snapshot, valid_window

TTL = 120
CATALOG_AGE = 24 * 60 * 60

def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Refused('duplicate_source_field')
        result[key] = value
    return result

def json_data(raw):
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refused('invalid_source_number')))
    except (ValueError, UnicodeError, RecursionError):
        raise Refused('unsupported_source') from None

def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.]+)?', value):
        raise Refused('unknown_client_version')
    return value.split('-')[0]

def stamp(value):
    try:
        parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.timestamp()
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise Refused('unknown_source_time') from None

def confirmation(preview):
    material = {k: v for k, v in preview.items() if k != 'confirmation'}
    try:
        return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    except (ValueError, TypeError):
        raise Refused('invalid_preview') from None

def make_preview(config_path, catalog_path, client_metadata_path, model_slug, action):
    if action not in ('set_maximum', 'remove_override'):
        raise Refused('unknown_action')
    config = read_snapshot(config_path, attributes=True)
    data = parse(config['raw'])
    before = data.get(KEY)
    if KEY in data and not valid_window(before):
        raise Refused('invalid_existing_window')
    sources = {'config': public_snapshot(config)}
    after, model = None, None
    now = time.time()
    if action == 'set_maximum':
        if any(k in data for k in ('model_catalog_json', 'profile', 'profiles')) or data.get('model_provider', 'openai') != 'openai':
            raise Refused('non_native_catalog_or_provider')
        catalog = read_snapshot(catalog_path)
        client = read_snapshot(client_metadata_path, system_metadata=True)
        declarations, metadata = json_data(catalog['raw']), json_data(client['raw'])
        if type(declarations) is not dict or type(metadata) is not dict:
            raise Refused('unsupported_source')
        if version(declarations.get('client_version')) != version(metadata.get('version', metadata.get('cliVersion'))):
            raise Refused('client_version_changed')
        age = now - stamp(declarations.get('fetched_at'))
        if not 0 <= age <= CATALOG_AGE:
            raise Refused('declaration_expired')
        rows = declarations.get('models')
        if type(rows) is not list or not 0 < len(rows) <= 2000:
            raise Refused('unknown_models')
        seen = set()
        for row in rows:
            if type(row) is not dict:
                raise Refused('unsupported_model')
            slug = row.get('slug')
            if type(slug) is not str or not slug or len(slug) > 256 or any(ord(c) < 32 for c in slug) or slug in seen:
                raise Refused('ambiguous_model')
            seen.add(slug)
            normal, maximum = row.get('context_window'), row.get('max_context_window')
            if not valid_window(normal) or not valid_window(maximum) or normal > maximum:
                raise Refused('unknown_model_maximum')
            if slug == model_slug:
                retirement = row.get('upgrade')
                if type(retirement) is dict and retirement.get('retirement_at') and stamp(retirement['retirement_at']) <= now:
                    raise Refused('model_retired')
                model, after = slug, maximum
        if model is None:
            raise Refused('model_missing')
        sources.update(catalog=public_snapshot(catalog), client=public_snapshot(client))
    candidate = patch_window(config['raw'], after)
    for source in sources.values():
        current = read_snapshot(source['path'], system_metadata=(source is sources.get('client')))
        if public_snapshot(current) != source:
            raise Refused('source_changed')
    result = {'schema': 1, 'action': action, 'target': config['path'], 'before': before,
              'after': after, 'model': model, 'scope': 'shared_user_file',
              'candidate_sha256': hashlib.sha256(candidate).hexdigest(), 'sources': sources,
              'issued_at': now, 'expires_at': now + TTL, 'session_verified': False,
              'declaration_kind': 'fresh_local_cache' if model else None}
    result['confirmation'] = confirmation(result)
    return result
