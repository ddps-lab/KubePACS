"""Run the existing optimizer against packaged inputs for multiple requests."""

import argparse
import json
import math
import os
from pathlib import Path
import sys


LIBRARY = Path(__file__).resolve().parent
ROOT = LIBRARY.parents[2]
DEFAULT_CASES = [(10, 1.0, 2.0), (50, 2.0, 4.0), (100, 1.0, 8.0)]


def parse_case(value):
    try:
        pods, cpu, memory = value.split(",")
        case = (int(pods), float(cpu), float(memory))
        if any(not math.isfinite(v) or v <= 0 for v in case):
            raise ValueError
        return case
    except (ValueError, OverflowError):
        raise argparse.ArgumentTypeError(
            "use PODS,VCPU,GIB with a positive integer pod count and positive finite resources"
        ) from None


def check_result(result, pods, mapping):
    nodes = result["nodepool_config"]
    capacity = result["actual_pods"]
    if not nodes or not math.isfinite(capacity) or capacity < pods:
        raise ValueError("allocation does not cover the requested pod count")
    for key in ("cost", "performance"):
        if not math.isfinite(result[key]) or result[key] <= 0:
            raise ValueError(f"invalid {key}")
    for node in nodes:
        count = node["num_instances"]
        if (
            not node["instance_type"]
            or node["availability_zone"] not in mapping.values()
            or not isinstance(count, int)
            or not math.isfinite(node["T3"])
            or not 0 < count <= node["T3"]
        ):
            raise ValueError("invalid node recommendation or availability limit exceeded")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", action="append", type=parse_case, metavar="PODS,VCPU,GIB",
        help="repeat for multiple requests (default: 10,1,2 / 50,2,4 / 100,1,8)",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "artifact-results/optimizer")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    figures = ROOT / "figures"
    if output == figures or figures in output.parents:
        parser.error("output must be outside figures/")
    input_csv = LIBRARY / "merged_coremark_spotdata_260221_0419.csv"
    mapping_path = LIBRARY / "us-east-1_az_mapping.json"
    for path in (input_csv, mapping_path):
        if not path.is_file():
            parser.error(f"required local input missing: {path}")
    with mapping_path.open() as stream:
        mapping = json.load(stream)
    if not isinstance(mapping, dict) or not mapping:
        parser.error("AZ mapping must be a nonempty JSON object")
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        parser.error(f"choose a fresh writable output directory: {error}")

    from alpha_ILP_library_v4 import getGoldenNodepool

    reports = []
    previous_cwd = Path.cwd()
    # The library resolves its AZ cache relative to the working directory.
    os.chdir(LIBRARY)
    try:
        for index, (pods, cpu, memory) in enumerate(args.case or DEFAULT_CASES, 1):
            report = {"request": {"pods": pods, "cpu": cpu, "mem": memory}}
            try:
                result = getGoldenNodepool(
                    str(input_csv), pod_count=pods, pod_cpu=cpu,
                    pod_mem=memory, region="us-east-1",
                )
                check_result(result, pods, mapping)
                report.update({key: result[key] for key in (
                    "alpha", "cost", "performance", "actual_pods", "nodepool_config",
                )})
                report["pass"] = True
            except Exception as error:
                report.update({"pass": False, "error": f"{type(error).__name__}: {error}"})
            reports.append(report)
            text = json.dumps(report, indent=2, allow_nan=False)
            (output / f"scenario-{index:02d}.json").write_text(text + "\n")
            print(text)
    finally:
        os.chdir(previous_cwd)
    passed = all(report["pass"] for report in reports)
    summary = {
        "pass": passed,
        "input_csv": str(input_csv.relative_to(ROOT)),
        "az_mapping": str(mapping_path.relative_to(ROOT)),
        "scenarios": reports,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(f"{'PASS' if passed else 'FAIL'}: {len(reports)} local optimizer scenarios")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
