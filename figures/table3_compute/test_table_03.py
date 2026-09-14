from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import table_03 as table


class Table3Tests(unittest.TestCase):
    def test_paper_values(self):
        self.assertEqual(table.table_rows(), [
            ('Karpenter', 'c5.xlarge', '$0.0662', 'Compilation', '9', '$0.0074'),
            ('Karpenter', 'c5.xlarge', '$0.0662', 'Video enc.', '31', '$0.0021'),
            ('KubePACS', 'c7i.xlarge', '$0.0733', 'Compilation', '13', '$0.0056'),
            ('KubePACS', 'c7i.xlarge', '$0.0733', 'Video enc.', '47', '$0.0016'),
            ('Best Case', '', '+10.73%', 'Video enc.', '+51.61%', '-23.8%'),
        ])

    def test_outputs_and_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'results'
            command = [sys.executable, str(table.HERE / 'table_03.py'), '--output', str(output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            for suffix in ('csv', 'md', 'tex'):
                self.assertTrue((output / f'table3.{suffix}').stat().st_size)
            latex = (output / 'table3.tex').read_text()
            self.assertIn(r'\$0.0662', latex)
            self.assertIn(r'-23.8\%', latex)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertNotEqual(subprocess.run(command[:-1] + [str(table.HERE / 'forbidden')],
                                               capture_output=True).returncode, 0)


if __name__ == '__main__':
    unittest.main()
