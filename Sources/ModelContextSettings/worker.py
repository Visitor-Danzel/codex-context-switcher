"""One pinned request, executed under the GUI's deny-default file sandbox."""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from ModelContextSettings import settings
from ContextSettings.config_file import Refused, canonical
from ContextSettings.preview import json_data

CLIENT=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/codex-package.json')
NATIVE=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')

def desktop_state():
    """Query names only; no-match is different from a failed system query."""
    try:
        result=subprocess.run(['/usr/bin/pgrep','-x','Codex|ChatGPT|codex|codex-cli'],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            timeout=2,env={'PATH':'/usr/bin:/bin'})
        return {0:'running',1:'closed'}.get(result.returncode,'unavailable')
    except (OSError,subprocess.TimeoutExpired):
        return 'unavailable'

def desktop_closed():
    return desktop_state()=='closed'

def validate_test_root(path):
    path=Path(path)
    if not str(path).startswith('/private/tmp/legacy-context-repair-') or Path(os.path.realpath(path))!=path:
        raise Refused('unsupported_target')
    try:info=os.lstat(path)
    except OSError:raise Refused('unsupported_target') from None
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise Refused('unsupported_target')
    return path

def paths_for(resources,home=None,test_root=None):
    resources=Path(resources)
    if test_root is not None:
        base=validate_test_root(test_root)
        config=base/'config.toml'; root=base/'settings';legacy=base/'models-custom.json'
    else:
        base=Path(home or '')
        if not base.is_absolute() or base.parent!=Path('/Users') or Path(os.path.realpath(base))!=base:
            raise Refused('unsupported_target')
        info=os.lstat(base)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid():raise Refused('unsupported_target')
        config=base/'.codex/config.toml';root=base/'Library/Application Support/CodexContextSwitcher';legacy=base/'.codex/context-switcher/models-custom.json'
        if Path(os.path.realpath(config.parent))!=config.parent:raise Refused('unsupported_target')
        if Path(os.path.realpath(root.parent))!=root.parent:raise Refused('unsupported_target')
    for path in [root,root/'catalogs',root/'journal']:
        if path.exists() or path.is_symlink():
            info=os.lstat(path)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
                raise Refused('unsafe_journal')
    return settings.Paths(config,resources/'current-models.json',resources/'catalog-record.json',CLIENT,NATIVE,root,legacy)

def respond(paths,request,isolated=False):
    try:
        if type(request) is not dict:raise Refused('invalid_request')
        fields={'inspect':{'operation'},'preview':{'operation','action','selected'},
                'apply':{'operation','preview','confirmation','exclusive_edit'}}
        op=request.get('operation')
        if op not in fields or set(request)!=fields[op]:raise Refused('invalid_request')
        # A catalog override owns the native model list, exceeding this tool's scope.
        # Retain fixture-only historical verification and explicit removal/recovery.
        if not isolated and op=='preview' and request.get('action')=='save':
            raise Refused('catalog_route_paused')
        # Disposable configuration is not used by any native desktop process.
        check='isolated' if isolated else desktop_state()
        closed=isolated or check=='closed'
        def gate():
            current='closed' if isolated else desktop_state()
            if current=='unavailable':raise Refused('desktop_check_unavailable')
            return {'desktop_closed':current=='closed',
                    'exclusive_edit':request['exclusive_edit'] is True}
        if op=='inspect':result=settings.inspect(paths)
        elif op=='preview':
            result=settings.make_preview(paths,request['action'],request['selected'])
            if not isolated and result.get('action')!='recover' and result.get('after') is not None:
                raise Refused('catalog_route_paused')
        else:
            preview=request['preview']
            if type(preview) is not dict or preview.get('target')!=str(paths.config):raise Refused('request_target_mismatch')
            if not isolated and (preview.get('action')=='save' or
                    (preview.get('action')!='recover' and preview.get('after') is not None)):
                raise Refused('catalog_route_paused')
            expected={'config':paths.config,'official':paths.official,'record':paths.record,'client':paths.client}
            sources=preview.get('sources')
            if type(sources) is not dict:raise Refused('request_target_mismatch')
            for name,source in sources.items():
                path=source.get('path') if type(source) is dict else None
                if name=='current_catalog':
                    if type(path) is not str or not (path==str(paths.legacy) or settings._owned_catalog(paths,path)):raise Refused('request_target_mismatch')
                elif name=='backup':
                    if preview.get('action')!='recover' or type(path) is not str or Path(path).parent!=paths.journal or Path(path).name!=str(preview.get('record_id'))+'.before':raise Refused('request_target_mismatch')
                elif name not in expected or path!=str(expected[name]):raise Refused('request_target_mismatch')
            if set(sources)==set() or 'config' not in sources:raise Refused('request_target_mismatch')
            result=settings.apply(paths,preview,request['confirmation'],gate)
        if op!='preview':result['catalog_route_paused']=not isolated
        return {'schema':1,'ok':True,'result':result,'desktop_closed':closed,
                'desktop_check':check,'isolated_test':isolated}
    except Refused as error:return {'schema':1,'ok':False,'error':str(error)}
    except (OSError,ValueError,TypeError,KeyError,AttributeError):return {'schema':1,'ok':False,'error':'operation_failed_check_current_file'}

def main():
    if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        print(json.dumps({'schema':1,'ok':False,'error':'unisolated_worker'}));return
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--home');parser.add_argument('--test-root');parser.add_argument('--request',required=True)
    args=parser.parse_args()
    try:
        if bool(args.home)==bool(args.test_root) or len(args.request.encode())>32768:raise Refused('invalid_request')
        paths=paths_for(Path(__file__).resolve().parent.parent,home=args.home,test_root=args.test_root)
        reply=respond(paths,json_data(args.request.encode()),isolated=args.test_root is not None)
    except (Refused,OSError,ValueError):reply={'schema':1,'ok':False,'error':'invalid_target_or_request'}
    print(json.dumps(reply,sort_keys=True,separators=(',',':'),allow_nan=False))

if __name__=='__main__':main()
