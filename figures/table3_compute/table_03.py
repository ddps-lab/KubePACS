"""Generate Table 3 from the recorded compute-workload measurements."""

import argparse
import csv
from decimal import Decimal
from pathlib import Path


HERE = Path(__file__).resolve().parent
MEASUREMENTS = (
    ('Karpenter', 'c5.xlarge', '0.0662', 'Compilation', 9),
    ('Karpenter', 'c5.xlarge', '0.0662', 'Video enc.', 31),
    ('KubePACS', 'c7i.xlarge', '0.0733', 'Compilation', 13),
    ('KubePACS', 'c7i.xlarge', '0.0733', 'Video enc.', 47),
)
HEADERS = ('System', 'Instance', 'Price/hour', 'App', 'Req./min', 'Price/Req.')


def table_rows():
    rows = []
    for system, instance, price, app, throughput in MEASUREMENTS:
        ratio = Decimal(price) / throughput
        rows.append((system, instance, f'${price}', app, str(throughput), f'${ratio:.4f}'))
    baseline, proposed = MEASUREMENTS[1], MEASUREMENTS[3]
    price_change = (Decimal(proposed[2]) / Decimal(baseline[2]) - 1) * 100
    throughput_change = (Decimal(proposed[4]) / Decimal(baseline[4]) - 1) * 100
    displayed_baseline = Decimal(rows[1][5].removeprefix('$'))
    displayed_proposed = Decimal(rows[3][5].removeprefix('$'))
    ratio_change = (displayed_proposed / displayed_baseline - 1) * 100
    rows.append(('Best Case', '', f'{price_change:+.2f}%', 'Video enc.',
                 f'{throughput_change:+.2f}%', f'{ratio_change:+.1f}%'))
    return rows


def latex_cell(value):
    return value.replace('$', r'\$').replace('%', r'\%')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE.parents[1] / 'artifact-results/table3')
    args = parser.parse_args()
    output = args.output.resolve()
    source = HERE.parent
    if output == source or source in output.parents or output.exists():
        parser.error('--output must be new and outside figures/')
    rows = table_rows()
    output.mkdir(parents=True)
    with (output / 'table3.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADERS)
        writer.writerows(rows)
    markdown = '\n'.join([
        '| ' + ' | '.join(HEADERS) + ' |',
        '| --- | --- | ---: | --- | ---: | ---: |',
        *('| ' + ' | '.join(row) + ' |' for row in rows),
    ]) + '\n'
    (output / 'table3.md').write_text(markdown)
    latex = ['\\begin{tabular}{llrlrr}', '\\hline']
    for row in (HEADERS, *rows):
        latex.append(' & '.join(latex_cell(cell) for cell in row) + r' \\')
    latex.extend(['\\hline', '\\end{tabular}', ''])
    (output / 'table3.tex').write_text('\n'.join(latex))
    print(markdown)
    print(f'PASS: Table 3; output: {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
