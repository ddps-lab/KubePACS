import argparse
import json
import pandas as pd
from pulp import *
import numpy as np
import requests
import boto3
import os
import sys

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

            if instance_type and region == target_region:
                spot_price_float = float(spot_price_value) if spot_price_value is not None else None
                
                spot_prices.append({
                    'InstanceType': instance_type,
                    'AZ': az,
                    'SpotPrice': spot_price_float,
                    'T3': t3_value
                })
        
        df_spot = pd.DataFrame(spot_prices)
        
        # Load CoreMark data from the same directory as the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        coremark_path = os.path.join(script_dir, 'aws_coremark_singlecore.csv')
        df_coremark = pd.read_csv(coremark_path)

        df_merged = pd.merge(df_spot, df_coremark[['InstanceType', 'CoreMark']], on='InstanceType', how='left')
        df_merged.dropna(subset=['CoreMark'], inplace=True)

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
                df_merged = df_merged[['InstanceType', 'AZ', 'vCPU', 'Memory', 'T3', 'SpotPrice', 'CoreMark']]

            except Exception as e:
                sys.stderr.write(f"AWS API Error: {e}\n")
                return None
        
        if not allow_arm:
            df_merged = df_merged[~df_merged['InstanceType'].str.split('.').str[0].str.contains('g')]

        return df_merged

    except Exception as e:
        sys.stderr.write(f"Error getting spot prices: {e}\n")
        return None

def load_and_preprocess(df, pod_cpu, pod_mem, allowed_instances=None):
    # df is now passed directly
    if 'AZ' in df.columns:
        df.rename(columns={'AZ': 'AvailabilityZone'}, inplace=True)

    df['T3'] = pd.to_numeric(df['T3'], errors='coerce')
    df.dropna(subset=['T3'], inplace=True)
    df['Max_Instance'] = (df['T3']).astype(int)
    df['PodAssignable'] = df.apply(
        lambda row: min(row['vCPU'] // pod_cpu, row['Memory'] // pod_mem), axis=1)
    df = df[df['PodAssignable'] > 0].reset_index(drop=True)
    df['CoreMark'] = pd.to_numeric(df['CoreMark'], errors='coerce')
    df['SpotPrice'] = pd.to_numeric(df['SpotPrice'], errors='coerce')
    # Fetch AZ mapping (ZoneId -> ZoneName)
    ec2 = boto3.client('ec2', region_name=args.region)
    az_response = ec2.describe_availability_zones()
    zone_id_to_name = {z['ZoneId']: z['ZoneName'] for z in az_response['AvailabilityZones']}
    
    # If df has ZoneIds (e.g. apne2-az1), map them to ZoneNames
    # Check if the first element looks like a ZoneId (e.g. ends with -az\d)
    if not df.empty:
        first_az = df['AvailabilityZone'].iloc[0]
        if '-az' in first_az: # Heuristic check
             df['AvailabilityZone'] = df['AvailabilityZone'].map(zone_id_to_name).fillna(df['AvailabilityZone'])

    df['InstanceKey'] = df['InstanceType'] + '_' + df['AvailabilityZone']

    if allowed_instances:
        # Rename 'AZ' to 'AvailabilityZone' in df to match allowed_instances structure
        df = df.rename(columns={'AZ': 'AvailabilityZone'})
        
        # Convert allowed_instances list to a DataFrame
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
        
        df = df_merged # Update df to the merged result

    return df

def define_problem():
    return LpProblem("SpotScheduling", LpMinimize)

def define_variables(keys):
    return LpVariable.dicts("Instance", keys, 0, None, LpInteger)

def set_alpha_weighted_objective(prob, x_vars, df, alpha):
    costs = dict(zip(df['InstanceKey'], df['SpotPrice']))
    # Performance: CoreMark * PodAssignable
    perfs = dict(zip(df['InstanceKey'], df['CoreMark'] * df['PodAssignable']))
    
    # Objective: Minimize (1-alpha)*Cost - alpha*Performance
    prob += lpSum([(1-alpha) * costs[k] * x_vars[k] - alpha * perfs[k] * x_vars[k] for k in x_vars])

def add_constraints(prob, x_vars, df, pod_count):
    # Constraint 1: Total Pods >= pod_count
    pod_capacities = dict(zip(df['InstanceKey'], df['PodAssignable']))
    prob += lpSum([pod_capacities[k] * x_vars[k] for k in x_vars]) >= pod_count
    
    # Constraint 2: Max instances per type
    max_instances = dict(zip(df['InstanceKey'], df['Max_Instance']))
    for k in x_vars:
        prob += x_vars[k] <= max_instances[k]

def solve_and_report(prob, x_vars, df, alpha):
    prob.solve(PULP_CBC_CMD(msg=0))
    
    if LpStatus[prob.status] != 'Optimal':
        return None, {}
        
    results = []
    total_cost = 0
    total_perf = 0
    
    for k in x_vars:
        count = x_vars[k].varValue
        if count > 0:
            row = df[df['InstanceKey'] == k].iloc[0]
            cost = row['SpotPrice'] * count
            perf = row['CoreMark'] * row['PodAssignable'] * count
            total_cost += cost
            total_perf += perf
            results.append({
                'Type': row['InstanceType'],
                'AZ': row['AvailabilityZone'],
                'Count': count,
                'TotalPodsOnType': row['PodAssignable'] * count
            })
            
    summary = {
        'Total Cost': total_cost,
        'Total PodWeighted CoreMark': total_perf
    }
    return results, summary

def generate_alpha_solutions(df, pod_count, pod_cpu, pod_mem, alpha_values, allowed_instances=None):
    alpha_solutions = []
    
    for alpha in alpha_values:
        processed_df = load_and_preprocess(df.copy(), pod_cpu, pod_mem, allowed_instances)
        if processed_df.empty:
            continue
        keys = processed_df['InstanceKey'].tolist()
        prob = define_problem()
        x_vars = define_variables(keys)
        
        set_alpha_weighted_objective(prob, x_vars, processed_df, alpha)
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

def getGoldenNodepool(df, pod_count, pod_cpu, pod_mem, allowed_instances=None, left=0.2, right=0.8, tolerance=0.01, max_iterations=20):
    golden_ratio = (np.sqrt(5) - 1) / 2
    x1 = left + (1 - golden_ratio) * (right - left)
    x2 = left + golden_ratio * (right - left)
    
    all_results = []
    
    points1 = generate_alpha_solutions(df, pod_count, pod_cpu, pod_mem, [x1], allowed_instances)
    if points1:
        f1 = points1[0]['performance'] / points1[0]['cost']
        all_results.append(points1[0])
    else:
        f1 = -float('inf')
    
    points2 = generate_alpha_solutions(df, pod_count, pod_cpu, pod_mem, [x2], allowed_instances)
    if points2:
        f2 = points2[0]['performance'] / points2[0]['cost']
        all_results.append(points2[0])
    else:
        f2 = -float('inf')
    
    iteration = 0
    while (right - left) > tolerance and iteration < max_iterations:
        if f1 > f2:
            right = x2
            x2 = x1
            f2 = f1
            x1 = left + (1 - golden_ratio) * (right - left)
            points1 = generate_alpha_solutions(df, pod_count, pod_cpu, pod_mem, [x1], allowed_instances)
            if points1:
                f1 = points1[0]['performance'] / points1[0]['cost']
                all_results.append(points1[0])
            else:
                f1 = -float('inf')
        else:
            left = x1
            x1 = x2
            f1 = f2
            x2 = left + golden_ratio * (right - left)
            points2 = generate_alpha_solutions(df, pod_count, pod_cpu, pod_mem, [x2], allowed_instances)
            if points2:
                f2 = points2[0]['performance'] / points2[0]['cost']
                all_results.append(points2[0])
            else:
                f2 = -float('inf')
        iteration += 1
    
    best_result = None
    best_performance = -float('inf')
    
    for result in all_results:
        actual_pods = sum(r['TotalPodsOnType'] for r in result['results'])
        if actual_pods == 0: continue
        performance_metric = result['performance'] / (result['cost'] * actual_pods)
        
        if performance_metric > best_performance:
            best_result = result
            best_performance = performance_metric
    
    if not best_result:
        return None

    target_instances = []
    az_mapping = fetch_and_cache_az_mapping()
    
    for node in best_result['results']:
        target_instances.append({
            "instance_type": str(node['Type']),
            "availability_zone": str(az_mapping.get(node['AZ'], node['AZ'])),
            "num_instances": int(node['Count'])
        })

    return target_instances

if __name__ == '__main__':
    # Change CWD to /tmp to allow PuLP to write temp files
    os.chdir('/tmp')

    parser = argparse.ArgumentParser()
    parser.add_argument('--pod-count', type=int, required=True)
    parser.add_argument('--pod-cpu', type=float, required=True)
    parser.add_argument('--pod-mem', type=float, required=True)
    parser.add_argument('--region', type=str, default='us-east-1')
    parser.add_argument('--allowed-instances-file', type=str, help='Path to JSON file containing allowed instances')
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

    result = getGoldenNodepool(df, args.pod_count, args.pod_cpu, args.pod_mem, allowed_instances=allowed_instances)
    if result:
        original_stdout.write(json.dumps(result))
        original_stdout.flush()
    else:
        sys.exit(1)
