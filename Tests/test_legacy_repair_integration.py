"""Run the actual packaged candidate and official CLI using only test fixtures."""
import json
import pathlib
import subprocess
import tempfile
import unittest

PROJECT=pathlib.Path(__file__).resolve().parents[1]
APP=PROJECT/'build/legacy-context-repair-candidate/Codex Context Switcher.app'
BIN=APP/'Contents/MacOS/CodexContextSwitcher'
class CandidateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='legacy-context-repair-',dir='/private/tmp'); self.root=pathlib.Path(self.tmp.name)
  self.config=self.root/'config.toml'; self.config.write_text('model="gpt-6.1-sol"\nmodel_catalog_json='+json.dumps(str(self.root/'models-custom.json'))+'\n')
 def tearDown(self):self.tmp.cleanup()
 def run_tool(self,*args):
  if not BIN.exists(): return 127,{}
  p=subprocess.run([str(BIN),'--test-root',str(self.root),*args],capture_output=True,timeout=30)
  return p.returncode,json.loads(p.stdout) if p.returncode==0 else {'error':p.stderr.decode(errors='replace')}
 def states(self,result): return {m['slug']:m['saved_extended'] for m in result['models']}
 def test_full_current_model_set_and_no_startup_writes(self):
  before=set(self.root.iterdir());rc,r=self.run_tool('--status');self.assertEqual(rc,0,r)
  self.assertEqual(set(self.root.iterdir()),before)
  self.assertTrue({'gpt-6.1-sol','gpt-6-sol','gpt-6-luna'}.issubset(self.states(r)))
  source=json.loads((APP/'Contents/Resources/current-models.json').read_text());self.assertEqual([m['slug'] for m in r['models']],[m['slug'] for m in source['models']]);self.assertFalse(r['chat_verified']);self.assertFalse(r['real_settings_writable'])
 def test_independent_save_new_process_undo_defaults(self):
  rc,a=self.run_tool('--toggle','gpt-6-astra');self.assertEqual(rc,0,a)
  self.assertTrue(self.states(a)['gpt-6-astra']);self.assertFalse(self.states(a)['gpt-6.1-sol'])
  rc,b=self.run_tool('--toggle','gpt-6.1-sol');self.assertEqual(rc,0,b)
  self.assertTrue(self.states(b)['gpt-6-astra']);self.assertTrue(self.states(b)['gpt-6.1-sol'])
  rc,restarted=self.run_tool('--status');self.assertEqual(rc,0,restarted);self.assertEqual(self.states(b),self.states(restarted))
  rc,u=self.run_tool('--undo');self.assertEqual(rc,0,u);self.assertEqual(self.states(a),self.states(u))
  rc,default=self.run_tool('--restore-all');self.assertEqual(rc,0,default);self.assertFalse(any(self.states(default).values()))
  original=json.loads((APP/'Contents/Resources/current-models.json').read_text());actual=json.loads((self.root/'models-custom.json').read_text())
  self.assertEqual(original,actual)
  self.assertEqual(default['configuration']['activation'],'configured');self.assertFalse(default['configuration']['chat_verified'])
 def test_missing_model_fails_without_changing_saved_files(self):
  rc,r=self.run_tool('--toggle','gpt-6-astra');self.assertEqual(rc,0,r)
  before={p.name:p.read_bytes() for p in self.root.iterdir() if p.is_file()}
  rc,_=self.run_tool('--toggle','missing-model');self.assertNotEqual(rc,0)
  self.assertEqual({p.name:p.read_bytes() for p in self.root.iterdir() if p.is_file()},before)
 def test_real_write_and_frozen_legacy_commands_are_refused(self):
  self.assertTrue(BIN.exists())
  for args in [('--toggle','gpt-6-astra'),('--enable-all',),('--mode','daily','--apply'),('--health',)]:
   p=subprocess.run([str(BIN),*args],capture_output=True,timeout=10)
   self.assertEqual(p.returncode,2)
 def test_state_symlink_is_refused_without_changing_fixture(self):
  target=self.root/'fake-protected.txt';target.write_text('unchanged')
  (self.root/'state.json').symlink_to(target)
  rc,_=self.run_tool('--status');self.assertNotEqual(rc,0);self.assertEqual(target.read_text(),'unchanged')
 def test_source_update_closes_runtime_gate(self):
  self.assertTrue(BIN.exists(),'candidate package must exist')
  # Use a temporary copy, leaving the candidate unchanged.
  import shutil
  copy=self.root/'copy.app';shutil.copytree(APP,copy)
  asset=copy/'Contents/Resources/current-models.json';asset.write_text('{"models":[]}')
  p=subprocess.run([str(copy/'Contents/MacOS/CodexContextSwitcher'),'--test-root',str(self.root),'--status'],capture_output=True,timeout=15)
  self.assertNotEqual(p.returncode,0);self.assertFalse((self.root/'state.json').exists())
if __name__=='__main__':unittest.main()
