"""Breaks caught: unrelated-byte rewrite, root/table confusion, unsafe file reads."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Sources'))
try:
    module = importlib.import_module('ContextSettings.config_file')
except ModuleNotFoundError:
    module = None

class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(module, 'independent context config editor is missing')

    def test_replace_root_preserves_unrelated_bytes_and_comment(self):
        before=b'# own fixture\r\nmodel_context_window = 272_000 # explanation\r\nnote="keep"\r\n[other]\r\nmodel_context_window=100\r\n'
        self.assertEqual(module.patch_window(before,300000),b'# own fixture\r\nmodel_context_window = 300000 # explanation\r\nnote="keep"\r\n[other]\r\nmodel_context_window=100\r\n')

    def test_insert_is_root_even_when_file_starts_with_table(self):
        self.assertEqual(module.patch_window(b'[other]\nmodel_context_window=100\n',300000),b'model_context_window = 300000\n[other]\nmodel_context_window=100\n')

    def test_remove_retains_inline_comment_and_table_value(self):
        self.assertEqual(module.patch_window(b'model_context_window = 200 # retain\n[other]\nmodel_context_window=100\n',None),b'# retain\n[other]\nmodel_context_window=100\n')

    def test_multiline_lookalike_is_not_edited(self):
        raw=b'note="""\nmodel_context_window = 123\n"""\nmodel_context_window = 200\n'
        self.assertEqual(module.patch_window(raw,300000),b'note="""\nmodel_context_window = 123\n"""\nmodel_context_window = 300000\n')

    def test_missing_remove_is_noop(self):
        self.assertEqual(module.patch_window(b'# fixture\n',None),b'# fixture\n')

    def test_bad_or_ambiguous_inputs_refused(self):
        for raw in [b'model_context_window=true\n',b'model_context_window=200\nmodel_context_window=100\n',b'"model_context_window"=200\n',b'model_context_window=0x100\n',b'bad syntax']:
            with self.subTest(raw=raw),self.assertRaises(module.Refused):module.patch_window(raw,300000)

    def test_invalid_values_refused(self):
        for value in [True,0,-1,1.5,9007199254740992,'300000']:
            with self.subTest(value=value),self.assertRaises(module.Refused):module.patch_window(b'',value)

    def test_snapshot_rejects_symlink_hardlink_and_fifo(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp).resolve();p=base/'config.toml';p.write_bytes(b'note="keep"\n')
            link=base/'link';link.symlink_to(p)
            with self.assertRaises(module.Refused):module.read_snapshot(link)
            os.link(p,base/'hard')
            with self.assertRaises(module.Refused):module.read_snapshot(p)
            pipe=base/'fifo';os.mkfifo(pipe)
            with self.assertRaises(module.Refused):module.read_snapshot(pipe)

    def test_snapshot_has_content_identity_and_bounded_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve()/'config.toml';p.write_bytes(b'note="keep"\n')
            snap=module.read_snapshot(p)
            self.assertEqual(snap['raw'],b'note="keep"\n');self.assertEqual(len(snap['sha256']),64)
            with self.assertRaises(module.Refused):module.read_snapshot(p,max_bytes=2)

    @unittest.skipUnless(sys.platform=='darwin','macOS extended attributes')
    def test_mac_attributes_are_refused_without_os_listxattr(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve()/'config.toml';p.write_bytes(b'note="keep"\n')
            self.assertEqual(module.read_snapshot(p,attributes=True)['raw'],b'note="keep"\n')
            subprocess.run(['/usr/bin/xattr','-w','test.fixture','value',str(p)],check=True)
            with self.assertRaises(module.Refused):module.read_snapshot(p,attributes=True)

if __name__=='__main__':unittest.main()
