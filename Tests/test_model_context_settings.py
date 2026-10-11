"""Real catalog/config transactions, using only private disposable fixtures."""
import copy
import hashlib
import importlib
import json
import pathlib
import sys
import tempfile
import tomllib
import unittest

PROJECT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'Sources'))


class CatalogSwitchTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((PROJECT / 'Sources/ModelContextSettings/settings.py').exists(),
                        'Missing actual per-model configuration saving module')
        self.module = importlib.import_module('ModelContextSettings.settings')
        self.tmp = tempfile.TemporaryDirectory(prefix='legacy-context-repair-', dir='/private/tmp')
        self.base = pathlib.Path(self.tmp.name)
        self.config = self.base / 'config.toml'
        self.original = b'# preserved\nmodel = "a"\n[other]\nvalue = "unchanged"\n'
        self.config.write_bytes(self.original)
        self.official = self.base / 'current-models.json'
        self.rows = {'models': [
            {'slug': 'a', 'context_window': 100, 'max_context_window': 400,
             'visibility': 'list', 'instructions': 'unchanged A'},
            {'slug': 'b', 'context_window': 200, 'max_context_window': 500,
             'visibility': 'list', 'instructions': 'unchanged B'},
            {'slug': 'fixed', 'context_window': 200, 'max_context_window': 200,
             'visibility': 'hide', 'instructions': 'unchanged hidden'}]}
        self.official.write_text(json.dumps(self.rows))
        self.native = self.base / 'codex'; self.native.write_bytes(b'fixture native identity')
        self.client = self.base / 'codex-package.json'; self.client.write_text('{"version":"0.162.0-alpha.17.2"}')
        self.record = self.base / 'catalog-record.json'
        self.record.write_text(json.dumps({'cli_version':'0.162.0-alpha.17.2',
            'catalog_sha256':hashlib.sha256(self.official.read_bytes()).hexdigest(),
            'native_sha256':hashlib.sha256(self.native.read_bytes()).hexdigest()}))
        self.paths = self.module.Paths(self.config, self.official, self.record, self.client,
            self.native, self.base / 'settings', self.base / 'models-custom.json')
        self.gate = lambda: {'desktop_closed':True,'exclusive_edit':True}

    def tearDown(self):
        if hasattr(self, 'tmp'): self.tmp.cleanup()

    def save(self, selection):
        preview = self.module.make_preview(self.paths, 'save', selection)
        return self.module.apply(self.paths, preview, preview['confirmation'], self.gate)

    def test_independent_models_real_config_and_restart(self):
        before = set(self.base.iterdir())
        self.assertEqual(self.module.inspect(self.paths)['state'], 'default')
        self.assertEqual(before, set(self.base.iterdir()), 'inspect must never create files')
        self.save(['a'])
        path = pathlib.Path(tomllib.loads(self.config.read_text())['model_catalog_json'])
        actual = json.loads(path.read_text())
        expected = copy.deepcopy(self.rows); expected['models'][0]['context_window'] = 400
        self.assertEqual(actual, expected)
        self.assertTrue(self.config.read_bytes().endswith(self.original))
        # A new worker/session reads configuration, rather than a stale in-memory selection.
        self.assertEqual(self.module.inspect(self.paths)['selected'], ['a'])
        self.save(['b'])
        self.assertEqual(self.module.inspect(self.paths)['selected'], ['b'])
        self.assertEqual(json.loads(path.read_text()), expected, 'previous immutable catalog retained')

    def test_undo_restores_exact_previous_config(self):
        self.save(['a']); before = self.config.read_bytes(); self.save(['a','b'])
        preview = self.module.make_preview(self.paths, 'undo', [])
        self.module.apply(self.paths, preview, preview['confirmation'], self.gate)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(self.module.inspect(self.paths)['selected'], ['a'])

    def test_default_removes_catalog_and_can_be_undone(self):
        self.save(['a']); before = self.config.read_bytes()
        preview = self.module.make_preview(self.paths, 'defaults', [])
        self.module.apply(self.paths, preview, preview['confirmation'], self.gate)
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(self.module.inspect(self.paths)['state'], 'default')
        preview = self.module.make_preview(self.paths, 'undo', [])
        self.module.apply(self.paths, preview, preview['confirmation'], self.gate)
        self.assertEqual(self.config.read_bytes(), before)

    def test_external_change_between_preview_and_apply_is_preserved(self):
        preview = self.module.make_preview(self.paths, 'save', ['a'])
        external = self.original + b'# external edit\n'; self.config.write_bytes(external)
        with self.assertRaisesRegex(self.module.Refused, 'preview_changed|source_changed'):
            self.module.apply(self.paths, preview, preview['confirmation'], self.gate)
        self.assertEqual(self.config.read_bytes(), external)

    def test_external_change_after_save_blocks_undo(self):
        self.save(['a']); self.config.write_bytes(self.config.read_bytes()+b'# external\n')
        with self.assertRaisesRegex(self.module.Refused, 'external_change'):
            self.module.make_preview(self.paths, 'undo', [])
        self.assertFalse(self.module.inspect(self.paths)['undo_available'])

    def test_unknown_model_and_unextendable_model_refused(self):
        for selection in [['missing'],['fixed'],['a','a']]:
            with self.assertRaises(self.module.Refused): self.save(selection)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_overrides_and_profiles_are_not_silently_deleted(self):
        for raw in [b'model_context_window=123\n', b'model_auto_compact_token_limit=99\n',
                    b'profile="work"\n', b'[profiles.work]\nmodel="a"\n', b'model_provider="other"\n']:
            self.config.write_bytes(raw)
            with self.assertRaises(self.module.Refused): self.save(['a'])
            self.assertEqual(self.config.read_bytes(),raw)

    def test_arbitrary_catalog_not_read_or_overwritten(self):
        self.config.write_text('model_catalog_json="/unrelated/private/catalog.json"\n')
        self.assertEqual(self.module.inspect(self.paths)['state'], 'other_catalog')
        with self.assertRaises(self.module.Refused): self.save(['a'])

    def test_runtime_update_blocks_save_but_keeps_undo(self):
        self.save(['a']); self.native.write_bytes(b'new version')
        self.assertFalse(self.module.inspect(self.paths)['runtime_compatible'])
        with self.assertRaisesRegex(self.module.Refused,'runtime_changed'): self.save(['b'])
        preview = self.module.make_preview(self.paths,'undo',[])
        self.module.apply(self.paths,preview,preview['confirmation'],self.gate)
        self.assertEqual(self.config.read_bytes(),self.original)

    def test_catalog_tamper_and_config_symlink_refused(self):
        self.save(['a']); path=pathlib.Path(tomllib.loads(self.config.read_text())['model_catalog_json'])
        path.chmod(0o600); path.write_text('{"models":[]}')
        self.assertEqual(self.module.inspect(self.paths)['state'],'damaged_catalog')
        with self.assertRaises(self.module.Refused): self.save(['b'])
        self.config.unlink(); self.config.symlink_to(self.official)
        with self.assertRaises(self.module.Refused): self.module.inspect(self.paths)

    def test_legacy_settings_not_rewritten(self):
        self.paths.legacy.write_text(json.dumps(self.rows)); original=self.paths.legacy.read_bytes()
        self.config.write_text('model_catalog_json='+json.dumps(str(self.paths.legacy))+'\n')
        self.save(['a'])
        self.assertEqual(self.paths.legacy.read_bytes(),original)
        self.assertEqual(self.module.inspect(self.paths)['selected'],['a'])

    def test_expired_confirmation_and_open_desktop_refused(self):
        preview=self.module.make_preview(self.paths,'save',['a'])
        for gate in [lambda:{'desktop_closed':False,'exclusive_edit':True},
                     lambda:{'desktop_closed':True,'exclusive_edit':False}]:
            with self.assertRaises(self.module.Refused):
                self.module.apply(self.paths,preview,preview['confirmation'],gate)
        with self.assertRaises(self.module.Refused): self.module.apply(self.paths,preview,'wrong',self.gate)
        self.assertEqual(self.config.read_bytes(),self.original)

    def test_uncertain_transaction_never_auto_rolls_back(self):
        self.save(['a']); active=self.paths.root/'journal/active.json'
        record=json.loads(active.read_text()); record['phase']='prepared'; active.write_text(json.dumps(record))
        before=self.config.read_bytes(); status=self.module.inspect(self.paths)
        self.assertEqual(status['transaction_state'],'uncertain'); self.assertFalse(status['undo_available'])
        with self.assertRaisesRegex(self.module.Refused,'uncertain_previous_transaction'):self.save(['b'])
        self.assertEqual(self.config.read_bytes(),before)

    def test_quoted_key_crlf_and_comments_preserved(self):
        raw=b'"model_catalog_json" = "/unrelated" # kept\r\n[other]\r\nmodel_catalog_json="nested"\r\n'
        candidate=self.module.patch_catalog(raw,'/new/path')
        self.assertEqual(tomllib.loads(candidate.decode())['other'],{'model_catalog_json':'nested'})
        self.assertIn(b'# kept\r\n',candidate)
        self.assertEqual(self.module.patch_catalog(candidate,None),b'# kept\r\n[other]\r\nmodel_catalog_json="nested"\r\n')

    def test_interrupted_saved_transaction_can_be_checked_without_rewriting_config(self):
        preview=self.module.make_preview(self.paths,'save',['a']);count=0
        def interrupted_gate():
            nonlocal count
            count+=1
            return {'desktop_closed':count<3,'exclusive_edit':True}
        with self.assertRaisesRegex(self.module.Refused,'codex_running_or_unknown'):
            self.module.apply(self.paths,preview,preview['confirmation'],interrupted_gate)
        before=self.config.read_bytes();self.assertEqual(self.module.inspect(self.paths)['transaction_state'],'uncertain')
        recovery=self.module.make_preview(self.paths,'recover',[])
        self.module.apply(self.paths,recovery,recovery['confirmation'],self.gate)
        self.assertEqual(self.config.read_bytes(),before)
        self.assertTrue(self.module.inspect(self.paths)['undo_available'])
        undo=self.module.make_preview(self.paths,'undo',[])
        self.module.apply(self.paths,undo,undo['confirmation'],self.gate)
        self.assertEqual(self.config.read_bytes(),self.original)

    def test_interrupted_unpublished_transaction_can_be_checked_without_overwriting(self):
        self.save(['a']);active=self.paths.root/'journal/active.json';record=json.loads(active.read_text())
        record['phase']='prepared';active.write_text(json.dumps(record));self.config.write_bytes(self.original)
        recovery=self.module.make_preview(self.paths,'recover',[])
        self.module.apply(self.paths,recovery,recovery['confirmation'],self.gate)
        self.assertEqual(self.config.read_bytes(),self.original)
        self.assertEqual(self.module.inspect(self.paths)['transaction_state'],'undone')

    def test_recovery_preserves_unrelated_external_change(self):
        self.save(['a']);active=self.paths.root/'journal/active.json';record=json.loads(active.read_text())
        record['phase']='prepared';active.write_text(json.dumps(record));self.config.write_bytes(b'model="external"\n')
        with self.assertRaisesRegex(self.module.Refused,'external_change'):
            self.module.make_preview(self.paths,'recover',[])
        self.assertEqual(self.config.read_bytes(),b'model="external"\n')


if __name__ == '__main__': unittest.main()
