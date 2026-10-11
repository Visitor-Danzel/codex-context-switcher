"""Breaks caught: stale persisted intent and automatic crash rollback."""
import importlib,json,os
from pathlib import Path
import subprocess,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Sources'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from context_settings_fixtures import fixtures,gate
from ContextSettings.preview import make_preview
try:module=importlib.import_module('ContextSettings.transaction')
except ModuleNotFoundError:module=None
SOURCE=str(Path(__file__).resolve().parents[1]/'Sources')
class RestartTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(module,'restart inspection is missing')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.config,self.catalog,self.client,self.journal=fixtures(self.tmp.name)
    def child(self,code):
        return subprocess.run([sys.executable,'-B','-c',code,SOURCE,str(self.config),str(self.catalog),str(self.client),str(self.journal)],capture_output=True,text=True,timeout=10)
    def test_new_process_reads_external_value_instead_of_saved_intent(self):
        p=make_preview(self.config,self.catalog,self.client,'fixture','set_maximum');module.apply(p,p['confirmation'],self.journal,gate)
        self.config.write_bytes(b'model_context_window=350000\n')
        r=self.child('import sys,json;sys.path.insert(0,sys.argv[1]);from ContextSettings.transaction import inspect;print(json.dumps(inspect(sys.argv[2],sys.argv[5])))')
        self.assertEqual(r.returncode,0,r.stderr);result=json.loads(r.stdout)
        self.assertEqual(result['window_tokens'],350000);self.assertEqual(result['state'],'external_change');self.assertFalse(result['session_verified'])
    def test_actual_process_exit_before_replace_leaves_uncertain_record_no_rollback(self):
        before=self.config.read_bytes()
        code='''import sys,os
sys.path.insert(0,sys.argv[1])
from ContextSettings.preview import make_preview
from ContextSettings.transaction import apply
original=os.replace
def crash(source,target,*args,**kwargs):
    if str(target)==sys.argv[2]:os._exit(72)
    return original(source,target,*args,**kwargs)
os.replace=crash
p=make_preview(sys.argv[2],sys.argv[3],sys.argv[4],'fixture','set_maximum')
apply(p,p['confirmation'],sys.argv[5],lambda:{'desktop_closed':True,'exclusive_edit':True})
'''
        r=self.child(code);self.assertEqual(r.returncode,72,r.stderr)
        self.assertEqual(module.inspect(self.config,self.journal)['state'],'uncertain')
        self.assertEqual(self.config.read_bytes(),before)

if __name__=='__main__':unittest.main()
