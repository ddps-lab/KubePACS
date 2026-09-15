"""Run the existing optimizer against packaged inputs for multiple requests."""

import argparse
import json
import math
import os
from pathlib import Path
import sys
import time


PROJECT = Path(__file__).resolve().parent
ROOT = PROJECT.parent
LIBRARY = ROOT / "figures/common/library"
DATA = PROJECT / "data"
REGIONS = ("us-east-1", "us-west-2", "eu-west-1", "ap-northeast-1")


def parse_case(value):
    try:
        region, pods, cpu, memory = value.split(",")
        case = (region, int(pods), float(cpu), float(memory))
        if region not in REGIONS or any(not math.isfinite(v) or v <= 0 for v in case[1:]):
            raise ValueError
        return case
    except (ValueError, OverflowError):
        raise argparse.ArgumentTypeError(
            "use REGION,PODS,VCPU,GIB with a supported region, positive integer pods, and finite positive resources"
        ) from None


def check_result(result, pods, mapping, candidates=None, cpu=None, memory=None):
    nodes = result["nodepool_config"]
    capacity = result["actual_pods"]
    if not nodes or not math.isfinite(capacity) or capacity < pods:
        raise ValueError("allocation does not cover the requested pod count")
    for key in ("cost", "performance"):
        if not math.isfinite(result[key]) or result[key] <= 0:
            raise ValueError(f"invalid {key}")
    seen = set()
    calculated_capacity = 0
    calculated_cost = 0.0
    reverse_mapping = {name: zone_id for zone_id, name in mapping.items()}
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
        key = (node["instance_type"], reverse_mapping[node["availability_zone"]])
        if key in seen:
            raise ValueError("duplicate instance/AZ recommendation")
        seen.add(key)
        if candidates is not None:
            row = candidates[key]
            if count > float(row["T3"]):
                raise ValueError("allocation exceeds input CSV availability limit")
            calculated_capacity += count * min(float(row["vCPU"]) // cpu, float(row["Memory"]) // memory)
            calculated_cost += count * float(row["SpotPrice"])
    if candidates is not None:
        if calculated_capacity < pods or not math.isclose(calculated_capacity, capacity):
            raise ValueError("reported capacity differs from input CSV calculation")
        if not math.isclose(calculated_cost, result["cost"], rel_tol=1e-8, abs_tol=1e-8):
            raise ValueError("reported cost differs from input CSV calculation")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", action="append", type=parse_case, metavar="REGION,PODS,VCPU,GIB",
        help="repeat for custom requests (default: ten scenarios from scenarios.json)",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "artifact-results/optimizer")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    figures = ROOT / "figures"
    if any(output == source or source in output.parents for source in (figures, PROJECT)):
        parser.error("output must be outside figures/ and optimizer/")
    if args.case:
        cases = args.case
    else:
        with (PROJECT / "scenarios.json").open() as stream:
            cases = [parse_case(",".join(str(row[k]) for k in ("region", "pods", "cpu", "mem")))
                     for row in json.load(stream)]
    import csv

    inputs = {}
    for region in dict.fromkeys(case[0] for case in cases):
        input_csv = DATA / f"{region}.csv"
        mapping_path = DATA / f"{region}_az_mapping.json"
        for path in (input_csv, mapping_path):
            if not path.is_file():
                parser.error(f"required local input missing: {path}")
        with mapping_path.open() as stream:
            mapping = json.load(stream)
        if (not isinstance(mapping, dict) or not mapping
                or len(set(mapping.values())) != len(mapping)
                or any(not name.startswith(region) for name in mapping.values())):
            parser.error(f"invalid AZ mapping for {region}")
        with input_csv.open() as stream:
            candidates = {(row["InstanceType"], row["AZ"]): row for row in csv.DictReader(stream)}
        if not candidates or any(az not in mapping for _, az in candidates):
            parser.error(f"input CSV contains unmapped availability zones for {region}")
        inputs[region] = (input_csv, mapping_path, mapping, candidates)
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        parser.error(f"choose a fresh writable output directory: {error}")

    sys.path.insert(0, str(LIBRARY))
    from alpha_ILP_library_v4 import getGoldenNodepool

    reports = []
    previous_cwd = Path.cwd()
    # The library resolves its AZ cache relative to the working directory.
    os.chdir(DATA)
    try:
        for index, (region, pods, cpu, memory) in enumerate(cases, 1):
            input_csv, mapping_path, mapping, candidates = inputs[region]
            report = {
                "request": {"region": region, "pods": pods, "cpu": cpu, "mem": memory},
                "input_csv": str(input_csv.relative_to(ROOT)),
                "az_mapping": str(mapping_path.relative_to(ROOT)),
            }
            started = time.monotonic()
            try:
                result = getGoldenNodepool(
                    str(input_csv), pod_count=pods, pod_cpu=cpu,
                    pod_mem=memory, region=region,
                )
                check_result(result, pods, mapping, candidates, cpu, memory)
                report.update({key: result[key] for key in (
                    "alpha", "cost", "performance", "actual_pods", "nodepool_config",
                )})
                report["pass"] = True
            except Exception as error:
                report.update({"pass": False, "error": f"{type(error).__name__}: {error}"})
            report["elapsed_seconds"] = round(time.monotonic() - started, 3)
            reports.append(report)
            text = json.dumps(report, indent=2, allow_nan=False)
            (output / f"scenario-{index:02d}.json").write_text(text + "\n")
            print(text)
    finally:
        os.chdir(previous_cwd)
    passed = all(report["pass"] for report in reports)
    summary = {
        "pass": passed,
        "scenarios": reports,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(f"{'PASS' if passed else 'FAIL'}: {len(reports)} local optimizer scenarios")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
