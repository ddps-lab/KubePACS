"""Regenerate Table 2 from stored alpha-sweep and allocation results."""

import argparse
import csv
import math
from pathlib import Path
from statistics import mean


HERE = Path(__file__).resolve().parent
RUNS = tuple(f'result_11{day:02d}{hour:02d}'
             for day in (3, 4, 5) for hour in (3, 9, 15, 21))
SCENARIOS = {(pods, cpu, mem) for pods in (10, 50, 100, 400, 1000)
             for cpu, mem in ((1, 2), (2, 2), (1, 4))}
SCENARIOS.update({(17, 7, 7), (75, 3, 5), (115, 4, 2), (287, 1, 6), (439, 1, 9)})
CONFIGS = ('Greedy', 'alpha=0', 'alpha=0.5', 'alpha=1', 'Ours')
EXPECTED = ('0.8616', '0.9563', '0.0006', '0.0001', '1.0000')


def read_rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def scenario(row):
    values = tuple(float(row[name]) for name in ('pods', 'cpu', 'mem'))
    if not all(math.isfinite(v) and v > 0 and v.is_integer() for v in values):
        raise ValueError(f'Invalid scenario: {values}')
    return tuple(int(v) for v in values)


def index_rows(rows):
    indexed = {}
    for row in rows:
        key = scenario(row)
        if key in indexed:
            raise ValueError(f'Duplicate scenario: {key}')
        indexed[key] = row
    if indexed.keys() != SCENARIOS:
        raise ValueError('Expected all 20 paper scenarios exactly once')
    return indexed


def efficiency(row):
    values = [float(row[name]) for name in ('performance', 'cost', 'actual_pods')]
    if not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError(f'Invalid performance, cost, or actual_pods: {values}')
    performance, cost, actual_pods = values
    return performance / (cost * actual_pods)


def aggregate(data, alpha1):
    if {p.name for p in data.glob('result_*') if p.is_dir()} != set(RUNS):
        raise ValueError('Expected the 12 paper runs')
    supplements = {}
    for row in read_rows(alpha1):
        key = (row['run'], scenario(row))
        if key in supplements or float(row['alpha']) != 1.0:
            raise ValueError(f'Invalid or duplicate alpha=1 row: {key}')
        supplements[key] = row
    if supplements.keys() != {(run, key) for run in RUNS for key in SCENARIOS}:
        raise ValueError('Expected 240 alpha=1 results')

    records = []
    for run in RUNS:
        folder = data / run
        golden = index_rows(read_rows(folder / 'golden_section_summary.csv'))
        greedy = index_rows(read_rows(folder / 'greedy_summary.csv'))
        for key in sorted(SCENARIOS):
            sweep = read_rows(folder / 'specific_result' / ('result_%d_%d_%d.csv' % key))
            selected = [greedy[key]]
            for alpha in (0.0, 0.5):
                matches = [r for r in sweep if float(r['alpha']) == alpha]
                if len(matches) != 1:
                    raise ValueError(f'{run}/{key}: expected one alpha={alpha} row')
                selected.append(matches[0])
            selected.extend([supplements[(run, key)], golden[key]])
            reference = efficiency(golden[key])
            for config, row in zip(CONFIGS, selected):
                records.append(dict(run=run, pods=key[0], cpu=key[1], mem=key[2],
                                    configuration=config, normalized_efficiency=efficiency(row) / reference))
    summary = [dict(configuration=config, samples=240,
                    normalized_efficiency=mean(r['normalized_efficiency'] for r in records
                                               if r['configuration'] == config))
               for config in CONFIGS]
    return summary, records


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=HERE.parent / 'figure6_search_best_alpha/aws/data')
    parser.add_argument('--alpha1', type=Path, default=HERE / 'data/alpha1.csv')
    parser.add_argument('--output', type=Path, default=HERE.parents[1] / 'artifact-results/table2')
    args = parser.parse_args()
    output = args.output.resolve()
    source = HERE.parent
    if output == source or source in output.parents or output.exists():
        parser.error('--output must be new and outside figures/')
    try:
        summary, records = aggregate(args.data, args.alpha1)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    actual = tuple(f"{row['normalized_efficiency']:.4f}" for row in summary)
    if actual != EXPECTED:
        parser.error(f'Table 2 mismatch: computed {actual}, expected {EXPECTED}')
    output.mkdir(parents=True)
    write_csv(output / 'table2.csv', summary)
    write_csv(output / 'table2_details.csv', records)
    markdown = ('| Metric | Greedy | alpha=0 | alpha=0.5 | alpha=1 | Ours |\n'
                '| --- | ---: | ---: | ---: | ---: | ---: |\n'
                '| Normalized E_Total | ' + ' | '.join(actual) + ' |\n')
    (output / 'table2.md').write_text(markdown)
    latex = ('\\begin{tabular}{lrrrrr}\n\\hline\n'
             ' & Greedy & $\\alpha=0$ & $\\alpha=0.5$ & $\\alpha=1$ & Ours \\\\\n'
             '$E_{\\mathrm{Total}}$ & ' + ' & '.join(actual) + ' \\\\\n'
             '\\hline\n\\end{tabular}\n')
    (output / 'table2.tex').write_text(latex)
    print(markdown)
    print(f'PASS: Table 2, 240 samples per configuration; output: {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
