"""Production policy must not introduce or reinstall a model-list override."""
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

    def test_production_preview_refuses_catalog_save_without_any_writes(self):
        before=set(self.base.iterdir());reply=self.request({'operation':'preview','action':'save','selected':['a']})
        self.assertFalse(reply['ok']);self.assertEqual(reply['error'],'catalog_route_paused')
        self.assertEqual(self.config.read_bytes(),self.original);self.assertEqual(set(self.base.iterdir()),before)

    def test_production_apply_refuses_previously_prepared_catalog_save(self):
        preview=self.module.make_preview(self.paths,'save',['a'])
        reply=self.request({'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':True})
        self.assertFalse(reply['ok']);self.assertEqual(reply['error'],'catalog_route_paused')
        self.assertEqual(self.config.read_bytes(),self.original);self.assertFalse(self.paths.root.exists())

    def test_inspection_marks_the_route_paused(self):
        self.save(['a']);before=self.config.read_bytes()
        reply=self.request({'operation':'inspect'})
        self.assertTrue(reply['ok']);self.assertTrue(reply['result']['catalog_route_paused'])
        self.assertEqual(reply['result']['selected'],['a']);self.assertEqual(self.config.read_bytes(),before)

    def test_explicit_defaults_removes_only_the_tools_override(self):
        self.save(['a']);reply=self.request({'operation':'preview','action':'defaults','selected':['a']})
        self.assertTrue(reply['ok']);preview=reply['result'];self.assertIsNone(preview['after'])
        reply=self.request({'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':True})
        self.assertTrue(reply['ok'],reply);self.assertEqual(self.config.read_bytes(),self.original)

    def test_production_undo_cannot_reinstall_the_catalog(self):
        self.save(['a']);preview=self.module.make_preview(self.paths,'defaults',[])
        self.module.apply(self.paths,preview,preview['confirmation'],self.gate)
        reply=self.request({'operation':'preview','action':'undo','selected':[]})
        self.assertFalse(reply['ok']);self.assertEqual(reply['error'],'catalog_route_paused')
        # A previously valid undo token cannot bypass the production restriction.
        preview=self.module.make_preview(self.paths,'undo',[])
        reply=self.request({'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':True})
        self.assertFalse(reply['ok']);self.assertEqual(reply['error'],'catalog_route_paused')
        self.assertEqual(self.config.read_bytes(),self.original)

    def test_record_recovery_does_not_rewrite_the_existing_configuration(self):
        self.save(['a']);active=self.paths.journal/'active.json';record=json.loads(active.read_text())
        record['phase']='prepared';active.write_text(json.dumps(record));before=self.config.read_bytes()
        reply=self.request({'operation':'preview','action':'recover','selected':[]});self.assertTrue(reply['ok'],reply)
        preview=reply['result'];reply=self.request({'operation':'apply','preview':preview,'confirmation':preview['confirmation'],'exclusive_edit':True})
        self.assertTrue(reply['ok'],reply);self.assertEqual(self.config.read_bytes(),before)


if __name__=='__main__':unittest.main()
