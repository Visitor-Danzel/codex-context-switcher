#!/bin/sh
# One fixed owned candidate. No install, launch, or legacy helper packaging.
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
candidate_root="$project_root/build/legacy-context-repair-candidate"
mkdir -p "$candidate_root/verification"
stage=$(mktemp -d "$candidate_root/stage.XXXXXX")
trap 'rm -rf "$stage"' EXIT HUP INT TERM
clang -fobjc-arc -Wall -Wextra -Werror -Wno-unused-function -Wno-deprecated-declarations -DCC_REPAIR_CANDIDATE -mmacosx-version-min=13.0 \
 -I "$project_root/Sources/CodexContextCore" -I "$project_root/Sources/LiveMonitorApp" \
 "$project_root/Sources/CodexContextSwitcherApp/main.m" "$project_root/Sources/CodexContextSwitcherApp/ContextRepairSession.m" "$project_root/Sources/CodexContextCore/CodexContextCore.m" \
 -framework Cocoa -framework Foundation -o "$stage/CodexContextSwitcher"
python3 - "$stage" <<'PY'
import hashlib,pathlib,sys
cli=pathlib.Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
(pathlib.Path(sys.argv[1])/'native-before.sha256').write_text(hashlib.sha256(cli.read_bytes()).hexdigest())
PY
"$stage/CodexContextSwitcher" --emit-catalog > "$stage/current-models.json"
"$stage/CodexContextSwitcher" --client-version > "$stage/client-version.txt"
python3 - "$project_root" "$stage" <<'PY'
import hashlib,json,pathlib,plistlib,shutil,sys
project,stage=map(pathlib.Path,sys.argv[1:])
cli=pathlib.Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
metadata=json.loads(pathlib.Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/codex-package.json').read_text())
version=(stage/'client-version.txt').read_text().strip()
if version!=metadata['version']:raise SystemExit('CLI package version mismatch')
native_hash=hashlib.sha256(cli.read_bytes()).hexdigest()
if native_hash!=(stage/'native-before.sha256').read_text():raise SystemExit('CLI changed during catalog probe; candidate preserved')
catalog=stage/'current-models.json';data=json.loads(catalog.read_text())
if len({m['slug'] for m in data['models']})!=len(data['models']):raise SystemExit('duplicate models')
record={'cli_version':version,'native_sha256':native_hash,'catalog_sha256':hashlib.sha256(catalog.read_bytes()).hexdigest(),'model_count':len(data['models']),'real_switch_completed':False}
history=json.loads((project/'Sources/ModelContextSettings/catalog_history.json').read_text())
if history.get('schema')!=1 or type(history.get('catalogs')) is not list:raise SystemExit('Invalid catalog history')
record['catalog_history']=history['catalogs']
app=stage/'Codex Context Switcher.app';mac=app/'Contents/MacOS';res=app/'Contents/Resources';mac.mkdir(parents=True);res.mkdir()
shutil.copy2(stage/'CodexContextSwitcher',mac/'CodexContextSwitcher');shutil.copy2(catalog,res/'current-models.json');shutil.copy2(project/'Sources/CodexContextSwitcherApp/legacy_context_readout.py',res/'legacy_context_readout.py')
for package,names in {'ContextSettings':['__init__.py','config_file.py','attributes.py','preview.py','transaction.py','worker.py'],
                      'ModelContextSettings':['__init__.py','settings.py','worker.py']}.items():
 (res/package).mkdir()
 for name in names:shutil.copy2(project/'Sources'/package/name,res/package/name)
(res/'catalog-record.json').write_text(json.dumps(record,indent=2)+'\n')
shutil.copy2(project/'AppIcon.icns',res/'AppIcon.icns')
shutil.copy2(project/'LICENSE',res/'LICENSE')
plist={'CFBundleExecutable':'CodexContextSwitcher','CFBundleIdentifier':'com.brucestudio.codex-context-switcher.repair-candidate','CFBundleName':'Codex Context Switcher','CFBundlePackageType':'APPL','CFBundleShortVersionString':'2.3.0','CFBundleVersion':'14','LSUIElement':False,'NSHighResolutionCapable':True,'LSMinimumSystemVersion':'13.0'}
plist['CFBundleIconFile']='AppIcon.icns'
(app/'Contents/Info.plist').write_bytes(plistlib.dumps(plist))
source_paths=[project/'Sources/CodexContextSwitcherApp'/name for name in ['main.m','RepairCandidate.h','MaximumContext.h','MaximumLanguage.h','ContextRepairSession.h','ContextRepairSession.m','legacy_context_readout.py']]
source_paths += [project/'Sources/ModelContextSettings/catalog_history.json']
source_paths += [project/'Sources/CodexContextCore'/name for name in ['CodexContextCore.h','CodexContextCore.m']]
source_paths += [p for package in ['ContextSettings','ModelContextSettings'] for p in sorted((project/'Sources'/package).glob('*.py'))]
record['source_sha256']={str(p.relative_to(project)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
record['real_save_available']=True
(stage/'candidate-owned.json').write_text(json.dumps(record,indent=2)+'\n')
PY
codesign --force --sign - "$stage/Codex Context Switcher.app"
codesign --verify --deep --strict "$stage/Codex Context Switcher.app"
python3 - "$candidate_root" "$stage" <<'PY'
import pathlib,json,shutil,sys
root,stage=map(pathlib.Path,sys.argv[1:]);app=root/'Codex Context Switcher.app'
if app.exists():
 if not (root/'candidate-owned.json').is_file():raise SystemExit('Refusing to replace an unowned candidate')
 shutil.rmtree(app)
shutil.move(str(stage/'Codex Context Switcher.app'),app);shutil.copy2(stage/'candidate-owned.json',root/'candidate-owned.json')
print(app)
PY
