"""Breaks caught: stale or mismatched declaration used as a maximum."""
import datetime
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Sources'))
try:module=importlib.import_module('ContextSettings.preview')
except ModuleNotFoundError:module=None

class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(module,'shared preview is missing')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.config=self.root/'config.toml';self.catalog=self.root/'models_cache.json';self.client=self.root/'codex-package.json'
        self.config.write_text('note="keep"\n');self.client.write_text(json.dumps({'version':'0.162.0-alpha.17.2'}))
        self.data={'client_version':'0.162.0','fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'models':[{'slug':'fixture','context_window':200000,'max_context_window':300000}]}
        self.write_catalog()
    def write_catalog(self):self.catalog.write_text(json.dumps(self.data))
    def preview(self,action='set_maximum'):return module.make_preview(self.config,self.catalog,self.client,'fixture',action)
    def test_preview_is_read_only_and_binds_sources(self):
        p=self.preview();self.assertEqual(self.config.read_bytes(),b'note="keep"\n');self.assertEqual(p['before'],None);self.assertEqual(p['after'],300000)
        self.assertFalse(p['session_verified']);self.assertEqual(p['scope'],'shared_user_file');self.assertEqual(set(p['sources']),{'config','catalog','client'});self.assertEqual(len(p['confirmation']),64)
    def test_remove_does_not_need_model_declaration(self):
        self.config.write_text('model_context_window=200000\n');self.catalog.unlink();self.client.unlink()
        p=self.preview('remove_override');self.assertEqual(p['after'],None);self.assertEqual(p['before'],200000)
    def test_stale_future_and_unknown_metadata_refused(self):
        for change in [{'fetched_at':'2020-01-01T00:00:00Z'},{'fetched_at':'2100-01-01T00:00:00Z'},{'fetched_at':'unknown'},{'client_version':'0.161.0'}]:
            self.data.update(change);self.write_catalog()
            with self.assertRaises(module.Refused):self.preview()
    def test_missing_duplicate_invalid_limits_refused(self):
        for models in [[],[self.data['models'][0]]*2,[{'slug':'fixture','context_window':200000,'max_context_window':True}],[{'slug':'fixture','context_window':400000,'max_context_window':300000}]]:
            self.data['models']=models;self.write_catalog()
            with self.assertRaises(module.Refused):self.preview()
    def test_custom_provider_catalog_and_legacy_profile_refused(self):
        for raw in ['model_catalog_json="fixture.json"\n','model_provider="fixture"\n','profile="fixture"\n']:
            self.config.write_text(raw)
            with self.assertRaises(module.Refused):self.preview()
    def test_catalog_change_changes_confirmation(self):
        first=self.preview();self.data['models'][0]['max_context_window']=350000;self.write_catalog()
        second=self.preview();self.assertNotEqual(first['confirmation'],second['confirmation']);self.assertEqual(second['after'],350000)

if __name__=='__main__':unittest.main()
