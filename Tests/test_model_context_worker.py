import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess
from unittest.mock import patch
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'Sources'))

def process_reply(code):
 # Fault injection is limited to process querying; real ACL/file checks run.
 real_run=subprocess.run
 def run(command,**kwargs):
  if command[0]=='/usr/bin/pgrep':return subprocess.CompletedProcess(command,code)
  return real_run(command,**kwargs)
 return run

class WorkerTests(unittest.TestCase):
 def setUp(self):
  self.assertTrue((PROJECT/'Sources/ModelContextSettings/worker.py').exists(),'Missing pinned per-model worker')
  self.worker=importlib.import_module('ModelContextSettings.worker')
  self.tmp=tempfile.TemporaryDirectory(prefix='legacy-context-repair-',dir='/private/tmp');self.root=Path(self.tmp.name)
 def tearDown(self):
  if hasattr(self,'tmp'):self.tmp.cleanup()
 def test_only_private_fixture_root_allowed(self):
  self.worker.validate_test_root(self.root)
  for path in ['/private/tmp',str(self.root/'missing')]:
   with self.assertRaises(self.worker.Refused):self.worker.validate_test_root(path)
  self.root.chmod(0o755)
  with self.assertRaises(self.worker.Refused):self.worker.validate_test_root(self.root)
 def test_linked_fixture_refused(self):
  link=self.root/'link';link.symlink_to(self.root)
  with self.assertRaises(self.worker.Refused):self.worker.validate_test_root(link)
 def test_request_fields_and_target_tampering_refused(self):
  paths=self.worker.paths_for(PROJECT/'Sources',test_root=self.root)
  for request in [{'operation':'inspect','unexpected':1},{'operation':'delete'},
                  {'operation':'apply','preview':{'target':'/unrelated'},'confirmation':'x','exclusive_edit':True}]:
   result=self.worker.respond(paths,request,isolated=True)
   self.assertFalse(result['ok'])
 def test_live_closed_check_never_assumes_success_on_unknown_process(self):
  # This execution occurs inside Codex; live saving must remain blocked.
  self.assertFalse(self.worker.desktop_closed())

 def test_process_probe_reports_closed_running_and_unavailable(self):
  probe=getattr(self.worker,'desktop_state',None)
  self.assertTrue(callable(probe),'Process query failures must be distinguished from a running Codex')
  for code,expected in [(0,'running'),(1,'closed'),(2,'unavailable'),(3,'unavailable')]:
   with self.subTest(code=code),patch.object(subprocess,'run',side_effect=process_reply(code)):
    self.assertEqual(probe(),expected)
    self.assertEqual(self.worker.desktop_closed(),expected=='closed')
  for failure in [OSError('synthetic query failure'),subprocess.TimeoutExpired('pgrep',2)]:
   with patch.object(subprocess,'run',side_effect=failure):
    self.assertEqual(probe(),'unavailable')
    self.assertFalse(self.worker.desktop_closed())

 def test_query_failure_blocks_withdrawal_with_its_own_error_and_no_writes(self):
  resources=PROJECT/'build/legacy-context-repair-candidate/Codex Context Switcher.app/Contents/Resources'
  paths=self.worker.paths_for(resources,test_root=self.root)
  original=b'model="gpt-6.1-sol"\n';paths.config.write_bytes(original)
  preview=self.worker.respond(paths,{'operation':'preview','action':'defaults','selected':[]},isolated=True)['result']
  request={'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':True}
  for code,error in [(0,'codex_running_or_unknown'),(3,'desktop_check_unavailable')]:
   with self.subTest(code=code),patch.object(subprocess,'run',side_effect=process_reply(code)):
    reply=self.worker.respond(paths,request)
    self.assertFalse(reply['ok']);self.assertEqual(reply['error'],error)
    self.assertEqual(paths.config.read_bytes(),original)
    self.assertFalse(paths.root.exists(),'A rejected process check must not prepare files or journals')

 def test_confirmed_closed_gate_allows_fixture_withdrawal_and_is_rechecked(self):
  resources=PROJECT/'build/legacy-context-repair-candidate/Codex Context Switcher.app/Contents/Resources'
  paths=self.worker.paths_for(resources,test_root=self.root)
  paths.config.write_text('model="gpt-6.1-sol"\n')
  preview=self.worker.respond(paths,{'operation':'preview','action':'save','selected':['gpt-6-astra']},isolated=True)['result']
  seeded=self.worker.respond(paths,{'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':True},isolated=True)
  self.assertTrue(seeded['ok'],seeded)
  preview=self.worker.respond(paths,{'operation':'preview','action':'defaults','selected':['gpt-6-astra']},isolated=True)['result']
  with patch.object(subprocess,'run',side_effect=process_reply(1)) as query:
   reply=self.worker.respond(paths,{'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':True})
   self.assertTrue(reply['ok'],reply)
   self.assertEqual(reply.get('desktop_check'),'closed')
   self.assertGreaterEqual(sum(c.args[0][0]=='/usr/bin/pgrep' for c in query.call_args_list),4,'Live process gate must be rechecked during the save')
  self.assertEqual(self.worker.settings.inspect(paths)['state'],'default')

if __name__=='__main__':unittest.main()
