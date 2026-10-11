"""Breaks caught: overwrite after drift, unowned undo, success before durable proof."""
import importlib,json,os
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Sources'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from context_settings_fixtures import fixtures,gate
from ContextSettings.preview import make_preview,Refused
try:module=importlib.import_module('ContextSettings.transaction')
except ModuleNotFoundError:module=None

class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(module,'shared transaction is missing')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.config,self.catalog,self.client,self.journal=fixtures(self.tmp.name)
        self.before=self.config.read_bytes()
    def preview(self,action='set_maximum'):return make_preview(self.config,self.catalog,self.client,'fixture',action)
    def save(self,p=None,g=gate):
        p=p or self.preview();return module.apply(p,p['confirmation'],self.journal,g)
    def test_save_readback_and_undo_restore_exact_bytes(self):
        self.assertEqual(self.save()['state'],'saved')
        self.assertEqual(self.config.read_bytes(),b'# fixture\nmodel_context_window = 300000 # retain\nnote="keep"\n')
        p=module.preview_undo(self.config,self.journal)
        self.assertEqual(module.apply(p,p['confirmation'],self.journal,gate)['state'],'undone')
        self.assertEqual(self.config.read_bytes(),self.before)
    def test_changed_config_refuses_save_and_preserves_external_bytes(self):
        p=self.preview();self.config.write_bytes(self.before+b'other="external"\n')
        with self.assertRaises(Refused):self.save(p)
        self.assertTrue(self.config.read_bytes().endswith(b'other="external"\n'))
    def test_changed_declaration_refuses_old_confirmation(self):
        p=self.preview();data=json.loads(self.catalog.read_text());data['models'][0]['max_context_window']=350000;self.catalog.write_text(json.dumps(data))
        with self.assertRaises(Refused):self.save(p)
        self.assertEqual(self.config.read_bytes(),self.before)
    def test_running_desktop_or_missing_exclusive_confirmation_refuses(self):
        for g in [lambda:{'desktop_closed':False,'exclusive_edit':True},lambda:{'desktop_closed':True,'exclusive_edit':False}]:
            with self.assertRaises(Refused):self.save(g=g)
        self.assertEqual(self.config.read_bytes(),self.before)
    def test_invalid_confirmation_and_expired_preview_refuse(self):
        p=self.preview()
        with self.assertRaises(Refused):module.apply(p,'0'*64,self.journal,gate)
        p['expires_at']=0
        with self.assertRaises(Refused):self.save(p)
    def test_external_edit_blocks_undo(self):
        self.save();self.config.write_bytes(self.config.read_bytes()+b'other="external"\n')
        with self.assertRaises(Refused):module.preview_undo(self.config,self.journal)
        self.assertEqual(module.inspect(self.config,self.journal)['state'],'external_change')
    def test_private_recovery_and_double_submit(self):
        p=self.preview();self.save(p)
        with self.assertRaises(Refused):self.save(p)
        self.assertEqual(self.journal.stat().st_mode&0o777,0o700)
        for f in self.journal.iterdir():self.assertEqual(f.stat().st_mode&0o777,0o600)
    def test_remove_and_undo_preserve_other_fields(self):
        self.save(self.preview('remove_override'))
        self.assertEqual(self.config.read_bytes(),b'# fixture\n# retain\nnote="keep"\n')
        p=module.preview_undo(self.config,self.journal);module.apply(p,p['confirmation'],self.journal,gate)
        self.assertEqual(self.config.read_bytes(),self.before)
    def test_forged_candidate_cannot_edit_another_key(self):
        p=self.preview();p['after']=400000
        with self.assertRaises(Refused):self.save(p)
        self.assertEqual(self.config.read_bytes(),self.before)
    def test_file_mode_and_native_attributes_survive_save(self):
        if sys.platform!='darwin':self.skipTest('macOS attributes')
        import subprocess
        subprocess.run(['/usr/bin/xattr','-c',str(self.config)],check=True)
        self.config.chmod(0o640)
        expected=module.read_snapshot(self.config,attributes=True)['attributes']
        self.assertEqual(self.save()['state'],'saved')
        self.assertEqual(self.config.stat().st_mode&0o777,0o640)
        self.assertEqual(module.read_snapshot(self.config,attributes=True)['attributes'],expected)
    def test_private_journal_acl_cannot_grant_other_users_access(self):
        if sys.platform!='darwin':self.skipTest('macOS ACL')
        import subprocess
        self.journal.mkdir(mode=0o700)
        subprocess.run(['/bin/chmod','+a','everyone allow list,search',str(self.journal)],check=True)
        with self.assertRaises(Refused):self.save()
        self.assertEqual(self.config.read_bytes(),self.before)
    def test_inspect_rejects_invalid_existing_window(self):
        self.config.write_bytes(b'model_context_window=true\n')
        with self.assertRaises(Refused):module.inspect(self.config,self.journal)

if __name__=='__main__':unittest.main()
