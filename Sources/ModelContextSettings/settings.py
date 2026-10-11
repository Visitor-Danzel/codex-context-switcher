"""Immutable complete catalogs and a reversible, single-key config transaction.

The caller must pin paths and require exclusive editing with Codex closed.
No automatic writes, startup rollback, model routing, or private service calls.
"""
import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid
from ContextSettings.attributes import restore
from ContextSettings.config_file import (Refused, parse, read_snapshot, public_snapshot,
                                         canonical, valid_window)
from ContextSettings.preview import json_data, confirmation, TTL
from ContextSettings.transaction import (_private_root, _load, _write_private, _record,
    _sync_directory, _lock, _gate, _fresh)

KEY = 'model_catalog_json'

@dataclass(frozen=True)
class Paths:
    config: Path
    official: Path
    record: Path
    client: Path
    native: Path
    root: Path
    legacy: Path

    @property
    def journal(self): return self.root / 'journal'


def digest(raw): return hashlib.sha256(raw).hexdigest()


def patch_catalog(raw, value):
    """Edit one ordinary root TOML string, verifying all other parsed values."""
    if value is not None and (type(value) is not str or not Path(value).is_absolute() or
                             len(value)>4096 or any(ord(c)<32 for c in value)):
        raise Refused('invalid_catalog_path')
    before=parse(raw); old=before.get(KEY)
    if KEY in before and type(old) is not str: raise Refused('invalid_existing_catalog')
    if old==value:return raw
    expected=dict(before)
    if value is None: expected.pop(KEY,None)
    else: expected[KEY]=value
    if KEY not in before:
        newline=b'\r\n' if b'\r\n' in raw else b'\n'
        candidate=(KEY+' = '+json.dumps(value,ensure_ascii=False)).encode()+newline+raw
    else:
        pattern=re.compile(rb'([ \t]*(?:model_catalog_json|"model_catalog_json"|\x27model_catalog_json\x27)[ \t]*=[ \t]*)("(?:[^"\\\r\n]|\\.)*"|\x27[^\x27\r\n]*\x27)([ \t]*)(#[^\r\n]*)?(\r?\n)?')
        offset=0; spans=[]
        for line in raw.splitlines(keepends=True):
            match=pattern.fullmatch(line)
            if match:
                try:
                    prefix=parse(raw[:offset]); end=parse(raw[:offset+len(line)])
                    if KEY not in prefix and end.get(KEY)==old:spans.append((offset,len(line),match))
                except Refused:pass
            offset+=len(line)
        if len(spans)!=1:raise Refused('unsupported_target_format')
        offset,length,m=spans[0]
        replacement=(m[1]+json.dumps(value,ensure_ascii=False).encode()+m[3]+(m[4] or b'')+(m[5] or b'')) if value is not None else ((m[4]+(m[5] or b'')) if m[4] else b'')
        candidate=raw[:offset]+replacement+raw[offset+length:]
    if parse(candidate)!=expected:raise Refused('unrelated_semantic_change')
    return candidate


def native_hash(path):
    fd=-1
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size>1024**3:raise Refused('runtime_changed')
        h=hashlib.sha256();total=0
        while True:
            chunk=os.read(fd,65536)
            if not chunk:break
            total+=len(chunk)
            if total>1024**3:raise Refused('runtime_changed')
            h.update(chunk)
        after=os.fstat(fd); current=os.stat(path,follow_symlinks=False)
        identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if identity(before)!=identity(after) or identity(before)!=identity(current):raise Refused('runtime_changed')
        return h.hexdigest()
    except OSError:raise Refused('runtime_changed') from None
    finally:
        if fd>=0:os.close(fd)


def sources(paths):
    official=read_snapshot(paths.official);record=read_snapshot(paths.record)
    data=json_data(official['raw']); declaration=json_data(record['raw'])
    if type(data) is not dict or type(declaration) is not dict or digest(official['raw'])!=declaration.get('catalog_sha256'):
        raise Refused('catalog_source_changed')
    rows=data.get('models')
    if type(rows) is not list or not 0<len(rows)<=100:raise Refused('unknown_models')
    seen=set()
    for row in rows:
        if type(row) is not dict:raise Refused('unsupported_model')
        slug=row.get('slug');normal=row.get('context_window');maximum=row.get('max_context_window')
        if type(slug) is not str or not slug or len(slug)>256 or any(ord(c)<32 for c in slug) or slug in seen:
            raise Refused('ambiguous_model')
        seen.add(slug)
        if not valid_window(normal) or not valid_window(maximum) or normal>maximum:raise Refused('unknown_model_maximum')
    fingerprints={'official':public_snapshot(official),'record':public_snapshot(record)}
    compatible=False
    try:
        client=read_snapshot(paths.client,system_metadata=True)
        compatible=(json_data(client['raw']).get('version')==declaration.get('cli_version') and
                    native_hash(paths.native)==declaration.get('native_sha256'))
        fingerprints['client']=public_snapshot(client)
    except (Refused,AttributeError):pass
    return data,declaration,compatible,fingerprints


def _owned_catalog(paths,value):
    p=Path(value)
    return p.parent==paths.root/'catalogs' and re.fullmatch(r'[a-f0-9]{64}\.json',p.name) is not None


def _selection(data,official):
    if type(data) is not dict or set(data)!=set(official) or any(data[k]!=official[k] for k in official if k!='models'):
        raise Refused('damaged_catalog')
    rows=data.get('models'); normal=official['models']
    if type(rows) is not list or len(rows)!=len(normal):raise Refused('damaged_catalog')
    selected=[]
    for a,b in zip(rows,normal):
        if type(a) is not dict or set(a)!=set(b) or any(a[k]!=b[k] for k in b if k!='context_window'):
            raise Refused('damaged_catalog')
        value=a.get('context_window')
        if type(value) is not int or value not in (b['context_window'],b['max_context_window']):raise Refused('damaged_catalog')
        if value>b['context_window']:selected.append(b['slug'])
    return selected


def _current(paths,config,official):
    data=parse(config['raw']);value=data.get(KEY)
    if value is None:return 'default',[],None
    if type(value) is not str:return 'other_catalog',[],None
    owned=_owned_catalog(paths,value);legacy=value==str(paths.legacy)
    if not owned and not legacy:return 'other_catalog',[],None
    try:
        snapshot=read_snapshot(value)
        if owned and digest(snapshot['raw'])+'.json'!=Path(value).name:raise Refused('damaged_catalog')
        selected=_selection(json_data(snapshot['raw']),official)
        return ('configured' if owned else 'legacy_configured'),selected,snapshot
    except Refused:return ('damaged_catalog' if owned else 'legacy_stale'),[],None


def _journal_status(paths,config):
    try:root=_private_root(paths.journal)
    except FileNotFoundError:return 'unmanaged',False
    record=_load(root)
    if not record:return 'unmanaged',False
    if record.get('target')!=config['path']:raise Refused('journal_target_mismatch')
    if record['phase']=='prepared':return 'uncertain',False
    if config['sha256']!=record.get('committed_sha256'):return 'external_change',False
    return record['phase'],record['phase']=='saved'


def inspect(paths):
    config=read_snapshot(paths.config)
    official,record,compatible,_=sources(paths)
    state,selected,_=_current(paths,config,official)
    data=parse(config['raw']);conflict=any(k in data for k in ('model_context_window','model_auto_compact_token_limit','profile','profiles')) or data.get('model_provider','openai')!='openai'
    transaction_state,undo=_journal_status(paths,config)
    if read_snapshot(paths.config)['sha256']!=config['sha256']:raise Refused('source_changed')
    return {'schema':1,'state':state,'selected':selected,'runtime_compatible':compatible,
            'configuration_conflict':conflict,'undo_available':undo,'transaction_state':transaction_state,
            'cli_version':record.get('cli_version'),'session_verified':False,
            'models':[{'slug':m['slug'],'name':m.get('display_name',m['slug']),
                       'default':m['context_window'],'maximum':m['max_context_window'],
                       'can_extend':m['max_context_window']>m['context_window'],
                       'hidden':m.get('visibility')=='hide'} for m in official['models']]}


def _reverse(raw,record):
    if digest(raw)!=record.get('after_sha256'):raise Refused('external_change')
    try:
        offset=record['offset'];before=bytes.fromhex(record['before_span']);after=bytes.fromhex(record['after_span'])
        if type(offset) is not int or not 0<=offset<=len(raw) or raw[offset:offset+len(after)]!=after:raise Refused('invalid_undo_span')
        candidate=raw[:offset]+before+raw[offset+len(after):]
        if digest(candidate)!=record.get('before_sha256'):raise Refused('invalid_undo_span')
        expected=dict(parse(raw));old=parse(candidate).get(KEY)
        if old is None:expected.pop(KEY,None)
        else:expected[KEY]=old
        if parse(candidate)!=expected:raise Refused('unrelated_semantic_change')
        return candidate
    except (KeyError,ValueError,TypeError):raise Refused('invalid_undo_span') from None


def make_preview(paths,action,selection):
    if action not in ('save','defaults','undo','recover'):raise Refused('unknown_action')
    config=read_snapshot(paths.config,attributes=True);data=parse(config['raw'])
    fingerprints={'config':public_snapshot(config)};record_id=None;catalog_raw=None
    if action=='recover':
        record=_load(_private_root(paths.journal))
        if not record or record['phase']!='prepared':raise Refused('recovery_unavailable')
        if record.get('target')!=config['path']:raise Refused('journal_target_mismatch')
        backup=read_snapshot(paths.journal/(record['id']+'.before'))
        if backup['sha256']!=record.get('before_sha256'):raise Refused('invalid_recovery_record')
        if config['sha256']==record.get('after_sha256'):
            if _reverse(config['raw'],record)!=backup['raw']:raise Refused('invalid_recovery_record')
        elif config['sha256']==record.get('before_sha256'):
            offset=record.get('offset');before=bytes.fromhex(record.get('before_span',''));after_span=bytes.fromhex(record.get('after_span',''))
            if type(offset) is not int or not 0<=offset<=len(config['raw']) or config['raw'][offset:offset+len(before)]!=before:raise Refused('invalid_recovery_record')
            after_raw=config['raw'][:offset]+after_span+config['raw'][offset+len(before):]
            if _reverse(after_raw,record)!=backup['raw']:raise Refused('invalid_recovery_record')
        else:raise Refused('external_change')
        candidate=config['raw'];after=data.get(KEY);selection=[];record_id=record['id']
        fingerprints['backup']=public_snapshot(backup)
    elif action=='undo':
        record=_load(_private_root(paths.journal))
        if not record or record['phase']!='saved':raise Refused('undo_unavailable')
        if record.get('target')!=config['path']:raise Refused('journal_target_mismatch')
        candidate=_reverse(config['raw'],record);after=parse(candidate).get(KEY);selection=[];record_id=record['id']
    else:
        if type(selection) is not list or any(type(s) is not str for s in selection) or len(set(selection))!=len(selection):raise Refused('invalid_selection')
        official,_,compatible,source_files=sources(paths)
        if not compatible:raise Refused('runtime_changed')
        if any(k in data for k in ('model_context_window','model_auto_compact_token_limit','profile','profiles')) or data.get('model_provider','openai')!='openai':raise Refused('configuration_override')
        state,_,current=_current(paths,config,official)
        if state in ('other_catalog','damaged_catalog'):raise Refused(state)
        # A stale legacy catalog can be explicitly replaced; the old file remains intact.
        allowed={r['slug'] for r in official['models'] if r['max_context_window']>r['context_window']}
        if not set(selection)<=allowed:raise Refused('invalid_selection')
        selection=sorted(selection)
        if action=='defaults':selection=[];after=None
        else:
            catalog=copy.deepcopy(official)
            for row in catalog['models']:
                if row['slug'] in selection:
                    retired=row.get('upgrade',{}).get('retirement_at') if type(row.get('upgrade')) is dict else None
                    if retired:
                        from ContextSettings.preview import stamp
                        if stamp(retired)<=time.time():raise Refused('model_retired')
                    row['context_window']=row['max_context_window']
            catalog_raw=json.dumps(catalog,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
            after=str(paths.root/'catalogs'/(digest(catalog_raw)+'.json'))
        candidate=patch_catalog(config['raw'],after)
        fingerprints.update(source_files)
        if current:fingerprints['current_catalog']=public_snapshot(current)
    now=time.time()
    preview={'schema':1,'action':action,'target':config['path'],'before':data.get(KEY),'after':after,
             'selected':selection,'candidate_sha256':digest(candidate),'catalog_sha256':digest(catalog_raw) if catalog_raw else None,
             'sources':fingerprints,'record_id':record_id,'issued_at':now,'expires_at':now+TTL,
             'session_verified':False}
    preview['confirmation']=confirmation(preview)
    return preview


def _install_catalog(paths,preview):
    official,_,compatible,_=sources(paths)
    if not compatible:raise Refused('runtime_changed')
    catalog=copy.deepcopy(official)
    for row in catalog['models']:
        if row['slug'] in preview['selected']:row['context_window']=row['max_context_window']
    raw=json.dumps(catalog,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    if digest(raw)!=preview['catalog_sha256']:raise Refused('catalog_source_changed')
    root=_private_root(paths.root/'catalogs',create=True);target=root/(digest(raw)+'.json')
    if str(target)!=preview['after']:raise Refused('request_target_mismatch')
    if target.exists() or target.is_symlink():
        if read_snapshot(target)['raw']!=raw:raise Refused('damaged_catalog')
    else:
        _write_private(target,raw);os.chmod(target,0o400);_sync_directory(root)


def apply(paths,preview,token,gate):
    _fresh(preview,token);_gate(gate)
    _private_root(paths.root,create=True);root=_private_root(paths.journal,create=True)
    with _lock(root):
        active=_load(root)
        if active and active['phase']=='prepared' and preview['action']!='recover':raise Refused('uncertain_previous_transaction')
        fresh=make_preview(paths,preview['action'],preview.get('selected'))
        for key in ('action','target','before','after','selected','candidate_sha256','catalog_sha256','sources','record_id'):
            if fresh.get(key)!=preview.get(key):raise Refused('preview_changed')
        snapshot=read_snapshot(paths.config,attributes=True)
        if preview['action']=='recover':
            _gate(gate)
            if snapshot['sha256']!=preview['candidate_sha256']:raise Refused('source_changed')
            active['phase']='saved' if snapshot['sha256']==active['after_sha256'] else 'undone'
            active['committed_sha256']=snapshot['sha256'];_record(root,active)
            return inspect(paths)
        candidate=_reverse(snapshot['raw'],active) if preview['action']=='undo' else patch_catalog(snapshot['raw'],preview['after'])
        if digest(candidate)!=preview['candidate_sha256']:raise Refused('candidate_changed')
        if candidate==snapshot['raw']:return inspect(paths)
        if preview['action']=='save':_install_catalog(paths,preview)
        record_id=uuid.uuid4().hex;prefix=0;suffix=0
        while prefix<min(len(snapshot['raw']),len(candidate)) and snapshot['raw'][prefix]==candidate[prefix]:prefix+=1
        while suffix<min(len(snapshot['raw']),len(candidate))-prefix and snapshot['raw'][-suffix-1]==candidate[-suffix-1]:suffix+=1
        record={'schema':1,'id':record_id,'phase':'prepared','target':snapshot['path'],
                'before_sha256':snapshot['sha256'],'after_sha256':digest(candidate),'offset':prefix,
                'before_span':snapshot['raw'][prefix:len(snapshot['raw'])-suffix].hex(),
                'after_span':candidate[prefix:len(candidate)-suffix].hex(),'attributes':snapshot['attributes']}
        _write_private(root/(record_id+'.before'),snapshot['raw']);_record(root,record)
        stage=Path(snapshot['path']).parent/('.codex-context-'+record_id+'.tmp')
        fd=os.open(stage,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);published=False
        try:
            with os.fdopen(fd,'wb',closefd=False) as out:
                out.write(candidate);out.flush();os.fchown(fd,-1,snapshot['identity'][7]);os.fchmod(fd,snapshot['identity'][5])
                restore(fd,snapshot['attributes']);os.fsync(fd)
            os.close(fd);fd=-1
            for name,source in preview['sources'].items():
                if public_snapshot(read_snapshot(source['path'],system_metadata=name=='client'))!=source:raise Refused('source_changed')
            if preview['action']=='save':
                if native_hash(paths.native)!=json_data(read_snapshot(paths.record)['raw'])['native_sha256']:raise Refused('runtime_changed')
                if digest(read_snapshot(preview['after'])['raw'])!=preview['catalog_sha256']:raise Refused('damaged_catalog')
            if public_snapshot(read_snapshot(paths.config,attributes=True))!=public_snapshot(snapshot):raise Refused('source_changed')
            _gate(gate);os.replace(stage,snapshot['path']);published=True;_sync_directory(Path(snapshot['path']).parent)
            readback=read_snapshot(paths.config,attributes=True)
            if readback['raw']!=candidate or readback['attributes']!=snapshot['attributes']:raise Refused('readback_uncertain')
            _gate(gate);record['phase']='undone' if preview['action']=='undo' else 'saved';record['committed_sha256']=readback['sha256'];_record(root,record)
            return inspect(paths)
        finally:
            if fd>=0:os.close(fd)
            if not published and stage.exists():stage.unlink()
            # Prepared records and backups remain after uncertain writes. Never auto restore.
