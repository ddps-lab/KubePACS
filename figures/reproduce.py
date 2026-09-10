"""Regenerate figures in a temporary copy and optionally compare reference PDFs."""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


FIGURES = {
    'figure1_cmp_coremark_price': [
        'cmp-coremark-price-legend.pdf', 'cpu-vendor-coremark-price.pdf',
        'intel-coremark-price.pdf', 'm-family-gen-coremark-price.pdf',
        'm6-family-coremark-price.pdf',
    ],
    'figure2_cmp_single_multi_sps': ['multiple-nodes-sps-real-availability.pdf'],
    'figure5_cmp_baseline_simulation': [
        'compare-type-usage.pdf', 'comparison-legend.pdf', 'comparison-msa.pdf',
        'comparison-related-work-benchmark-score.pdf',
    ],
    'figure6_search_best_alpha/aws': [
        'distribution-of-alphas-to-workloads-short.pdf',
        'distribution-of-alphas-to-workloads.pdf',
    ],
    'figure6_search_best_alpha/azure': [
        'distribution-of-alphas-to-workloads-azure-short.pdf',
        'distribution-of-alphas-to-workloads-azure.pdf',
    ],
    'figure7_simulation_variousalpha': ['impact-of-alpha-spacing.pdf'],
    'figure8_special_instance': ['network-disk-intensive-workload-stack.pdf'],
    'figure9_ddd': ['t3-values-to-successful-requests-count.pdf'],
    'figure10_exp_k8s_karpenter': [
        'karpenter_vs_kubecaps_availability_cr.pdf',
        'karpenter_vs_kubecaps_cost_cr.pdf',
        'karpenter_vs_kubecaps_performance_cr.pdf',
    ],
    'figure11_graph_analytics': ['graph-analytics.pdf'],
    'figure12_fis': [
        'fis-coremark-comparison.pdf', 'fis-cost-comparison.pdf',
        'fis-recovery-comparison.pdf',
    ],
}


def compare_pdf(reference, generated):
    import numpy as np
    from PIL import Image

    with tempfile.TemporaryDirectory(prefix='kubepacs-render-') as directory:
        directory = Path(directory)
        pages = []
        for name, pdf in [('reference', reference), ('generated', generated)]:
            subprocess.run(
                ['pdftoppm', '-r', '200', '-png', str(pdf), str(directory / name)],
                check=True, capture_output=True, timeout=120,
            )
            pages.append(sorted(directory.glob(f'{name}-*.png')))
        if len(pages[0]) != len(pages[1]) or not pages[0]:
            return {'pass': False, 'reason': 'page count mismatch'}
        maximum = 0
        for old, new in zip(*pages):
            with Image.open(old) as a, Image.open(new) as b:
                if a.size != b.size:
                    return {'pass': False, 'reason': 'page dimensions differ'}
                delta = np.abs(np.asarray(a.convert('RGB')).astype(int)
                               - np.asarray(b.convert('RGB')).astype(int))
                maximum = max(maximum, int(delta.max()))
        return {'pass': maximum <= 8, 'max_channel_difference': maximum,
                'exact_pixels': maximum == 0}


def main():
    source = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=source.parent / 'artifact-results/figures')
    parser.add_argument('--compare', action='store_true', help='Compare with bundled reference PDFs at 200 DPI')
    args = parser.parse_args()
    output = args.output.resolve()
    if output == source or source in output.parents:
        parser.error('--output must be outside the figures source directory')
    if output.exists():
        parser.error('--output must not already exist; choose a fresh run directory')
    if args.compare:
        if not shutil.which('pdftoppm'):
            parser.error('--compare requires pdftoppm (Poppler)')
        from matplotlib import font_manager
        try:
            font_manager.findfont('Roboto', fallback_to_default=False)
        except ValueError:
            parser.error('--compare requires the Roboto font')
    output.mkdir(parents=True)
    report = {'compare': args.compare, 'python': sys.version, 'packages': {
        name: importlib.metadata.version(name)
        for name in ['matplotlib', 'numpy', 'pandas', 'seaborn', 'pillow']
    }, 'scripts': [], 'pdfs': [], 'pass': True}
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='kubepacs-figures-') as directory:
        work = Path(directory) / 'figures'
        shutil.copytree(source, work, ignore=shutil.ignore_patterns('.venv', '__pycache__', '*.pdf'))
        env = dict(os.environ, MPLBACKEND='Agg', MPLCONFIGDIR=str(output / 'matplotlib'))
        for folder in FIGURES:
            destination = output / folder
            destination.mkdir(parents=True)
            for script in sorted((work / folder).glob('figure_*.py')):
                script_start = time.monotonic()
                with (destination / f'{script.stem}.log').open('w') as log:
                    try:
                        result = subprocess.run([sys.executable, script.name], cwd=script.parent,
                                                env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
                        status = result.returncode
                    except subprocess.TimeoutExpired:
                        status = 124
                        log.write('\nTimed out after 180 seconds.\n')
                report['scripts'].append({'path': f'{folder}/{script.name}', 'exit_code': status,
                                          'seconds': round(time.monotonic() - script_start, 2)})
                report['pass'] &= status == 0
                print(f'{folder}/{script.name}: exit {status}', flush=True)
            for name in FIGURES[folder]:
                generated = work / folder / name
                entry = {'path': f'{folder}/{name}', 'pass': generated.exists() and generated.stat().st_size > 0}
                if entry['pass']:
                    shutil.copy2(generated, destination / name)
                    if args.compare:
                        try:
                            entry.update(compare_pdf(source / folder / name, generated))
                        except (OSError, subprocess.SubprocessError) as error:
                            entry.update({'pass': False, 'reason': str(error)})
                report['pdfs'].append(entry)
                report['pass'] &= entry['pass']
    report['seconds'] = round(time.monotonic() - start, 2)
    (output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"{'PASS' if report['pass'] else 'FAIL'}: {len(report['scripts'])} scripts, "
          f"{len(report['pdfs'])} PDFs; report: {output / 'summary.json'}")
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
