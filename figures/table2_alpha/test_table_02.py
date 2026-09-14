from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import table_02 as table


class Table2Tests(unittest.TestCase):
    def test_efficiency(self):
        self.assertEqual(table.efficiency(dict(performance=120, cost=2, actual_pods=3)), 20)
        for value in (0, -1, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                table.efficiency(dict(performance=120, cost=value, actual_pods=3))

    def test_scenario_coverage(self):
        rows = [dict(pods=p, cpu=c, mem=m) for p, c, m in table.SCENARIOS]
        self.assertEqual(len(table.index_rows(rows)), 20)
        for invalid in (rows[:-1], rows + rows[:1]):
            with self.assertRaises(ValueError):
                table.index_rows(invalid)

    def test_supplement_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'alpha1.csv'
            rows = table.read_rows(table.HERE / 'data/alpha1.csv')
            for invalid in (rows[:-1], rows + rows[:1]):
                table.write_csv(path, invalid)
                with self.assertRaises(ValueError):
                    table.aggregate(table.HERE.parent / 'figure6_search_best_alpha/aws/data', path)

    def test_cli_outputs_and_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'results'
            command = [sys.executable, str(table.HERE / 'table_02.py'), '--output', str(output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS: Table 2', result.stdout)
            summary = table.read_rows(output / 'table2.csv')
            self.assertEqual(tuple(f"{float(r['normalized_efficiency']):.4f}" for r in summary), table.EXPECTED)
            self.assertTrue(all(int(r['samples']) == 240 for r in summary))
            self.assertEqual(len(table.read_rows(output / 'table2_details.csv')), 1200)
            for name in ('table2.md', 'table2.tex'):
                self.assertTrue((output / name).stat().st_size)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertNotEqual(subprocess.run(command[:-1] + [str(table.HERE / 'forbidden')],
                                               capture_output=True).returncode, 0)


if __name__ == '__main__':
    unittest.main()
