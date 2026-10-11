"""Exercise production policies and the real CLI with synthetic private data."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
PROJECT=Path(__file__).resolve().parents[1]
BASE=PROJECT/'build/legacy-context-repair-candidate'
RES=BASE/'Codex Context Switcher.app/Contents/Resources'
BIN=BASE/'Codex Context Switcher.app/Contents/MacOS/CodexContextSwitcher'
CLI='/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'

class RealPolicyTests(unittest.TestCase):
 def test_production_policy_can_distinguish_no_process_from_query_failure(self):
  # Removing the sysmond lookup rule must break the actual no-match query.
  with tempfile.TemporaryDirectory(prefix='legacy-context-repair-',dir='/private/tmp') as tmp:
   policy=subprocess.check_output([str(BASE/'verification/emit-maximum-policy'),str(RES),tmp],text=True)
   p=subprocess.run(['/usr/bin/sandbox-exec','-p',policy,'/usr/bin/pgrep','-x',
                     '^maximum_context_definitely_absent_83db9d$'],capture_output=True,text=True,timeout=4)
   self.assertEqual(p.returncode,1,'Expected a confirmed no-match, not a failed process-list query: '+p.stderr)

 def test_worker_scope_denies_protected_read_write_and_network(self):
  with tempfile.TemporaryDirectory(prefix='legacy-context-repair-',dir='/private/tmp') as tmp, tempfile.TemporaryDirectory(prefix='maximum-context-protected-',dir='/private/tmp') as protected:
   root=Path(tmp);config=root/'config.toml';config.write_text('model="gpt-6.1-sol"\n');secret=Path(protected)/'synthetic-history.json';secret.write_text('synthetic unchanged')
   keychain=Path(protected)/'synthetic-keychain.db';keychain.write_text('synthetic unchanged')
   policy=subprocess.check_output([str(BASE/'verification/emit-maximum-policy'),str(RES),tmp],text=True)
   code='''import json,socket,sys
result={}
result['config_read']=open(sys.argv[1]).read().startswith('model=')
for name,path in [('history_read',sys.argv[2]),('keychain_read',sys.argv[3])]:
 try:open(path).read();result[name]=False
 except PermissionError:result[name]=True
try:open(sys.argv[2],'w').write('bad');result['outside_write']=False
except PermissionError:result['outside_write']=True
try:
 s=socket.socket();s.settimeout(.2);s.connect(('127.0.0.1',9));result['network']=False
except PermissionError:result['network']=True
except OSError:result['network']=False
print(json.dumps(result))
'''
   p=subprocess.run(['/usr/bin/sandbox-exec','-p',policy,'/usr/local/bin/python3','-I','-S','-B','-c',code,str(config),str(secret),str(keychain)],capture_output=True,text=True,timeout=10)
   self.assertEqual(p.returncode,0,p.stderr);result=json.loads(p.stdout)
   self.assertEqual(result,{'config_read':True,'history_read':True,'keychain_read':True,'outside_write':True,'network':True})
   self.assertEqual(secret.read_text(),'synthetic unchanged');self.assertEqual(keychain.read_text(),'synthetic unchanged')

 def test_official_cli_loads_saved_per_model_catalog_and_defaults(self):
  with tempfile.TemporaryDirectory(prefix='legacy-context-repair-',dir='/private/tmp') as tmp:
   root=Path(tmp);config=root/'config.toml';config.write_text('model="gpt-6.1-sol"\n')
   def call(request):
    p=subprocess.run([str(BIN),'--test-root',tmp,'--settings-request',json.dumps(request)],capture_output=True,text=True,timeout=35)
    self.assertEqual(p.returncode,0,p.stdout);return json.loads(p.stdout)['result']
   policy=subprocess.check_output([str(BASE/'verification/emit-policy'),tmp],text=True)
   environment={'HOME':tmp,'CODEX_HOME':tmp,'TMPDIR':tmp,'PATH':'/usr/bin:/bin','LANG':'en_US.UTF-8'}
   def load():
    p=subprocess.run(['/usr/bin/sandbox-exec','-p',policy,CLI,'debug','models'],cwd=tmp,env=environment,capture_output=True,text=True,timeout=20)
    self.assertEqual(p.returncode,0,'guarded official CLI rejected fixture catalog')
    return json.loads(p.stdout)
   source=json.loads((RES/'current-models.json').read_text())
   for selected in [['gpt-6-astra'],['gpt-6.1-sol']]:
    preview=call({'operation':'preview','action':'save','selected':selected})
    call({'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':True})
    actual=load();self.assertEqual(len(actual['models']),len(source['models']))
    for a,b in zip(actual['models'],source['models']):
     self.assertEqual(a['slug'],b['slug']);self.assertEqual(a['context_window'],b['max_context_window'] if b['slug'] in selected else b['context_window'])
   preview=call({'operation':'preview','action':'defaults','selected':[]})
   call({'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':True})
   actual=load();self.assertEqual([(r['slug'],r['context_window']) for r in actual['models']],[(r['slug'],r['context_window']) for r in source['models']])

if __name__=='__main__':unittest.main()
