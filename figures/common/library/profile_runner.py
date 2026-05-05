"""
alpha_ILP_library_v4.py의 CPU/메모리 사용률 측정 스크립트
- psutil을 사용하여 백그라운드에서 0.5초 간격 샘플링
- 4개 리전(N.Virginia, Oregon, Ireland, Tokyo) x 100회 반복
- 결과를 CSV + TXT로 저장
"""

import os
import sys
import time
import threading
import csv
from datetime import datetime

import psutil
import numpy as np

from alpha_ILP_library_v4 import get_aws_spot_prices, getGoldenNodepool


class ResourceMonitor:
    def __init__(self, interval=0.5):
        self.interval = interval
        self.process = psutil.Process(os.getpid())
        self.num_cores = psutil.cpu_count()
        self.memory_samples = []  # RSS in bytes
        self.cpu_samples = []     # percent (normalized to 0-100%)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self.process.cpu_percent(interval=None)
        self.memory_samples = []
        self.cpu_samples = []
        self._stop.clear()
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

    def _monitor(self):
        while not self._stop.is_set():
            try:
                self.memory_samples.append(self.process.memory_info().rss)
                raw_cpu = self.process.cpu_percent(interval=None)
                self.cpu_samples.append(raw_cpu / self.num_cores)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            time.sleep(self.interval)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def get_report(self):
        if not self.memory_samples:
            return None
        mem_mb = [m / (1024 * 1024) for m in self.memory_samples]
        return {
            'peak_memory_mb': max(mem_mb),
            'avg_memory_mb': sum(mem_mb) / len(mem_mb),
            'peak_cpu_pct': max(self.cpu_samples) if self.cpu_samples else 0,
            'avg_cpu_pct': sum(self.cpu_samples) / len(self.cpu_samples) if self.cpu_samples else 0,
            'samples': len(self.memory_samples),
        }


def run_single(file_path, pod_count, pod_cpu, pod_mem, workload_intensity):
    monitor = ResourceMonitor(interval=0.5)
    monitor.start()
    start_time = time.perf_counter()

    result = getGoldenNodepool(
        file_path, pod_count, pod_cpu, pod_mem,
        workload_intensity, verbose=False
    )

    elapsed = time.perf_counter() - start_time
    monitor.stop()
    report = monitor.get_report()
    report['elapsed_s'] = elapsed
    return result, report


def main():
    NUM_RUNS = 100
    POD_COUNT = 200
    POD_CPU = 1
    POD_MEM = 8
    WORKLOAD_INTENSITY = "default"

    REGIONS = {
        'us-east-1': 'N. Virginia',
        'us-west-2': 'Oregon',
        'eu-west-1': 'Ireland',
        'ap-northeast-1': 'Tokyo',
    }

    timestamp = datetime.now().strftime('%y%m%d_%H%M')
    csv_path = f'profile_results_{timestamp}.csv'
    txt_path = f'profile_results_{timestamp}.txt'
    num_cores = psutil.cpu_count()

    # CSV 헤더 작성
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'region', 'region_name', 'run', 'elapsed_s',
            'peak_memory_mb', 'avg_memory_mb', 'peak_cpu_pct', 'avg_cpu_pct'
        ])

    # TXT 파일 초기화
    with open(txt_path, 'w') as f:
        f.write(f"=== KubePACS ILP Profiling Report ===\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"CPU Cores: {num_cores}\n")
        f.write(f"Runs per region: {NUM_RUNS}\n")
        f.write(f"Config: POD_COUNT={POD_COUNT}, POD_CPU={POD_CPU}, POD_MEM={POD_MEM}\n\n")

    all_summaries = []

    for region, region_name in REGIONS.items():
        print(f"\n{'='*60}")
        print(f"  Region: {region_name} ({region})")
        print(f"{'='*60}")

        # 리전별 데이터 로드
        print("  Fetching spot price data...")
        file_path = get_aws_spot_prices(target_region=region, allow_arm=False)
        if file_path == -1:
            print(f"  ERROR: Failed to fetch data for {region}, skipping.")
            continue
        print(f"  Data file: {file_path}\n")

        run_reports = []
        for i in range(NUM_RUNS):
            result, report = run_single(file_path, POD_COUNT, POD_CPU, POD_MEM, WORKLOAD_INTENSITY)
            run_reports.append(report)

            # CSV에 개별 row 추가
            with open(csv_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    region, region_name, i + 1,
                    f"{report['elapsed_s']:.4f}",
                    f"{report['peak_memory_mb']:.2f}",
                    f"{report['avg_memory_mb']:.2f}",
                    f"{report['peak_cpu_pct']:.2f}",
                    f"{report['avg_cpu_pct']:.2f}",
                ])

            if (i + 1) % 10 == 0 or i == 0:
                print(
                    f"  Run {i+1:3d}/{NUM_RUNS} | "
                    f"Time: {report['elapsed_s']:.2f}s | "
                    f"Peak Mem: {report['peak_memory_mb']:.1f} MB | "
                    f"Avg CPU: {report['avg_cpu_pct']:.1f}%"
                )

        # 리전별 요약
        times = [r['elapsed_s'] for r in run_reports]
        peak_mems = [r['peak_memory_mb'] for r in run_reports]
        avg_mems = [r['avg_memory_mb'] for r in run_reports]
        peak_cpus = [r['peak_cpu_pct'] for r in run_reports]
        avg_cpus = [r['avg_cpu_pct'] for r in run_reports]

        summary = {
            'region': region,
            'region_name': region_name,
            'time_mean': np.mean(times), 'time_std': np.std(times),
            'peak_mem_mean': np.mean(peak_mems), 'peak_mem_std': np.std(peak_mems),
            'avg_mem_mean': np.mean(avg_mems), 'avg_mem_std': np.std(avg_mems),
            'peak_cpu_mean': np.mean(peak_cpus), 'peak_cpu_std': np.std(peak_cpus),
            'avg_cpu_mean': np.mean(avg_cpus), 'avg_cpu_std': np.std(avg_cpus),
        }
        all_summaries.append(summary)

        region_txt = (
            f"\n--- {region_name} ({region}) ---\n"
            f"  Execution Time : {summary['time_mean']:8.2f}s  (±{summary['time_std']:.2f}s)\n"
            f"  Peak Memory    : {summary['peak_mem_mean']:8.1f} MB (±{summary['peak_mem_std']:.1f} MB)\n"
            f"  Avg Memory     : {summary['avg_mem_mean']:8.1f} MB (±{summary['avg_mem_std']:.1f} MB)\n"
            f"  Peak CPU       : {summary['peak_cpu_mean']:8.2f}%   (±{summary['peak_cpu_std']:.2f}%)\n"
            f"  Avg CPU        : {summary['avg_cpu_mean']:8.2f}%   (±{summary['avg_cpu_std']:.2f}%)\n"
        )
        print(region_txt)

        with open(txt_path, 'a') as f:
            f.write(region_txt)

    # === 전체 요약 ===
    print("\n" + "=" * 112)
    print("  Overall Summary (All Regions)")
    print("=" * 112)
    header = f"  {'Region':<20} {'Time(s)':<16} {'Peak Mem(MB)':<18} {'Avg Mem(MB)':<18} {'Peak CPU(%)':<18} {'Avg CPU(%)':<16}"
    print(header)
    print("  " + "-" * 108)

    with open(txt_path, 'a') as f:
        f.write(f"\n{'='*112}\n")
        f.write(f"  Overall Summary (All Regions)\n")
        f.write(f"{'='*112}\n")
        f.write(header + "\n")
        f.write("  " + "-" * 108 + "\n")

    for s in all_summaries:
        line = (
            f"  {s['region_name']:<20} "
            f"{s['time_mean']:.2f} ±{s['time_std']:.2f}    "
            f"{s['peak_mem_mean']:.1f} ±{s['peak_mem_std']:.1f}      "
            f"{s['avg_mem_mean']:.1f} ±{s['avg_mem_std']:.1f}      "
            f"{s['peak_cpu_mean']:.2f} ±{s['peak_cpu_std']:.2f}      "
            f"{s['avg_cpu_mean']:.2f} ±{s['avg_cpu_std']:.2f}"
        )
        print(line)
        with open(txt_path, 'a') as f:
            f.write(line + "\n")

    # 전체 평균 row
    avg_line_sep = "  " + "-" * 108
    avg_line = (
        f"  {'Average':<20} "
        f"{np.mean([s['time_mean'] for s in all_summaries]):.2f} ±{np.mean([s['time_std'] for s in all_summaries]):.2f}    "
        f"{np.mean([s['peak_mem_mean'] for s in all_summaries]):.1f} ±{np.mean([s['peak_mem_std'] for s in all_summaries]):.1f}      "
        f"{np.mean([s['avg_mem_mean'] for s in all_summaries]):.1f} ±{np.mean([s['avg_mem_std'] for s in all_summaries]):.1f}      "
        f"{np.mean([s['peak_cpu_mean'] for s in all_summaries]):.2f} ±{np.mean([s['peak_cpu_std'] for s in all_summaries]):.2f}      "
        f"{np.mean([s['avg_cpu_mean'] for s in all_summaries]):.2f} ±{np.mean([s['avg_cpu_std'] for s in all_summaries]):.2f}"
    )
    print(avg_line_sep)
    print(avg_line)
    with open(txt_path, 'a') as f:
        f.write(avg_line_sep + "\n")
        f.write(avg_line + "\n")

    print("=" * 112)
    print(f"\nResults saved to:")
    print(f"  CSV: {csv_path}")
    print(f"  TXT: {txt_path}")

    with open(txt_path, 'a') as f:
        f.write(f"{'='*112}\n")


if __name__ == '__main__':
    main()
