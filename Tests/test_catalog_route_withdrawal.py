"""Accepted production catalog mode; all configuration files are disposable."""
import importlib
import json
import unittest
from unittest.mock import patch
import test_model_context_settings as fixtures


class CatalogRouteWithdrawalTests(unittest.TestCase):
    setUp=fixtures.CatalogSwitchTests.setUp
    tearDown=fixtures.CatalogSwitchTests.tearDown
    save=fixtures.CatalogSwitchTests.save

    def request(self,request):
        worker=importlib.import_module('ModelContextSettings.worker')
        # Only mock the external process-name query; real config/journal code runs.
        with patch.object(worker,'desktop_state',return_value='closed'):
            return worker.respond(self.paths,request,isolated=False)

    def preview(self,action,selected):
        reply=self.request({'operation':'preview','action':action,'selected':selected})
        self.assertTrue(reply['ok'],reply)
        return reply['result']

    def apply(self,preview):
        return self.request({'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':True})

    def test_production_preview_discloses_scope_without_writes(self):
        before=set(self.base.iterdir());preview=self.preview('save',['a'])
        self.assertEqual(preview['catalog_scope'],'bundled_cli_snapshot')
        self.assertEqual(preview['catalog_model_count'],len(self.rows['models']))
        self.assertEqual(self.config.read_bytes(),self.original);self.assertEqual(set(self.base.iterdir()),before)

    def test_production_apply_saves_independently_and_restart_reads_config(self):
        import copy,pathlib,tomllib
        self.assertTrue(self.apply(self.preview('save',['a']))['ok'])
        status=self.request({'operation':'inspect'})['result']
        self.assertFalse(status['catalog_route_paused']);self.assertEqual(status['selected'],['a'])
        self.assertEqual(status['catalog_scope'],'bundled_cli_snapshot')
        self.assertEqual(status['catalog_model_count'],len(self.rows['models']))
        path=pathlib.Path(tomllib.loads(self.config.read_text())['model_catalog_json'])
        expected=copy.deepcopy(self.rows);expected['models'][0]['context_window']=400
        self.assertEqual(json.loads(path.read_text()),expected)
        self.assertTrue(self.config.read_bytes().endswith(self.original))
        self.assertTrue(self.apply(self.preview('save',['b']))['ok'])
        self.assertEqual(self.request({'operation':'inspect'})['result']['selected'],['b'])

    def test_restoration_does_not_remove_closed_or_exclusive_guards(self):
        worker=importlib.import_module('ModelContextSettings.worker');preview=self.preview('save',['a'])
        for state,exclusive,error in [('running',True,'codex_running_or_unknown'),('unavailable',True,'desktop_check_unavailable'),('closed',False,'exclusive_edit_not_confirmed')]:
            with patch.object(worker,'desktop_state',return_value=state):
                reply=worker.respond(self.paths,{'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':exclusive})
            self.assertFalse(reply['ok']);self.assertEqual(reply['error'],error)
            self.assertEqual(self.config.read_bytes(),self.original);self.assertFalse(self.paths.root.exists())

    def test_explicit_defaults_removes_only_the_tools_override(self):
        self.save(['a']);reply=self.request({'operation':'preview','action':'defaults','selected':['a']})
        self.assertTrue(reply['ok']);preview=reply['result'];self.assertIsNone(preview['after'])
        reply=self.request({'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':True})
        self.assertTrue(reply['ok'],reply);self.assertEqual(self.config.read_bytes(),self.original)

    def test_production_undo_explicitly_reinstalls_previous_catalog(self):
        self.save(['a']);before=self.config.read_bytes()
        self.assertTrue(self.apply(self.preview('defaults',[]))['ok'])
        self.assertEqual(self.config.read_bytes(),self.original)
        preview=self.preview('undo',[])
        self.assertEqual(preview['catalog_scope'],'bundled_cli_snapshot')
        self.assertTrue(self.apply(preview)['ok']);self.assertEqual(self.config.read_bytes(),before)

    def test_external_change_still_blocks_save(self):
        preview=self.preview('save',['a']);raw=self.original+b'# keep external\n';self.config.write_bytes(raw)
        reply=self.apply(preview);self.assertFalse(reply['ok'])
        self.assertIn(reply['error'],['preview_changed','source_changed']);self.assertEqual(self.config.read_bytes(),raw)

    def test_undo_refuses_a_modified_or_missing_catalog_before_config_changes(self):
        import pathlib,tomllib
        self.save(['a']);path=pathlib.Path(tomllib.loads(self.config.read_text())['model_catalog_json'])
        self.save(['b']);before=self.config.read_bytes();path.chmod(0o600)
        raw=json.loads(path.read_text());raw['models'][0]['instructions']='changed externally';path.write_text(json.dumps(raw))
        reply=self.request({'operation':'preview','action':'undo','selected':[]})
        self.assertFalse(reply['ok']);self.assertEqual(self.config.read_bytes(),before)
        path.unlink();reply=self.request({'operation':'preview','action':'undo','selected':[]})
        self.assertFalse(reply['ok']);self.assertEqual(self.config.read_bytes(),before)

    def test_undo_catalog_edit_after_preview_does_not_publish(self):
        import pathlib,tomllib
        self.save(['a']);path=pathlib.Path(tomllib.loads(self.config.read_text())['model_catalog_json'])
        self.save(['b']);before=self.config.read_bytes();preview=self.preview('undo',[])
        path.chmod(0o600);path.write_text('{"models":[]}')
        reply=self.apply(preview);self.assertFalse(reply['ok'])
        self.assertEqual(self.config.read_bytes(),before)

    def test_record_recovery_does_not_rewrite_the_existing_configuration(self):
        self.save(['a']);active=self.paths.journal/'active.json';record=json.loads(active.read_text())
        record['phase']='prepared';active.write_text(json.dumps(record));before=self.config.read_bytes()
        reply=self.request({'operation':'preview','action':'recover','selected':[]});self.assertTrue(reply['ok'],reply)
        preview=reply['result'];reply=self.request({'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':True})
        self.assertTrue(reply['ok'],reply);self.assertEqual(self.config.read_bytes(),before)


if __name__=='__main__':unittest.main()
