"""
AWS Lambda handler for KubePACS ILP solver.
Designed for Lambda Function URL invocation.

Expected JSON body (POST):
{
    "pod_count": 10,
    "pod_cpu": 0.5,
    "pod_mem": 1.0,
    "workload_intensity": "default",       // optional: "default", "network", "disk", "disk_network"
    "region": "us-east-1",                 // required
    "allowed_instances": [...]             // optional
}
"""

import json
import os
import re
import warnings

import boto3
import numpy as np
import pandas as pd
import requests
from pulp import (
    PULP_CBC_CMD,
    LpMinimize,
    LpProblem,
    LpStatus,
    LpVariable,
    lpSum,
)

warnings.filterwarnings("ignore")

# Change CWD to /tmp so PuLP can write temp files
os.chdir("/tmp")

# ---------------------------------------------------------------------------
# Coremark CSV: bundled alongside this file in the Lambda deployment package
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COREMARK_PATH = os.path.join(SCRIPT_DIR, "aws_coremark_singlecore.csv")


# ---------------------------------------------------------------------------
# Helper functions (ported from kubepacs_cli.py)
# ---------------------------------------------------------------------------

def fetch_and_cache_az_mapping(region="us-east-1"):
    try:
        ec2 = boto3.client("ec2", region_name=region)
        response = ec2.describe_availability_zones(AllAvailabilityZones=True)
        return {az["ZoneId"]: az["ZoneName"] for az in response["AvailabilityZones"]}
    except Exception as e:
        print(f"[WARN] Error fetching AZ mapping: {e}")
        return {}


def get_aws_spot_prices(target_region="us-east-1", allow_arm=True):
    spot_price_url = "https://d26bk4799jlxhe.cloudfront.net/latest_data/latest_aws.json"

    try:
        response = requests.get(spot_price_url)
        response.raise_for_status()
        spot_data = response.json()

        spot_prices = []
        for item in spot_data:
            instance_type = item.get("InstanceType")
            region = item.get("Region")
            if instance_type and region == target_region:
                spot_price_value = item.get("SpotPrice")
                ondemand_price_value = item.get("OndemandPrice")
                spot_prices.append({
                    "InstanceType": instance_type,
                    "AZ": item.get("AZ"),
                    "SpotPrice": float(spot_price_value) if spot_price_value is not None else None,
                    "OndemandPrice": float(ondemand_price_value) if ondemand_price_value is not None else None,
                    "T3": item.get("T3"),
                    "SPS": item.get("SPS"),
                    "IF": item.get("IF"),
                })

        df_spot = pd.DataFrame(spot_prices)

        df_coremark = pd.read_csv(COREMARK_PATH)
        df_merged = pd.merge(df_spot, df_coremark[["InstanceType", "CoreMark"]], on="InstanceType", how="left")
        df_merged.dropna(subset=["CoreMark"], inplace=True)
        df_merged = df_merged[df_merged["SpotPrice"] > 0]

        # Fetch instance specs from EC2 API
        client = boto3.client("ec2", region_name=target_region)
        instance_types_to_describe = df_merged["InstanceType"].dropna().unique().tolist()
        specs_list = []
        chunk_size = 100

        if instance_types_to_describe:
            all_specs = []
            for i in range(0, len(instance_types_to_describe), chunk_size):
                chunk = instance_types_to_describe[i : i + chunk_size]
                resp = client.describe_instance_types(InstanceTypes=chunk)
                all_specs.extend(resp.get("InstanceTypes", []))

            for spec in all_specs:
                it = spec.get("InstanceType")
                vcpu = spec.get("VCpuInfo", {}).get("DefaultVCpus")
                memory = spec.get("MemoryInfo", {}).get("SizeInMiB")
                if it and vcpu is not None and memory is not None:
                    specs_list.append({"InstanceType": it, "vCPU": vcpu, "Memory": memory / 1024})

            df_specs = pd.DataFrame(specs_list)
            df_merged = pd.merge(df_merged, df_specs, on="InstanceType", how="left")
            df_merged = df_merged[
                ["InstanceType", "AZ", "vCPU", "Memory", "T3", "SPS", "IF", "SpotPrice", "OndemandPrice", "CoreMark"]
            ]

        if not allow_arm:
            df_merged = df_merged[~df_merged["InstanceType"].str.split(".").str[0].str.contains("g")]

        return df_merged

    except Exception as e:
        print(f"[ERROR] Error getting spot prices: {e}")
        return None


def extract_base_and_option(instance_family):
    pattern = (
        r"^([a-z]+[0-9]+(?:(?:a|g|i|m1ultra|m2|m2pro)(?:-flex)?|(?:-flex)?))"
        r"([a-z0-9]*)$"
    )
    match = re.match(pattern, instance_family)
    if match:
        return match.group(1), match.group(2)
    return instance_family, ""


def scale_coremark_for_specialized(df, workload_intensity):
    option_map = {
        "network": "n",
        "disk": "d",
        "disk_network": ["d", "n"],
    }
    if workload_intensity not in option_map or workload_intensity == "default":
        return df

    current_option_map = option_map[workload_intensity]
    if isinstance(current_option_map, list):
        def is_target_option(opt_str):
            return all(c in opt_str for c in current_option_map)
    else:
        def is_target_option(opt_str):
            return current_option_map in opt_str

    base_mask = df["InstanceOptions"] == ""
    base_prices = df[base_mask].set_index("BaseFamily")["OndemandPrice"].to_dict()

    def scale_row(row):
        on_demand_price = row.get("OndemandPrice")
        if on_demand_price is None or pd.isna(on_demand_price):
            return row["CoreMark"]
        if is_target_option(row["InstanceOptions"]) and row["BaseFamily"] in base_prices:
            base_price = base_prices[row["BaseFamily"]]
            if pd.notna(base_price) and base_price > 0 and pd.notna(on_demand_price):
                return row["CoreMark"] * (on_demand_price / base_price)
        return row["CoreMark"]

    df["CoreMark"] = df.apply(scale_row, axis=1)
    return df


def load_and_preprocess(df, pod_cpu, pod_mem, region="us-east-1", workload_intensity="default", allowed_instances=None):
    if df.empty:
        return df

    if workload_intensity != "default":
        df["InstanceFamily"] = df["InstanceType"].str.split(".").str[0]
        df[["BaseFamily", "InstanceOptions"]] = df["InstanceFamily"].apply(
            lambda x: pd.Series(extract_base_and_option(x))
        )

    df["T3"] = pd.to_numeric(df["T3"], errors="coerce")
    df.dropna(subset=["T3"], inplace=True)
    df["Max_Instance"] = df["T3"]

    VM_MEMORY_OVERHEAD_PERCENT = 0.075
    df["Net_vCPU"] = df["vCPU"] - 0.1
    df["Net_Memory"] = df["Memory"] * (1 - VM_MEMORY_OVERHEAD_PERCENT)

    df["PodAssignable"] = df.apply(
        lambda row: max(0, min(row["Net_vCPU"] // pod_cpu, row["Net_Memory"] // pod_mem)), axis=1
    )
    df = df[df["PodAssignable"] > 0].reset_index(drop=True)

    df["CoreMark"] = pd.to_numeric(df["CoreMark"], errors="coerce")
    df["SpotPrice"] = pd.to_numeric(df["SpotPrice"], errors="coerce")
    df["OndemandPrice"] = pd.to_numeric(df["OndemandPrice"], errors="coerce")

    if "AZ" in df.columns:
        df.rename(columns={"AZ": "AvailabilityZone"}, inplace=True)

    if not df.empty:
        first_az = df["AvailabilityZone"].iloc[0]
        if "-az" in str(first_az):
            az_mapping = fetch_and_cache_az_mapping(region)
            df["AvailabilityZone"] = df["AvailabilityZone"].map(az_mapping).fillna(df["AvailabilityZone"])

    df["InstanceKey"] = df["InstanceType"] + "_" + df["AvailabilityZone"]
    df = df.drop_duplicates(subset=["InstanceKey"])

    df = scale_coremark_for_specialized(df, workload_intensity)

    if allowed_instances:
        allowed_df = pd.DataFrame(allowed_instances)
        allowed_df.rename(columns={"instance_type": "InstanceType", "availability_zone": "AvailabilityZone"}, inplace=True)
        df = pd.merge(df, allowed_df, on=["InstanceType", "AvailabilityZone"], how="inner")
        if df.empty:
            raise ValueError("No allowed instances remaining after filtering.")

    return df


# ---------------------------------------------------------------------------
# ILP solver functions
# ---------------------------------------------------------------------------

def define_problem():
    return LpProblem("Pod_Instance_Selection", LpMinimize)


def define_variables(keys):
    return LpVariable.dicts("x", keys, lowBound=0, cat="Integer")


def set_alpha_weighted_objective(prob, x_vars, df, alpha, scale="min"):
    keys = df["InstanceKey"].tolist()
    spot = dict(zip(keys, df["SpotPrice"]))
    perf = dict(zip(keys, df["CoreMark"]))
    pod_assign = dict(zip(keys, df["PodAssignable"]))

    if scale == "min":
        min_spot = min(spot.values())
        min_perf = min([p * pod_assign[k] for k, p in perf.items()])
        normalized_cost = lpSum([(spot[k] / min_spot) * x_vars[k] for k in keys])
        normalized_perf = lpSum([(perf[k] * pod_assign[k] / min_perf) * x_vars[k] for k in keys])
    elif scale == "log":
        log_spot = {k: np.log1p(v) for k, v in spot.items()}
        log_perf = {k: np.log1p(p * pod_assign[k]) for k, p in perf.items()}
        min_log_spot = min(log_spot.values())
        min_log_perf = min(log_perf.values())
        normalized_cost = lpSum([(log_spot[k] / min_log_spot) * x_vars[k] for k in keys])
        normalized_perf = lpSum([(log_perf[k] / min_log_perf) * x_vars[k] for k in keys])
    elif scale == "min-max":
        min_spot = min(spot.values())
        max_spot = max(spot.values())
        min_perf = min([p * pod_assign[k] for k, p in perf.items()])
        max_perf = max([p * pod_assign[k] for k, p in perf.items()])
        normalized_cost = lpSum([((spot[k] - min_spot) / (max_spot - min_spot)) * x_vars[k] for k in keys])
        normalized_perf = lpSum([((perf[k] * pod_assign[k] - min_perf) / (max_perf - min_perf)) * x_vars[k] for k in keys])

    prob += (1 - alpha) * normalized_cost - alpha * normalized_perf


def add_constraints(prob, x_vars, df, pod_count):
    keys = df["InstanceKey"].tolist()
    pod_assign = dict(zip(keys, df["PodAssignable"]))
    max_inst = dict(zip(keys, df["Max_Instance"]))

    prob += lpSum([pod_assign[k] * x_vars[k] for k in keys]) >= pod_count
    for k in keys:
        prob += x_vars[k] <= max_inst[k]


def solve_and_report(prob, x_vars, df):
    prob.solve(PULP_CBC_CMD(msg=0))

    if LpStatus[prob.status] != "Optimal":
        return [], {}

    keys_lookup = {row["InstanceKey"]: row.to_dict() for _, row in df.iterrows()}
    results = []
    total_cost = 0
    total_pod_weighted_coremark = 0
    total_pods_assigned = 0

    for k, var in x_vars.items():
        if var.varValue > 0:
            info = keys_lookup[k]
            count = int(var.varValue)
            pods_on_this_type = info["PodAssignable"] * count
            cost = info["SpotPrice"] * count
            pod_weighted_coremark = info["CoreMark"] * pods_on_this_type

            results.append({
                "InstanceKey": k,
                "Type": info["InstanceType"],
                "AZ": info["AvailabilityZone"],
                "Count": count,
                "TotalPodsOnType": pods_on_this_type,
            })
            total_cost += cost
            total_pod_weighted_coremark += pod_weighted_coremark
            total_pods_assigned += pods_on_this_type

    summary = {
        "Total Cost": total_cost,
        "Total PodWeighted CoreMark": total_pod_weighted_coremark,
        "Total Pods Assigned": total_pods_assigned,
    }
    return results, summary


def generate_alpha_solutions(df, pod_count, pod_cpu, pod_mem, alpha_values, region="us-east-1",
                             workload_intensity="default", scale="min", allowed_instances=None):
    processed_df = load_and_preprocess(df.copy(), pod_cpu, pod_mem, region, workload_intensity, allowed_instances)
    if processed_df.empty:
        return []

    keys = processed_df["InstanceKey"].tolist()
    alpha_solutions = []

    for alpha in alpha_values:
        prob = define_problem()
        x_vars = define_variables(keys)
        set_alpha_weighted_objective(prob, x_vars, processed_df, alpha, scale=scale)
        add_constraints(prob, x_vars, processed_df, pod_count)
        results, summary = solve_and_report(prob, x_vars, processed_df)
        if results:
            alpha_solutions.append({
                "alpha": alpha,
                "cost": summary["Total Cost"],
                "performance": summary["Total PodWeighted CoreMark"],
                "results": results,
            })

    return alpha_solutions


def getGoldenNodepool(df, pod_count, pod_cpu, pod_mem, region="us-east-1",
                      allowed_instances=None, workload_intensity="default",
                      left=0.0, right=1, tolerance=0.01, max_iterations=20, scale="min"):
    golden_ratio = (np.sqrt(5) - 1) / 2
    all_results = []

    best_alpha = None
    best_perf_per_cost = -float("inf")

    def evaluate_alpha(alpha):
        nonlocal best_alpha, best_perf_per_cost

        points = generate_alpha_solutions(
            df, pod_count, pod_cpu, pod_mem, [alpha],
            region=region, workload_intensity=workload_intensity,
            scale=scale, allowed_instances=allowed_instances,
        )
        if not points:
            return -float("inf")

        point = points[0]
        all_results.append(point)

        actual_pods = sum(r["TotalPodsOnType"] for r in point["results"])
        if actual_pods == 0:
            return -float("inf")

        calc_metric = point["performance"] / (point["cost"] * actual_pods)

        if calc_metric > best_perf_per_cost:
            best_perf_per_cost = calc_metric
            best_alpha = alpha

        return calc_metric

    x1 = left + (1 - golden_ratio) * (right - left)
    x2 = left + golden_ratio * (right - left)

    evaluate_alpha(left)
    f1 = evaluate_alpha(x1)
    f2 = evaluate_alpha(x2)
    evaluate_alpha(right)

    iteration = 0
    while (right - left) > tolerance and iteration < max_iterations:
        if f1 >= f2:
            right = x2
            x2 = x1
            f2 = f1
            x1 = left + (1 - golden_ratio) * (right - left)
            f1 = evaluate_alpha(x1)
        else:
            left = x1
            x1 = x2
            f1 = f2
            x2 = left + golden_ratio * (right - left)
            f2 = evaluate_alpha(x2)
        iteration += 1

    # Find best result across all evaluated alphas
    final_best_result = None
    final_best_metric = -float("inf")

    for result in all_results:
        actual_pods = sum(r["TotalPodsOnType"] for r in result["results"])
        if actual_pods == 0:
            continue
        metric = result["performance"] / (result["cost"] * actual_pods)
        if metric > final_best_metric:
            final_best_result = result
            final_best_metric = metric

    if not final_best_result:
        return None

    print(
        f"[KubePACS] Best alpha: {final_best_result['alpha']:.4f}, "
        f"Cost: ${final_best_result['cost']:.4f}, "
        f"Performance: {final_best_result['performance']:.2f}, "
        f"Metric: {final_best_metric:.4f}"
    )

    target_instances = []
    for node in final_best_result["results"]:
        target_instances.append({
            "instance_type": str(node["Type"]),
            "availability_zone": str(node["AZ"]),
            "num_instances": int(node["Count"]),
        })

    return target_instances


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def _make_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    """
    Entry point for AWS Lambda with Function URL.

    Accepts POST with JSON body:
        pod_count (int, required)
        pod_cpu (float, required)
        pod_mem (float, required)
        workload_intensity (str, optional) - "default" | "network" | "disk" | "disk_network"
        region (str, optional) - default "us-east-1"
        allowed_instances (list, optional)
    """
    try:
        # Function URL wraps the body as a string
        if isinstance(event.get("body"), str):
            params = json.loads(event["body"])
        elif isinstance(event, dict) and "pod_count" in event:
            # Direct invocation (e.g. test console)
            params = event
        else:
            params = event.get("body", {})
            if isinstance(params, str):
                params = json.loads(params)

        # --- Validate required parameters ---
        pod_count = params.get("pod_count")
        pod_cpu = params.get("pod_cpu")
        pod_mem = params.get("pod_mem")

        region = params.get("region")

        if pod_count is None or pod_cpu is None or pod_mem is None or region is None:
            return _make_response(400, {
                "error": "Missing required parameters: pod_count, pod_cpu, pod_mem, region",
            })

        pod_count = int(pod_count)
        pod_cpu = float(pod_cpu)
        pod_mem = float(pod_mem)

        if pod_count <= 0 or pod_cpu <= 0 or pod_mem <= 0:
            return _make_response(400, {"error": "pod_count, pod_cpu, pod_mem must be positive"})

        # --- Optional parameters ---
        workload_intensity = params.get("workload_intensity", "default")
        allowed_instances = params.get("allowed_instances")

        # --- Fetch spot price data ---
        df = get_aws_spot_prices(target_region=region, allow_arm=False)
        if df is None:
            return _make_response(502, {"error": "Failed to fetch spot price data"})

        # --- Solve ---
        result = getGoldenNodepool(
            df,
            pod_count,
            pod_cpu,
            pod_mem,
            region=region,
            allowed_instances=allowed_instances,
            workload_intensity=workload_intensity,
        )

        if result is None:
            return _make_response(404, {"error": "No feasible solution found"})

        return _make_response(200, {"result": result})

    except json.JSONDecodeError:
        return _make_response(400, {"error": "Invalid JSON body"})
    except ValueError as e:
        return _make_response(400, {"error": str(e)})
    except Exception as e:
        print(f"[ERROR] Unhandled exception: {e}")
        return _make_response(500, {"error": f"Internal server error: {str(e)}"})
