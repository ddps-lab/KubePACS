import gzip
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'kubepacs_cli', Path(__file__).with_name('kubepacs_cli.py'))
cli = importlib.util.module_from_spec(spec)
stdout = sys.stdout
try:
    spec.loader.exec_module(cli)
finally:
    sys.stdout = stdout


class SnapshotTests(unittest.TestCase):
    def test_local_inputs_never_fetch_live_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'snapshot.json'
            compressed = path.with_suffix('.json.gz')
            records = [{'Region': 'ap-northeast-2'}]
            path.write_text(json.dumps(records))
            with gzip.open(compressed, 'wt') as stream:
                json.dump(records, stream)
            with patch.object(cli.requests, 'get', side_effect=AssertionError('network')):
                self.assertEqual(cli.load_spot_data(str(path)), records)
                self.assertEqual(cli.load_spot_data(str(compressed)), records)
                with patch.dict(os.environ, {'KUBEPACS_SPOT_DATA_PATH': str(path)}):
                    self.assertEqual(cli.load_spot_data(), records)
                    with self.assertRaises(FileNotFoundError):
                        cli.load_spot_data(str(path.parent / 'missing.json'))
                path.write_text('{}')
                with self.assertRaises(ValueError):
                    cli.load_spot_data(str(path))

    def test_live_input_has_timeout(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(cli.requests, 'get') as get:
                get.return_value.json.return_value = []
                self.assertEqual(cli.load_spot_data(), [])
                self.assertEqual(get.call_args.kwargs['timeout'], 30)
                get.return_value.raise_for_status.assert_called_once()


if __name__ == '__main__':
    unittest.main()
