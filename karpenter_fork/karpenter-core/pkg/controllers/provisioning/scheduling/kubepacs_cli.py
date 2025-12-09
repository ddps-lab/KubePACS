import argparse
import json
import pandas as pd
from pulp import *
import numpy as np
import requests
import boto3
import os
import sys
import re

# Suppress warnings
import warnings
warnings.filterwarnings("ignore")

# Redirect stdout to stderr to ensure only the final JSON is printed to actual stdout
original_stdout = sys.stdout
sys.stdout = sys.stderr

def fetch_and_cache_az_mapping(region='us-east-1'):
    try:
        ec2 = boto3.client('ec2', region_name=region)
        response = ec2.describe_availability_zones(AllAvailabilityZones=True)
        mapping = {az['ZoneId']: az['ZoneName'] for az in response['AvailabilityZones']}
        return mapping
    except Exception as e:
        sys.stderr.write(f"Error fetching AZ mapping: {e}\n")
        return {}

def get_aws_spot_prices(target_region='us-east-1', allow_arm=True):
    spot_price_url = "https://d26bk4799jlxhe.cloudfront.net/latest_data/latest_aws.json"

    try:
        response = requests.get(spot_price_url)
        response.raise_for_status()
        
        spot_data = response.json()
        
        spot_prices = [] 
        for item in spot_data:
            instance_type = item.get('InstanceType')
            region = item.get('Region')
            az = item.get('AZ')
            spot_price_value = item.get('SpotPrice')
            t3_value = item.get('T3')
            sps_value = item.get('SPS')
            if_value = item.get('IF')
            ondemand_price_value = item.get('OndemandPrice')

            if instance_type and region == target_region:
                spot_price_float = float(spot_price_value) if spot_price_value is not None else None
                ondemand_price_float = float(ondemand_price_value) if ondemand_price_value is not None else None
                
                spot_prices.append({
                    'InstanceType': instance_type,
                    'AZ': az,
                    'SpotPrice': spot_price_float,
                    'OndemandPrice': ondemand_price_float,
                    'T3': t3_value,
                    'SPS': sps_value,
                    'IF': if_value
                })
        
        df_spot = pd.DataFrame(spot_prices)
        
        # Load CoreMark data from the same directory as the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        coremark_path = os.path.join(script_dir, 'aws_coremark_singlecore.csv')
        df_coremark = pd.read_csv(coremark_path)

        df_merged = pd.merge(df_spot, df_coremark[['InstanceType', 'CoreMark']], on='InstanceType', how='left')
        df_merged.dropna(subset=['CoreMark'], inplace=True)
        # Filter out invalid spot prices
        df_merged = df_merged[df_merged['SpotPrice'] > 0]

        client = boto3.client('ec2', region_name=target_region)
        instance_types_to_describe = df_merged['InstanceType'].dropna().unique().tolist()
        specs_list = []
        
        chunk_size = 100
        all_specs = []
        
        if instance_types_to_describe:
            try:
                for i in range(0, len(instance_types_to_describe), chunk_size):
                    chunk = instance_types_to_describe[i:i + chunk_size]
                    response = client.describe_instance_types(InstanceTypes=chunk)
                    all_specs.extend(response.get('InstanceTypes', []))
                
                for spec in all_specs:
                    instance_type = spec.get('InstanceType')
                    vcpu_info = spec.get('VCpuInfo', {})
                    memory_info = spec.get('MemoryInfo', {})
                    vcpu = vcpu_info.get('DefaultVCpus')
                    memory = memory_info.get('SizeInMiB')
                    
                    if instance_type and vcpu is not None and memory is not None:
                        specs_list.append({
                            'InstanceType': instance_type,
                            'vCPU': vcpu,
                            'Memory': memory / 1024
                        })
                
                df_specs = pd.DataFrame(specs_list)
                df_merged = pd.merge(df_merged, df_specs, on='InstanceType', how='left')
                df_merged = df_merged[['InstanceType', 'AZ', 'vCPU', 'Memory', 'T3', 'SPS', 'IF', 'SpotPrice', 'OndemandPrice', 'CoreMark']]

            except Exception as e:
                sys.stderr.write(f"AWS API Error: {e}\n")
                return None
        
        if not allow_arm:
            df_merged = df_merged[~df_merged['InstanceType'].str.split('.').str[0].str.contains('g')]

        return df_merged

    except Exception as e:
        sys.stderr.write(f"Error getting spot prices: {e}\n")
        return None

def extract_base_and_option(instance_family):
    pattern = (
        r"^([a-z]+[0-9]+(?:(?:a|g|i|m1ultra|m2|m2pro)(?:-flex)?|(?:-flex)?))"  # base
        r"([a-z0-9]*)$"  # option (optional suffix)
    )
    match = re.match(pattern, instance_family)
    if match:
        base = match.group(1)
        option = match.group(2)
        return base, option
    return instance_family, ""

def scale_coremark_for_specialized(df, workload_intensity):
    option_map = {
        "network": "n",
        "disk": "d",
        "disk_network": ["d", "n"]
    }

    if workload_intensity not in option_map or workload_intensity == "default":
        return df

    current_option_map = option_map[workload_intensity]
    if isinstance(current_option_map, list):
        def is_target_option(opt_str):
            return all(char_opt in opt_str for char_opt in current_option_map)
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

def load_and_preprocess(df, pod_cpu, pod_mem, workload_intensity="default", allowed_instances=None):
    if df.empty:
        return df

    if workload_intensity != "default":
        df["InstanceFamily"] = df["InstanceType"].str.split(".").str[0]
        df[["BaseFamily", "InstanceOptions"]] = df["InstanceFamily"].apply(
            lambda x: pd.Series(extract_base_and_option(x))
        )

    df['T3'] = pd.to_numeric(df['T3'], errors='coerce')
    df.dropna(subset=['T3'], inplace=True)
    df['Max_Instance'] = df['T3']
    
    # Subtract overhead (simulated kube-reserved)
    # vCPU: 0.1 core, Memory: 200 MiB
    df['Net_vCPU'] = df['vCPU'] - 0.1
    df['Net_Memory'] = df['Memory'] - 0.2
    
    df['PodAssignable'] = df.apply(
        lambda row: max(0, min(row['Net_vCPU'] // pod_cpu, row['Net_Memory'] // pod_mem)), axis=1)
    df = df[df['PodAssignable'] > 0].reset_index(drop=True)
    
    df['CoreMark'] = pd.to_numeric(df['CoreMark'], errors='coerce')
    df['SpotPrice'] = pd.to_numeric(df['SpotPrice'], errors='coerce')
    df['OndemandPrice'] = pd.to_numeric(df['OndemandPrice'], errors='coerce')

    # AZ Handling: Ensure consistent naming
    if 'AZ' in df.columns:
        df.rename(columns={'AZ': 'AvailabilityZone'}, inplace=True)
    
    # Heuristic AZ mapping correction for ZoneIds
    if not df.empty:
        first_az = df['AvailabilityZone'].iloc[0]
        if '-az' in str(first_az): 
            az_mapping = fetch_and_cache_az_mapping(args.region) # Use global args.region if available
            df['AvailabilityZone'] = df['AvailabilityZone'].map(az_mapping).fillna(df['AvailabilityZone'])

    df['InstanceKey'] = df['InstanceType'] + '_' + df['AvailabilityZone']
    df = df.drop_duplicates(subset=['InstanceKey'])

    # Apply Workload Intensity Scaling
    df = scale_coremark_for_specialized(df, workload_intensity)

    # Filtering by allowed_instances
    if allowed_instances:
        df = df.rename(columns={'AZ': 'AvailabilityZone'}) # Ensure consistency
        allowed_df = pd.DataFrame(allowed_instances)
        allowed_df.rename(columns={'instance_type': 'InstanceType', 'availability_zone': 'AvailabilityZone'}, inplace=True)
        
        df_merged = pd.merge(df, allowed_df, on=['InstanceType', 'AvailabilityZone'], how='inner')

        if df_merged.empty:
            aws_azs = df['AvailabilityZone'].unique() if not df.empty else "Empty"
            allowed_azs = allowed_df['AvailabilityZone'].unique() if not allowed_df.empty else "Empty"
            msg = (f"No allowed instances remaining after filtering. "
                   f"Allowed instances count: {len(allowed_df)}, AWS instances count: {len(df)}. "
                   f"AWS AZs: {aws_azs}, Allowed AZs: {allowed_azs}")
            print(msg, file=sys.stderr, flush=True)
            sys.exit(1)
        
        df = df_merged

    return df

def define_problem():
    return LpProblem("Pod_Instance_Selection", LpMinimize)

def define_variables(keys):
    return LpVariable.dicts("x", keys, lowBound=0, cat='Integer')

def set_alpha_weighted_objective(prob, x_vars, df, alpha, scale="min"):
    keys = df['InstanceKey'].tolist()
    spot = dict(zip(keys, df['SpotPrice']))
    perf = dict(zip(keys, df['CoreMark']))
    pod_assign = dict(zip(keys, df['PodAssignable']))

    if scale == "min":
        # min based scaling
        min_spot = min(spot.values())
        min_perf = min([p * pod_assign[k] for k, p in perf.items()])
        
        normalized_cost = lpSum([(spot[k] / min_spot) * x_vars[k] for k in keys])
        normalized_perf = lpSum([(perf[k] * pod_assign[k] / min_perf) * x_vars[k] for k in keys])
    
    elif scale == "log":
        # log based scaling
        log_spot = {k: np.log1p(v) for k, v in spot.items()}
        log_perf = {k: np.log1p(p * pod_assign[k]) for k, p in perf.items()}
        
        min_log_spot = min(log_spot.values())
        min_log_perf = min(log_perf.values())
        
        normalized_cost = lpSum([(log_spot[k] / min_log_spot) * x_vars[k] for k in keys])
        normalized_perf = lpSum([(log_perf[k] / min_log_perf) * x_vars[k] for k in keys])
    
    elif scale == "min-max":
        # min-max based scaling
        min_spot = min(spot.values())
        max_spot = max(spot.values())
        min_perf = min([p * pod_assign[k] for k, p in perf.items()])
        max_perf = max([p * pod_assign[k] for k, p in perf.items()])
        
        normalized_cost = lpSum([((spot[k] - min_spot) / (max_spot - min_spot)) * x_vars[k] for k in keys])
        normalized_perf = lpSum([((perf[k] * pod_assign[k] - min_perf) / (max_perf - min_perf)) * x_vars[k] for k in keys])
    
    # Weighted objective function
    prob += (1 - alpha) * normalized_cost - alpha * normalized_perf

def add_constraints(prob, x_vars, df, pod_count):
    keys = df['InstanceKey'].tolist()
    pod_assign = dict(zip(keys, df['PodAssignable']))
    max_inst = dict(zip(keys, df['Max_Instance']))

    # Min Pod Requirement
    prob += lpSum([pod_assign[k] * x_vars[k] for k in keys]) >= pod_count

    # Max Instance Limit
    for k in keys:
        prob += x_vars[k] <= max_inst[k]

def solve_and_report(prob, x_vars, df, alpha):
    prob.solve(PULP_CBC_CMD(msg=0))
    
    if LpStatus[prob.status] != 'Optimal':
        return [], {}
        
    # Create a lookup dictionary manually to avoid duplicate index errors
    keys = {row['InstanceKey']: row.to_dict() for _, row in df.iterrows()}
    results = []
    total_cost = 0
    total_pod_weighted_coremark = 0
    total_pods_assigned_by_model = 0
    
    for k, var in x_vars.items():
        if var.varValue > 0:
            info = keys[k]
            # Debug log to file
            with open('/tmp/kubepacs_debug.log', 'a') as debug_f:
                debug_f.write(f"[DEBUG] Key: {k}, Raw VarValue: {var.varValue}, Int Cast: {int(var.varValue)}\n")
                debug_f.write(f"[DEBUG] Instance: {info['InstanceType']}, vCPU: {info['vCPU']}, Memory: {info['Memory']}, PodAssignable: {info['PodAssignable']}, SpotPrice: {info['SpotPrice']}\n")
            
            count = int(var.varValue)
            pods_on_this_type = info['PodAssignable'] * count
            cost = info['SpotPrice'] * count
            pod_weighted_coremark = info['CoreMark'] * pods_on_this_type
            
            results.append({
                'InstanceKey': k,
                'Type': info['InstanceType'],
                'AZ': info['AvailabilityZone'], # Use consistent key
                'Count': count,
                'TotalPodsOnType': pods_on_this_type
            })
            
            total_cost += cost
            total_pod_weighted_coremark += pod_weighted_coremark
            total_pods_assigned_by_model += pods_on_this_type
            
    summary = {
        'Total Cost': total_cost,
        'Total PodWeighted CoreMark': total_pod_weighted_coremark,
        'Total Pods Assigned': total_pods_assigned_by_model
    }
    return results, summary

def generate_alpha_solutions(df, pod_count, pod_cpu, pod_mem, alpha_values, workload_intensity="default", scale="min", allowed_instances=None):
    alpha_solutions = []
    
    # Preprocess once if possible, but since workload_intensity is constant, we can.
    # However allowed_instances might be applied.
    processed_df = load_and_preprocess(df.copy(), pod_cpu, pod_mem, workload_intensity, allowed_instances)
    
    if processed_df.empty:
        return []

    keys = processed_df['InstanceKey'].tolist()

    for alpha in alpha_values:
        prob = define_problem()
        x_vars = define_variables(keys)
        
        set_alpha_weighted_objective(prob, x_vars, processed_df, alpha, scale=scale)
        add_constraints(prob, x_vars, processed_df, pod_count)
        
        results, summary = solve_and_report(prob, x_vars, processed_df, alpha)
        
        if results:
            alpha_solutions.append({
                'alpha': alpha,
                'cost': summary['Total Cost'],
                'performance': summary['Total PodWeighted CoreMark'],
                'results': results
            })
    
    return alpha_solutions

def getGoldenNodepool(df, pod_count, pod_cpu, pod_mem, allowed_instances=None, workload_intensity="default", left=0.0, right=1, tolerance=0.01, max_iterations=20, scale="min"):
    golden_ratio = (np.sqrt(5) - 1) / 2
    
    all_results = []
    
    best_alpha = None
    best_perf_per_cost = -float('inf')
    best_cost = None
    best_performance = None
    best_results = None
    
    def evaluate_alpha(alpha):
        nonlocal best_alpha, best_perf_per_cost, best_cost, best_performance, best_results
        
        alpha_values = [alpha]
        points = generate_alpha_solutions(df, pod_count, pod_cpu, pod_mem, alpha_values, workload_intensity=workload_intensity, scale=scale, allowed_instances=allowed_instances)
        
        if not points:
            return -float('inf')
        
        point = points[0]
        all_results.append(point)
        
        actual_pods = sum(r['TotalPodsOnType'] for r in point['results'])
        if actual_pods == 0:
            return -float('inf')

        # New performance metric from Library v4: performance / (cost * actual_pods)
        # This penalizes large nodes if they aren't fully utilized for the specific pod count
        calc_metric = point['performance'] / (point['cost'] * actual_pods)
        
        if calc_metric > best_perf_per_cost:
            best_perf_per_cost = calc_metric
            best_alpha = alpha
            best_cost = point['cost']
            best_performance = point['performance']
            best_results = point['results']
        
        return calc_metric
    
    x1 = left + (1 - golden_ratio) * (right - left)
    x2 = left + golden_ratio * (right - left)
    
    f_left = evaluate_alpha(left)
    f1 = evaluate_alpha(x1)
    f2 = evaluate_alpha(x2)
    f_right = evaluate_alpha(right)
    
    iteration = 0
    while (right - left) > tolerance and iteration < max_iterations:
        if f1 > f2:
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
    
    # Iterate all results to find best based on specific metric
    final_best_result = None
    final_best_metric = -float('inf')
    
    for result in all_results:
        actual_pods = sum(r['TotalPodsOnType'] for r in result['results'])
        if actual_pods == 0: continue
        
        # Consistent metric calculation
        performance_metric = result['performance'] / (result['cost'] * actual_pods)
        
        if performance_metric > final_best_metric:
            final_best_result = result
            final_best_metric = performance_metric
    
    if not final_best_result:
        return None

    target_instances = []
    
    for node in final_best_result['results']:
        target_instances.append({
            "instance_type": str(node['Type']),
            "availability_zone": str(node['AZ']), # Already mapped and clean
            "num_instances": int(node['Count'])
        })

    return target_instances

if __name__ == '__main__':
    # Change CWD to /tmp to allow PuLP to write temp files
    try:
        os.chdir('/tmp')
    except Exception as e:
        sys.stderr.write(f"Warning: Could not chdir to /tmp: {e}\n")

    parser = argparse.ArgumentParser()
    parser.add_argument('--pod-count', type=int, required=True)
    parser.add_argument('--pod-cpu', type=float, required=True)
    parser.add_argument('--pod-mem', type=float, required=True)
    parser.add_argument('--region', type=str, default='us-east-1')
    parser.add_argument('--allowed-instances-file', type=str, help='Path to JSON file containing allowed instances')
    parser.add_argument('--workload-intensity', type=str, default='default', help='Workload intensity: default, network, disk, disk_network')
    args = parser.parse_args()

    df = get_aws_spot_prices(target_region=args.region, allow_arm=False)
    if df is None:
        sys.exit(1)

    allowed_instances = None
    if args.allowed_instances_file:
        try:
            if args.allowed_instances_file == '-':
                allowed_instances = json.load(sys.stdin)
            else:
                with open(args.allowed_instances_file, 'r') as f:
                    allowed_instances = json.load(f)
        except Exception as e:
            sys.stderr.write(f"Error reading allowed instances file: {e}\n")
            sys.exit(1)

    result = getGoldenNodepool(df, args.pod_count, args.pod_cpu, args.pod_mem, 
                               allowed_instances=allowed_instances,
                               workload_intensity=args.workload_intensity)
    
    if result:
        original_stdout.write(json.dumps(result))
        original_stdout.flush()
    else:
        sys.exit(1)
