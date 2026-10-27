"""Actual app -> actual restricted worker -> disposable config, no real writes."""
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

PROJECT=Path(__file__).resolve().parents[1]
APP=PROJECT/'build/legacy-context-repair-candidate/Codex Context Switcher.app'
BIN=APP/'Contents/MacOS/CodexContextSwitcher'

class PackagedSwitchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='legacy-context-repair-',dir='/private/tmp');self.root=Path(self.tmp.name)
  self.config=self.root/'config.toml';self.original=b'model="gpt-6.1-sol"\n# preserved\n[other]\nvalue="unchanged"\n';self.config.write_bytes(self.original)
 def tearDown(self):self.tmp.cleanup()
 def call(self,request,expect=True):
  process=subprocess.run([str(BIN),'--test-root',str(self.root),'--settings-request',json.dumps(request)],capture_output=True,timeout=35)
  self.assertTrue(process.stdout,process.stderr.decode(errors='replace'))
  reply=json.loads(process.stdout)
  self.assertEqual(reply['ok'],expect,reply)
  return reply
 def preview(self,action,selected):return self.call({'operation':'preview','action':action,'selected':selected})['result']
 def apply(self,preview,expect=True):return self.call({'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':True},expect)
 def test_save_restart_undo_default_from_actual_package(self):
  before=set(self.root.iterdir());status=self.call({'operation':'inspect'})['result'];self.assertEqual(set(self.root.iterdir()),before)
  source=json.loads((APP/'Contents/Resources/current-models.json').read_text())
  self.assertEqual([m['slug'] for m in status['models']],[m['slug'] for m in source['models']])
  self.apply(self.preview('save',['gpt-6-astra']))
  first=self.config.read_bytes();path=Path(tomllib.loads(first.decode())['model_catalog_json'])
  actual=json.loads(path.read_text());source=json.loads((APP/'Contents/Resources/current-models.json').read_text())
  expected=json.loads(json.dumps(source));next(m for m in expected['models'] if m['slug']=='gpt-6-astra')['context_window']=872000
  self.assertEqual(actual,expected)
  self.assertEqual(self.call({'operation':'inspect'})['result']['selected'],['gpt-6-astra'])
  self.apply(self.preview('save',['gpt-6.1-sol']))
  self.assertEqual(self.call({'operation':'inspect'})['result']['selected'],['gpt-6.1-sol'])
  self.apply(self.preview('undo',[]));self.assertEqual(self.config.read_bytes(),first)
  self.apply(self.preview('defaults',[]));self.assertEqual(self.config.read_bytes(),self.original)
  self.apply(self.preview('undo',[]));self.assertEqual(self.config.read_bytes(),first)
 def test_external_changes_preserved_in_packaged_pipeline(self):
  preview=self.preview('save',['gpt-6-astra']);external=self.original+b'# external\n';self.config.write_bytes(external)
  reply=self.apply(preview,False);self.assertIn(reply['error'],['preview_changed','source_changed']);self.assertEqual(self.config.read_bytes(),external)
 def test_confirm_and_target_tamper_refused(self):
  preview=self.preview('save',['gpt-6-astra']);preview['target']='/unrelated/config.toml'
  self.apply(preview,False);self.assertEqual(self.config.read_bytes(),self.original)
 def test_arbitrary_fixture_and_live_command_line_writes_refused(self):
  for args in [['--test-root','/private/tmp','--settings-request','{}'],['--settings-request','{"operation":"apply"}']]:
   p=subprocess.run([str(BIN),*args],capture_output=True,timeout=15);self.assertEqual(p.returncode,2)
 def test_package_excludes_frozen_controls(self):
  resources=APP/'Contents/Resources'
  self.assertFalse((resources/'PersonalControls').exists())
  self.assertFalse(list(resources.rglob('*personal_transaction*')))
 def test_worker_refuses_python_site_initialization(self):
  import sys
  p=subprocess.run([sys.executable,'-I','-B',str(APP/'Contents/Resources/ModelContextSettings/worker.py'),
                    '--test-root',str(self.root),'--request','{"operation":"inspect"}'],capture_output=True,text=True,timeout=20)
  reply=json.loads(p.stdout);self.assertFalse(reply['ok'],reply);self.assertEqual(reply['error'],'unisolated_worker')
 def test_normal_status_reads_configuration_instead_of_legacy_drafts(self):
  p=subprocess.run([str(BIN),'--status'],capture_output=True,text=True,timeout=20)
  reply=json.loads(p.stdout);self.assertTrue(reply.get('ok'),reply)
  self.assertIn(reply['result']['state'],['default','configured','legacy_configured','legacy_stale','other_catalog','damaged_catalog'])

if __name__=='__main__':unittest.main()
