"""Single bounded request; no credentials, native CLI, networking or gate bypass."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ContextSettings import transaction
    from ContextSettings.config_file import Refused, canonical, read_snapshot
    from ContextSettings.preview import json_data, make_preview
else:
    from . import transaction
    from .config_file import Refused, canonical, read_snapshot
    from .preview import json_data, make_preview

CLIENT='/Applications/ChatGPT.app/Contents/Resources/codex-cli/codex-package.json'

def validate_paths(config, catalog, client, journal):
    paths=[canonical(str(p)) for p in (config,catalog,client,journal)]
    # The GUI pins its own home paths in the sandbox; no directory-service
    # lookup or inherited HOME is required inside a deny-default worker.
    home=paths[0].parent.parent
    defaults=[home/'.codex/config.toml',home/'.codex/models_cache.json',Path(CLIENT),home/'Library/Application Support/Codex Monitor/ContextSettings/journal']
    if paths==[canonical(str(p)) for p in defaults] and home.stat().st_uid==os.getuid():
        return paths
    # Only explicitly supplied disposable fixtures, never arbitrary user paths.
    roots=[Path('/private/tmp'),Path('/private/var/folders')]
    if not any(all(p.is_relative_to(r) and p!=r for p in paths) for r in roots):
        raise Refused('unsupported_target')
    if [p.name for p in paths] != ['config.toml','models_cache.json','codex-package.json','journal'] or len({p.parent for p in paths})!=1:
        raise Refused('unsupported_target')
    if paths[0].parent.stat().st_uid!=os.getuid():
        raise Refused('unsupported_target')
    return paths

def desktop_closed():
    try:
        result=subprocess.run(['/usr/bin/pgrep','-x','Codex|ChatGPT|codex|codex-cli'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2,env={'PATH':'/usr/bin:/bin'})
        return result.returncode==1
    except (OSError,subprocess.TimeoutExpired):
        return False

def respond(config, catalog, client, journal, request):
    try:
        config,catalog,client,journal=validate_paths(config,catalog,client,journal)
        if type(request) is not dict:
            raise Refused('invalid_request')
        operation=request.get('operation')
        fields={'inspect':{'operation'},'preview':{'operation','model','action'},'undo_preview':{'operation'},
                'apply':{'operation','preview','confirmation','exclusive_edit'}}
        if operation not in fields or set(request)!=fields[operation]:
            raise Refused('invalid_request')
        if operation=='inspect':
            status=transaction.inspect(config,journal)
            models=[]; catalog_error=None
            try:
                rows=json_data(read_snapshot(catalog)['raw']).get('models')
                if not isinstance(rows,list) or not 0<len(rows)<=100:
                    raise Refused('unsupported_catalog')
                # Full validation and source fingerprinting before exposing choices.
                make_preview(config,catalog,client,rows[0].get('slug'),'set_maximum')
                models=[row['slug'] for row in rows]
            except Refused as error:
                catalog_error=str(error)
            return {'schema':1,'ok':True,'result':status,'models':models,'catalog_error':catalog_error,'desktop_closed':desktop_closed()}
        if operation=='preview':
            result=make_preview(config,catalog,client,request['model'],request['action'])
        elif operation=='undo_preview':
            result=transaction.preview_undo(config,journal)
        else:
            preview=request['preview']
            if type(preview) is not dict or preview.get('target')!=str(config):
                raise Refused('request_target_mismatch')
            expected={'config':str(config),'catalog':str(catalog),'client':str(client)}
            sources=preview.get('sources')
            if type(sources) is not dict or any(name not in expected or type(source) is not dict or source.get('path')!=expected[name] for name,source in sources.items()):
                raise Refused('request_target_mismatch')
            result=transaction.apply(preview,request['confirmation'],journal,lambda:{'desktop_closed':desktop_closed(),'exclusive_edit':request['exclusive_edit'] is True})
        return {'schema':1,'ok':True,'result':result,'desktop_closed':desktop_closed()}
    except Refused as error:
        return {'schema':1,'ok':False,'error':str(error)}
    except (OSError,ValueError,TypeError,KeyError,AttributeError,subprocess.SubprocessError):
        # Do not print raw TOML, source exceptions or private recovery bytes.
        return {'schema':1,'ok':False,'error':'operation_failed_check_current_file'}

def main():
    parser=argparse.ArgumentParser(add_help=False)
    for name in ('config','catalog','client','journal','request'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    try:
        if len(args.request.encode())>32768:
            raise Refused('request_too_large')
        request=json_data(args.request.encode())
        reply=respond(args.config,args.catalog,args.client,args.journal,request)
    except (Refused,ValueError):
        reply={'schema':1,'ok':False,'error':'invalid_request'}
    print(json.dumps(reply,sort_keys=True,separators=(',',':'),allow_nan=False))

if __name__=='__main__':
    main()
