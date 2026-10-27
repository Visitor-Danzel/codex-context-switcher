"""Version upgrades must preserve choices without trusting a rehashed forgery."""
import copy
import hashlib
import json
import pathlib
import tomllib
import unittest
import test_model_context_settings as fixtures


def fingerprint(value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


class CatalogMigrationTests(unittest.TestCase):
    setUp=fixtures.CatalogSwitchTests.setUp
    tearDown=fixtures.CatalogSwitchTests.tearDown
    save=fixtures.CatalogSwitchTests.save

    def upgrade(self, trusted=True):
        old=copy.deepcopy(self.rows)
        baseline={'cli_version':'old','metadata_sha256':fingerprint({k:v for k,v in old.items() if k!='models'}),
                  'models':[{'slug':r['slug'],'default':r['context_window'],'maximum':r['max_context_window'],
                             'identity_sha256':fingerprint({k:v for k,v in r.items() if k!='context_window'})}
                            for r in old['models']]}
        self.old_path=pathlib.Path(tomllib.loads(self.config.read_text())['model_catalog_json'])
        self.old_bytes=self.old_path.read_bytes()
        self.rows['models'][0]['instructions']='new official instructions'
        self.rows['models'].append({'slug':'terra','context_window':500,'max_context_window':872,
                                   'visibility':'list','instructions':'new model'})
        self.official.write_text(json.dumps(self.rows))
        record=json.loads(self.record.read_text())
        record['catalog_sha256']=hashlib.sha256(self.official.read_bytes()).hexdigest()
        record['catalog_history']=[baseline] if trusted else []
        self.record.write_text(json.dumps(record))

    def rehash_old(self,change):
        data=json.loads(self.old_bytes);change(data)
        raw=json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        path=self.old_path.parent/(hashlib.sha256(raw).hexdigest()+'.json')
        path.write_bytes(raw);path.chmod(0o400)
        self.config.write_bytes(self.module.patch_catalog(self.config.read_bytes(),str(path)))

    def test_upgrade_inspection_preserves_selection_without_writes(self):
        self.save(['a']);self.upgrade();before=self.config.read_bytes()
        state=self.module.inspect(self.paths)
        self.assertEqual(state['state'],'catalog_outdated')
        self.assertEqual(state['selected'],['a'])
        self.assertEqual([r['slug'] for r in state['models']],['a','b','fixed','terra'])
        self.assertEqual(self.config.read_bytes(),before)
        self.assertEqual(self.old_path.read_bytes(),self.old_bytes)

    def test_upgrade_save_uses_full_new_catalog_and_undo_restores_old(self):
        self.save(['a']);self.upgrade();before=self.config.read_bytes()
        # Unrelated external edits are preserved by the new explicit save.
        self.config.write_bytes(before+b'# external, keep\n');before=self.config.read_bytes()
        self.save(['a']);state=self.module.inspect(self.paths)
        self.assertEqual(state['state'],'configured');self.assertEqual(state['selected'],['a'])
        current=pathlib.Path(tomllib.loads(self.config.read_text())['model_catalog_json'])
        expected=copy.deepcopy(self.rows);expected['models'][0]['context_window']=400
        self.assertEqual(json.loads(current.read_text()),expected)
        self.assertEqual(self.old_path.read_bytes(),self.old_bytes)
        self.assertTrue(self.config.read_bytes().endswith(b'# external, keep\n'))
        preview=self.module.make_preview(self.paths,'undo',[])
        self.module.apply(self.paths,preview,preview['confirmation'],self.gate)
        self.assertEqual(self.config.read_bytes(),before)
        self.assertEqual(self.module.inspect(self.paths)['selected'],['a'])

    def test_outdated_catalog_can_explicitly_restore_defaults_and_undo(self):
        self.save(['b']);self.upgrade();before=self.config.read_bytes()
        preview=self.module.make_preview(self.paths,'defaults',[])
        self.module.apply(self.paths,preview,preview['confirmation'],self.gate)
        self.assertEqual(self.config.read_bytes(),self.original)
        preview=self.module.make_preview(self.paths,'undo',[])
        self.module.apply(self.paths,preview,preview['confirmation'],self.gate)
        self.assertEqual(self.config.read_bytes(),before)
        self.assertEqual(self.module.inspect(self.paths)['selected'],['b'])

    def test_rehashed_instruction_forgery_is_not_a_version_upgrade(self):
        self.save(['a']);self.upgrade()
        self.rehash_old(lambda d:d['models'][0].update(instructions='untrusted instructions'))
        before=self.config.read_bytes()
        self.assertEqual(self.module.inspect(self.paths)['state'],'damaged_catalog')
        with self.assertRaisesRegex(self.module.Refused,'damaged_catalog'):self.save(['a'])
        self.assertEqual(self.config.read_bytes(),before)

    def test_rehashed_invalid_context_is_refused(self):
        self.save(['a']);self.upgrade()
        self.rehash_old(lambda d:d['models'][0].update(context_window=399))
        self.assertEqual(self.module.inspect(self.paths)['state'],'damaged_catalog')
        with self.assertRaisesRegex(self.module.Refused,'damaged_catalog'):self.save(['a'])

    def test_unknown_old_catalog_is_not_guessed(self):
        self.save(['a']);self.upgrade(trusted=False)
        self.assertEqual(self.module.inspect(self.paths)['state'],'damaged_catalog')
        with self.assertRaisesRegex(self.module.Refused,'damaged_catalog'):self.save(['a'])

    def test_catalog_edit_after_upgrade_preview_never_overwrites_config(self):
        self.save(['a']);self.upgrade();before=self.config.read_bytes()
        preview=self.module.make_preview(self.paths,'save',['a'])
        self.old_path.chmod(0o600);self.old_path.write_bytes(b'{"models":[]}')
        with self.assertRaises(self.module.Refused):
            self.module.apply(self.paths,preview,preview['confirmation'],self.gate)
        self.assertEqual(self.config.read_bytes(),before)

    def test_removed_selected_model_cannot_silently_disappear_on_save(self):
        self.save(['a']);self.upgrade()
        self.rows['models']=self.rows['models'][1:];self.official.write_text(json.dumps(self.rows))
        record=json.loads(self.record.read_text());record['catalog_sha256']=hashlib.sha256(self.official.read_bytes()).hexdigest();self.record.write_text(json.dumps(record))
        self.assertEqual(self.module.inspect(self.paths)['selected'],['a'])
        with self.assertRaisesRegex(self.module.Refused,'invalid_selection'):self.save(['a'])

    def test_gui_defaults_clears_a_removed_preserved_selection(self):
        self.save(['a']);self.upgrade();self.rows['models']=self.rows['models'][1:]
        self.official.write_text(json.dumps(self.rows));record=json.loads(self.record.read_text())
        record['catalog_sha256']=hashlib.sha256(self.official.read_bytes()).hexdigest();self.record.write_text(json.dumps(record))
        preview=self.module.make_preview(self.paths,'defaults',['a'])
        self.module.apply(self.paths,preview,preview['confirmation'],self.gate)
        self.assertEqual(self.config.read_bytes(),self.original)

    def test_gui_defaults_clears_a_now_fixed_preserved_selection(self):
        self.save(['a']);self.upgrade();self.rows['models'][0]['context_window']=400
        self.official.write_text(json.dumps(self.rows));record=json.loads(self.record.read_text())
        record['catalog_sha256']=hashlib.sha256(self.official.read_bytes()).hexdigest();self.record.write_text(json.dumps(record))
        preview=self.module.make_preview(self.paths,'defaults',['a'])
        self.module.apply(self.paths,preview,preview['confirmation'],self.gate)
        self.assertEqual(self.config.read_bytes(),self.original)

    def test_rehashed_metadata_order_or_duplicate_forgery_is_refused(self):
        self.save(['a']);self.upgrade()
        for change in [lambda d:d.update(extra='untrusted'),
                       lambda d:d['models'].reverse(),
                       lambda d:d['models'].__setitem__(1,copy.deepcopy(d['models'][0]))]:
            with self.subTest(change=change):
                self.rehash_old(change)
                self.assertEqual(self.module.inspect(self.paths)['state'],'damaged_catalog')
                with self.assertRaisesRegex(self.module.Refused,'damaged_catalog'):self.save(['a'])


if __name__=='__main__':unittest.main()
