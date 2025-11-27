## 2025-05-23 수정

import pandas as pd
from pulp import *
import numpy as np
import matplotlib.pyplot as plt
import requests
import json
import pandas as pd
from datetime import datetime
import boto3
import os

def fetch_and_cache_az_mapping(region='us-east-1'):
    ec2 = boto3.client('ec2', region_name=region)
    response = ec2.describe_availability_zones(AllAvailabilityZones=True)
    mapping = {az['ZoneId']: az['ZoneName'] for az in response['AvailabilityZones']}
    with open(f'{region}_az_mapping.json', 'w') as f:
        json.dump(mapping, f)
    return mapping

def load_az_mapping(region='us-east-1'):
    if os.path.exists(f'{region}_az_mapping.json'):
        with open(f'{region}_az_mapping.json', 'r') as f:
            return json.load(f)
    else:
        return fetch_and_cache_az_mapping(region)

def get_aws_spot_prices(target_region='us-east-1', allow_arm=True):
    # 스팟 인스턴스 가격 데이터 URL
    spot_price_url = "https://d26bk4799jlxhe.cloudfront.net/latest_data/latest_aws.json"

    try:
        response = requests.get(spot_price_url)
        response.raise_for_status()  # HTTP 오류 발생 시 예외 발생
        
        # JSON 데이터 파싱
        spot_data = response.json()
        
        # 지정된 리전의 모든 AZ에 대한 데이터 필터링
        spot_prices = [] 
        for item in spot_data:
            instance_type = item.get('InstanceType')
            region = item.get('Region')
            az = item.get('AZ')
            spot_price_value = item.get('SpotPrice')
            t3_value = item.get('T3')
            sps_value = item.get('SPS')
            if_value = item.get('IF')


            # InstanceType이 있고, Region이 target_region인 경우
            if instance_type and region == target_region:
                # SpotPrice가 None이 아닐 때만 float으로 변환, None이면 None 유지
                spot_price_float = float(spot_price_value) if spot_price_value is not None else None
                
                spot_prices.append({
                    'InstanceType': instance_type,
                    'AZ': az, # AZ 정보 추가
                    'SpotPrice': spot_price_float,
                    'T3': t3_value,
                    'SPS': sps_value,
                    'IF': if_value
                })
        
        # 스팟 가격 데이터를 DataFrame으로 변환
        df_spot = pd.DataFrame(spot_prices)
        
        # CoreMark 데이터 읽기
        df_coremark = pd.read_csv('aws_coremark_singlecore.csv')

        # Instance_Type을 기준으로 두 DataFrame 조인
        df_merged = pd.merge(df_spot, df_coremark[['InstanceType', 'CoreMark']], on='InstanceType', how='left')

        df_merged.dropna(subset=['CoreMark'], inplace=True)
        df_merged = df_merged[df_merged['SpotPrice'] > 0]

        # AWS 인스턴스 사양 정보 가져오기
        client = boto3.client('ec2', region_name=target_region)
        instance_types_to_describe = df_merged['InstanceType'].dropna().unique().tolist()
        specs_list = []
        
        # describe_instance_types는 한 번에 최대 100개의 인스턴스 타입을 처리할 수 있습니다.
        chunk_size = 100
        all_specs = [] # 모든 API 호출 결과를 누적할 리스트
        
        if instance_types_to_describe:
            try:
                for i in range(0, len(instance_types_to_describe), chunk_size):
                    chunk = instance_types_to_describe[i:i + chunk_size]
                    print(f"처리 중인 인스턴스 타입 청크: {i // chunk_size + 1} / { (len(instance_types_to_describe) + chunk_size - 1) // chunk_size }")
                    response = client.describe_instance_types(InstanceTypes=chunk)
                    all_specs.extend(response.get('InstanceTypes', [])) # 결과 누적
                
                # 누적된 결과 처리
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
                            'Memory': memory / 1024 # MiB를 GiB로 변환
                        })
                
                df_specs = pd.DataFrame(specs_list)
                df_merged = pd.merge(df_merged, df_specs, on='InstanceType', how='left')

                # 최종 열 순서 지정
                df_merged = df_merged[['InstanceType', 'AZ', 'vCPU', 'Memory', 'T3', 'SPS', 'IF', 'SpotPrice', 'CoreMark']]

            except Exception as e:
                print(f"AWS API 호출 중 오류 발생: {e}")
                return -1
        
        if not allow_arm:
            # ARM 아키텍처 인스턴스 제외 (InstanceType을 '.'을 기준으로 split한 후, split된 문자열 중 첫 번째가 'g'로 끝나는 인스턴스 타입)
            df_merged = df_merged[~df_merged['InstanceType'].str.split('.').str[0].str.contains('g')]

        # 현재 시간을 가져와서 파일명 생성
        current_time = datetime.now()
        filename = f"merged_coremark_spotdata_{current_time.strftime('%y%m%d_%H%M')}.csv"
        
        # CSV 파일로 저장
        df_merged.to_csv(filename, index=False)
        print(f"데이터가 {filename}에 저장되었습니다.")
        
        return filename

    except Exception as e:
        print(f"오류 발생: {e}")
        return -1

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
        "disk_network": ["d", "n"]  # network_disk는 d와 n이 모두 옵션에 포함되어야 함
    }

    if workload_intensity not in option_map or workload_intensity == "default": # workload_intensity == "default" 조건 추가
        # print(f"workload_intensity: {workload_intensity} is not in option_map")
        return df
    # network_disk는 리스트, 나머지는 str로 처리
    current_option_map = option_map[workload_intensity]
    if isinstance(current_option_map, list):
        # network_disk: "d"와 "n"이 모두 InstanceOptions에 포함되어야 함
        def is_target_option(opt_str):
            return all(char_opt in opt_str for char_opt in current_option_map)
    else:
        # network 또는 disk: 해당 옵션 문자가 InstanceOptions에 포함되어야 함
        def is_target_option(opt_str):
            return current_option_map in opt_str

    # df["BaseFamily"] = df["InstanceFamily"].str.extract(r"([a-z]+\d+)") # load_and_preprocess에서 처리하므로 제거
    base_mask = df["InstanceOptions"] == "" # BaseFamily의 옵션은 ""
    base_prices = df[base_mask].set_index("BaseFamily")["OndemandPrice"].to_dict()

    def scale_row(row):
        # OndemandPrice가 없는 경우를 대비하여 row.get 사용
        on_demand_price = row.get("OndemandPrice")
        if on_demand_price is None or pd.isna(on_demand_price): # OndemandPrice가 없거나 NaN이면 스케일링하지 않음
            return row["CoreMark"]

        if is_target_option(row["InstanceOptions"]) and row["BaseFamily"] in base_prices:
            base_price = base_prices[row["BaseFamily"]]
            if pd.notna(base_price) and base_price > 0 and pd.notna(on_demand_price): # NaN 체크 추가
                return row["CoreMark"] * (on_demand_price / base_price)
        return row["CoreMark"]

    df["CoreMark"] = df.apply(scale_row, axis=1)
    return df

# === 1. Data Preprocessing ===
def load_and_preprocess(file_path, pod_cpu, pod_mem,  workload_intensity="default"):
    df = pd.read_csv(file_path)
    if workload_intensity != "default":
        df["InstanceFamily"] = df["InstanceType"].str.split(".").str[0]
        df[["BaseFamily", "InstanceOptions"]] = df["InstanceFamily"].apply(
            lambda x: pd.Series(extract_base_and_option(x))
        )
    df['T3'] = pd.to_numeric(df['T3'], errors='coerce')
    df.dropna(subset=['T3'], inplace=True)
    df['Max_Instance'] = (df['T3'] * 0.4).astype(int)
    df['PodAssignable'] = df.apply(
        lambda row: min(row['vCPU'] // pod_cpu, row['Memory'] // pod_mem), axis=1)
    df = df[df['PodAssignable'] > 0].reset_index(drop=True)
    df['CoreMark'] = pd.to_numeric(df['CoreMark'], errors='coerce')
    df['SpotPrice'] = pd.to_numeric(df['SpotPrice'], errors='coerce')
    df['InstanceKey'] = df['InstanceType'] + '_' + df['AZ']
    
    df = scale_coremark_for_specialized(df, workload_intensity)
    return df

# === 2. Problem Setup ===
def define_problem():
    return LpProblem("Pod_Instance_Selection", LpMinimize)

def define_variables(keys):
    return LpVariable.dicts("x", keys, lowBound=0, cat='Integer')

# === 3. Alpha Weighted Objective Function ===
def set_alpha_weighted_objective(prob, x_vars, df, alpha, scale="min"):
    """
    alpha: 비용과 성능 사이의 가중치 (0~1)
    alpha가 0에 가까울수록 비용 최적화에 중점
    alpha가 1에 가까울수록 성능 최적화에 중점
    scale: 스케일링 방식 ("min", "log", "min-max")
    """
    keys = df['InstanceKey'].tolist()
    spot = dict(zip(keys, df['SpotPrice']))
    perf = dict(zip(keys, df['CoreMark']))
    pod_assign = dict(zip(keys, df['PodAssignable']))

    if scale == "min":
        # min 기반 스케일링
        min_spot = min(spot.values())
        min_perf = min([p * pod_assign[k] for k, p in perf.items()])
        
        normalized_cost = lpSum([(spot[k] / min_spot) * x_vars[k] for k in keys])
        normalized_perf = lpSum([(perf[k] * pod_assign[k] / min_perf) * x_vars[k] for k in keys])
    
    elif scale == "log":
        # log 기반 스케일링
        log_spot = {k: np.log1p(v) for k, v in spot.items()}
        log_perf = {k: np.log1p(p * pod_assign[k]) for k, p in perf.items()}
        
        min_log_spot = min(log_spot.values())
        min_log_perf = min(log_perf.values())
        
        normalized_cost = lpSum([(log_spot[k] / min_log_spot) * x_vars[k] for k in keys])
        normalized_perf = lpSum([(log_perf[k] / min_log_perf) * x_vars[k] for k in keys])
    
    elif scale == "min-max":
        # min-max 기반 스케일링
        min_spot = min(spot.values())
        max_spot = max(spot.values())
        min_perf = min([p * pod_assign[k] for k, p in perf.items()])
        max_perf = max([p * pod_assign[k] for k, p in perf.items()])
        
        normalized_cost = lpSum([((spot[k] - min_spot) / (max_spot - min_spot)) * x_vars[k] for k in keys])
        normalized_perf = lpSum([((perf[k] * pod_assign[k] - min_perf) / (max_perf - min_perf)) * x_vars[k] for k in keys])
    
    # 가중치가 적용된 목적함수
    prob += (1 - alpha) * normalized_cost - alpha * normalized_perf, "Alpha_Weighted_Objective"

# === 4. Constraints ===
def add_constraints(prob, x_vars, df, pod_count):
    keys = df['InstanceKey'].tolist()
    pod_assign = dict(zip(keys, df['PodAssignable']))
    max_inst = dict(zip(keys, df['Max_Instance']))

    prob += lpSum([pod_assign[k] * x_vars[k] for k in keys]) >= pod_count, "Min_Pod_Requirement"

    for k in keys:
        prob += x_vars[k] <= max_inst[k], f"Max_Instance_Limit_{k}"

# === 5. Solver and Result ===
def solve_and_report(prob, x_vars, df, alpha, verbose=False):
    # CBC 솔버 출력 끄기
    status = prob.solve(PULP_CBC_CMD(msg=False))
    if verbose:
        print(f"\n=== Alpha = {alpha:.3f} ===")
        print(f"Status: {LpStatus[status]}")
    if status != 1:
        return [], {}

    keys = df.set_index('InstanceKey').to_dict('index')
    results = []
    total_cost = 0
    total_pod_weighted_coremark = 0
    total_pods_assigned_by_model = 0

    if verbose:
        print("\n인스턴스 조합 상세 정보:")
        print("-" * 100)
        print(f"{'인스턴스 타입':<20} {'AZ':<10} {'개수':<8} {'Pod/인스턴스':<12} {'총 Pod 수':<10} {'비용':<12} {'CoreMark':<10}")
        print("-" * 100)

    for k, var in x_vars.items():
        if var.varValue > 0:
            info = keys[k]
            count = int(var.varValue)
            pods_on_this_type = info['PodAssignable'] * count
            cost = info['SpotPrice'] * count
            pod_weighted_coremark = info['CoreMark'] * pods_on_this_type
            results.append({
                'InstanceKey': k,
                'Type': info['InstanceType'],
                'AZ': info['AZ'],
                'Count': count,
                'TotalPodsOnType': pods_on_this_type,
                'Cost': cost,
                'PodWeightedCoreMark': pod_weighted_coremark,
                'T3': info['T3']
            })
            
            if verbose:
                print(f"{info['InstanceType']:<20} {info['AZ']:<10} {count:<8} {info['PodAssignable']:<12} {pods_on_this_type:<10} {cost:<12.2f} {info['CoreMark']:<10.2f}")
            
            total_cost += cost
            total_pod_weighted_coremark += pod_weighted_coremark
            total_pods_assigned_by_model += pods_on_this_type

    if verbose:
        print("-" * 100)
        print(f"총 Pod 수: {total_pods_assigned_by_model}")
        print(f"총 비용: {total_cost:.2f}")
        print(f"총 CoreMark: {total_pod_weighted_coremark:.2f}")
        print("-" * 100)

    summary = {
        'Total Cost': total_cost,
        'Total PodWeighted CoreMark': total_pod_weighted_coremark,
        'Total Pods Assigned': total_pods_assigned_by_model
    }

    return results, summary

# === 6. Alpha Solutions Generation ===
def generate_alpha_solutions(file_path, pod_count, pod_cpu, pod_mem, alpha_values, verbose=False, workload_intensity="default", scale="min"):
    """
    alpha_values: alpha 값 리스트
    verbose: 상세 출력 여부
    scale: 스케일링 방식 ("min", "log", "min-max")
    """
    alpha_solutions = []
    
    for alpha in alpha_values:
        df = load_and_preprocess(file_path, pod_cpu, pod_mem, workload_intensity)
        keys = df['InstanceKey'].tolist()
        prob = define_problem()
        x_vars = define_variables(keys)
        
        set_alpha_weighted_objective(prob, x_vars, df, alpha, scale=scale)
        add_constraints(prob, x_vars, df, pod_count)
        
        results, summary = solve_and_report(prob, x_vars, df, alpha, verbose=verbose)
        alpha_solutions.append({
            'pods': pod_count,
            'cpu': pod_cpu,
            'mem': pod_mem,
            'alpha': alpha,
            'cost': summary['Total Cost'],
            'performance': summary['Total PodWeighted CoreMark'],
            'results': results
        })
    
    return alpha_solutions

# === 7. Visualization ===
def visualize_alpha_solutions(alpha_solutions, fixed_alpha_points=None, optimal_alpha=None, verbose=False, pod_count=400, pod_cpu=2, pod_mem=8):
    optimal_point = next((point for point in alpha_solutions if abs(point['alpha'] - optimal_alpha) < 1e-6), None)
    
    # 2. Alpha-Performance, Alpha-Pod Count, Alpha-Cost를 함께 보여주는 그래프
    plt.figure(figsize=(12, 8))
    if fixed_alpha_points:
        # alpha 값을 정순으로 정렬
        sorted_points = sorted(fixed_alpha_points, key=lambda x: x['alpha'])
        alphas = [point['alpha'] for point in sorted_points]
        performances = [point['performance'] for point in sorted_points]
        pod_counts = [sum(result['TotalPodsOnType'] for result in point['results']) for point in sorted_points]
        costs = [point['cost'] for point in sorted_points]
        
        # Pod 1개당 performance 계산
        performance_metric = [perf / pod_count for perf, pod_count in zip(performances, pod_counts)]
        # Cost 당 performance 계산
        performance_metric = [perf / cost for perf, cost in zip(performance_metric, costs)]
        
        # 성능 그래프 (왼쪽 y축)
        ax1 = plt.gca()
        line1 = ax1.plot(alphas, performances, 'b-', label='Total Performance')
        ax1.scatter(alphas, performances, c='blue', s=50)
        ax1.set_xlabel('Alpha (Performance Weight)')
        ax1.set_ylabel('Total Performance (PodWeighted CoreMark)', color='b')
        ax1.tick_params(axis='y', labelcolor='b')
        
        # Pod 개수 그래프 (오른쪽 y축)
        ax2 = ax1.twinx()
        line2 = ax2.plot(alphas, pod_counts, 'g-', label='Pod Count')
        ax2.scatter(alphas, pod_counts, c='green', s=50)
        ax2.set_ylabel('Total Pod Count', color='g')
        ax2.tick_params(axis='y', labelcolor='g')
        podcount_min = min(pod_counts)
        ax2.set_ylim(podcount_min, podcount_min*2)  # Cost y축 범위 설정
        
        # 비용 그래프 (오른쪽 y축)
        ax3 = ax1.twinx()
        line3 = ax3.plot(alphas, costs, 'r-', label='Cost')
        ax3.scatter(alphas, costs, c='red', s=50)
        ax3.set_ylabel('Total Cost ($)', color='r')
        ax3.tick_params(axis='y', labelcolor='r')
        min_cost = min(costs)
        ax3.set_ylim(min_cost, min_cost * 2)  # Cost y축 범위를 최소 비용부터 최소 비용의 2배까지 설정
        
        # Cost 당 performance 그래프 (오른쪽 y축)
        ax4 = ax1.twinx()
        line4 = ax4.plot(alphas, performance_metric, 'c-', label='Performance/(Cost*Pods_assignable)')
        ax4.scatter(alphas, performance_metric, c='cyan', s=50)
        ax4.set_ylabel('Performance/(Cost*Pods_assignable)', color='c')
        ax4.tick_params(axis='y', labelcolor='c')
        
        # 오른쪽 y축 위치 조정
        ax3.spines['right'].set_position(('outward', 60))
        ax4.spines['right'].set_position(('outward', 120))
        

        if optimal_point:
            total_pods = sum(result['TotalPodsOnType'] for result in optimal_point['results'])
            perf_per_cost_optimal = optimal_point['performance'] / (optimal_point['cost'] * total_pods)
            
            ax1.scatter(optimal_alpha, optimal_point['performance'], 
                       c='blue', marker='*', s=300, label=f'Optimal Alpha ({optimal_alpha:.3f})')
            ax2.scatter(optimal_alpha, total_pods, 
                       c='green', marker='*', s=300)
            ax3.scatter(optimal_alpha, optimal_point['cost'],
                       c='red', marker='*', s=300)
            ax4.scatter(optimal_alpha, perf_per_cost_optimal,
                       c='cyan', marker='*', s=300)
    
    # 범례 설정
    lines = line1 + line2 + line3 + line4
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper right')
    
    plt.title('Alpha vs Performance, Pod Count, Cost, and Efficiency Metrics')
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(f'alpha_performance.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    return optimal_point

# === 8. Golden Section Nodepool Generator ===
def getGoldenNodepool(file_path, pod_count, pod_cpu, pod_mem, workload_intensity="default", left=0.0, right=1, tolerance=0.01, max_iterations=20, verbose=False, scale="min", region="us-east-1"):
    """
    황금 분할 탐색을 사용하여 최적의 alpha 값을 찾고, 해당 alpha 값에 대한 노드풀 구성을 반환합니다.
    
    Args:
        file_path: 데이터 파일 경로
        pod_count: 파드 수
        pod_cpu: 파드당 CPU
        pod_mem: 파드당 메모리
        left: 탐색 범위의 왼쪽 경계
        right: 탐색 범위의 오른쪽 경계
        tolerance: 허용 오차
        max_iterations: 최대 반복 횟수
        verbose: 상세 출력 여부
        
    Returns:
        최적의 alpha 값과 해당 노드풀 구성 정보를 포함한 딕셔너리
    """
    if verbose:
        print("\n=== Testing getGoldenNodepool ===")
        print(f"Pod Count: {pod_count}, CPU: {pod_cpu}, Memory: {pod_mem}")
    
    # 황금비
    golden_ratio = (np.sqrt(5) - 1) / 2
    
    # 초기 구간 설정
    x1 = left + (1 - golden_ratio) * (right - left)
    x2 = left + golden_ratio * (right - left)
    
    # 탐색된 alpha 값들과 결과를 저장할 리스트
    explored_alphas = []
    explored_podcount = []
    all_results = []
    
    # 초기 함수 값 계산
    alpha_values = [x1]
    points1 = generate_alpha_solutions(file_path, pod_count, pod_cpu, pod_mem, alpha_values, verbose=verbose, workload_intensity=workload_intensity, scale=scale)
    explored_alphas.append(x1)
    
    if not points1:
        f1 = -float('inf')
        explored_podcount.append(0)
    else:
        f1 = points1[0]['performance'] / points1[0]['cost']
        all_results.append(points1[0])
        explored_podcount.append(sum(result['TotalPodsOnType'] for result in points1[0]['results']))
    
    alpha_values = [x2]
    points2 = generate_alpha_solutions(file_path, pod_count, pod_cpu, pod_mem, alpha_values, verbose=verbose, workload_intensity=workload_intensity, scale=scale)
    explored_alphas.append(x2)
    
    if not points2:
        f2 = -float('inf')
        explored_podcount.append(0)
    else:
        f2 = points2[0]['performance'] / points2[0]['cost']
        all_results.append(points2[0])
        explored_podcount.append(sum(result['TotalPodsOnType'] for result in points2[0]['results']))
    
    # 최적의 alpha 값과 성능 지표
    best_alpha = None
    best_perf_per_cost = -1
    best_cost = None
    best_performance = None
    best_actual_pods = None
    best_excess_pods = None
    best_results = None
    
    iteration = 0
    while (right - left) > tolerance and iteration < max_iterations:
        if f1 > f2:
            # x1이 더 좋은 경우
            right = x2
            x2 = x1
            f2 = f1
            x1 = left + (1 - golden_ratio) * (right - left)
            
            alpha_values = [x1]
            points1 = generate_alpha_solutions(file_path, pod_count, pod_cpu, pod_mem, alpha_values, verbose=verbose, workload_intensity=workload_intensity, scale=scale)
            explored_alphas.append(x1)
            
            if not points1:
                f1 = -float('inf')
                explored_podcount.append(0)
            else:
                f1 = points1[0]['performance'] / points1[0]['cost']
                all_results.append(points1[0])
                explored_podcount.append(sum(result['TotalPodsOnType'] for result in points1[0]['results']))
                
                # 현재 성능이 더 좋은 경우 업데이트
                if f1 > best_perf_per_cost:
                    best_perf_per_cost = f1
                    best_alpha = x1
                    best_cost = points1[0]['cost']
                    best_performance = points1[0]['performance']
                    best_results = points1[0]['results']
                    best_actual_pods = sum(result['TotalPodsOnType'] for result in points1[0]['results'])
                    best_excess_pods = best_actual_pods - pod_count
        else:
            # x2가 더 좋은 경우
            left = x1
            x1 = x2
            f1 = f2
            x2 = left + golden_ratio * (right - left)
            
            alpha_values = [x2]
            points2 = generate_alpha_solutions(file_path, pod_count, pod_cpu, pod_mem, alpha_values, verbose=verbose, workload_intensity=workload_intensity, scale=scale)
            explored_alphas.append(x2)
            
            if not points2:
                f2 = -float('inf')
                explored_podcount.append(0)
            else:
                f2 = points2[0]['performance'] / points2[0]['cost']
                all_results.append(points2[0])
                explored_podcount.append(sum(result['TotalPodsOnType'] for result in points2[0]['results']))
                
                # 현재 성능이 더 좋은 경우 업데이트
                if f2 > best_perf_per_cost:
                    best_perf_per_cost = f2
                    best_alpha = x2
                    best_cost = points2[0]['cost']
                    best_performance = points2[0]['performance']
                    best_results = points2[0]['results']
                    best_actual_pods = sum(result['TotalPodsOnType'] for result in points2[0]['results'])
                    best_excess_pods = best_actual_pods - pod_count
        
        iteration += 1
    
    # all_results를 순회하면서 최적의 결과 찾기
    best_result = None
    best_performance = -float('inf')
    
    # 새로운 성능 지표를 사용한 코드
    for result in all_results:
        actual_pods = sum(r['TotalPodsOnType'] for r in result['results'])
        # 새로운 성능 지표: 성능 / (비용 * 실제 파드 수)
        performance_metric = result['performance'] / (result['cost'] * actual_pods)
        
        if performance_metric > best_performance:
            best_result = result
            best_performance = performance_metric
    
    if best_result:
        best_alpha = best_result['alpha']
        best_cost = best_result['cost']
        best_performance = best_result['performance']
        best_results = best_result['results']
        best_actual_pods = sum(result['TotalPodsOnType'] for result in best_results)
        best_excess_pods = best_actual_pods - pod_count
        best_perf_per_cost = best_performance / best_cost
    
    if verbose:
        print("\n=== Best Nodepool Configuration ===")
        print(f"Optimal Alpha: {best_alpha:.3f}")
        print(f"Total Cost per Hour: ${best_cost:.2f}")
        print(f"Total Performance: {best_performance:.2f}")
        print(f"Performance per Cost: {best_perf_per_cost:.2f}")
        print(f"Actual Pods: {best_actual_pods}")
        print(f"Excess Pods: {best_excess_pods}")
        print(f"Total Iterations: {iteration}")

    # 결과 가공
    target_instances = []
    az_mapping = load_az_mapping(region)
    for node in best_results:
        target_instances.append({
            "instance_type": str(node['Type']),
            "availability_zone": str(az_mapping.get(node['AZ'])),
            "num_instances": int(node['Count']),
            "T3": node['T3']
        })

    # 결과 출력
    if verbose:
        print("\n=== Nodepool Configuration ===")
        print("[\n    {")
        for i, instance in enumerate(target_instances):
            print(f'        "instance_type": "{instance["instance_type"]}",')
            print(f'        "availability_zone": "{instance["availability_zone"]}",')
            print(f'        "num_instances": {instance["num_instances"]}')
            if i < len(target_instances) - 1:
                print("    },")
                print("    {")
            else:
                print("    }")
        print("]")
    
    return {
        'pods': pod_count,
        'cpu': pod_cpu,
        'mem': pod_mem,
        'alpha': best_alpha,
        'cost': best_cost,
        'performance': best_performance,
        'perf_per_cost': best_perf_per_cost,
        'actual_pods': best_actual_pods,
        'excess_pods': best_excess_pods,
        'iterations': iteration,
        'explored_alphas': explored_alphas,
        'explored_podcount': explored_podcount,
        'nodepool_config': target_instances,
        'workload_intensity': workload_intensity
    }

def getSpotVerseNodepool(filepath, pod_count, pod_cpu, pod_mem, threshold=6, unit='node', verbose=False):
    # 데이터프레임 로드 및 전처리
    df = load_and_preprocess(filepath, pod_cpu, pod_mem)
    df['T'] = df['SPS'] + df['IF']
    df_filtered = df[df['T'] >= threshold].copy()
    df_filtered['PricePerPod'] = df_filtered['SpotPrice']/df_filtered['PodAssignable']

    if unit == 'node':
        df_sorted = df_filtered.sort_values(by='SpotPrice')
    elif unit == 'pod':
        df_sorted = df_filtered.sort_values(by='PricePerPod')
    
    # pod_count를 가장 가격이 싼 값의 PodAssignable 값으로 나눈 값을 정수로 올림
    cheapest_pod_assignable = df_sorted.iloc[0]['PodAssignable']
    required_instances = np.ceil(pod_count / cheapest_pod_assignable).astype(int)
    
    # 인스턴스 정보 가공
    target_instance = df_sorted.iloc[0]
    az_mapping = load_az_mapping()
    instance_info = {
        "instance_type": str(target_instance['InstanceType']),
        "availability_zone": str(az_mapping.get(target_instance['AZ'])),
        "num_instances": required_instances,
        "T3": target_instance['T3']
    }

    # num_instances 만큼 노드를 사용했을 때 생성되는 파드 수와 남는 파드 수 계산
    actual_pods = required_instances * cheapest_pod_assignable
    excess_pods = actual_pods - pod_count

    # Total Cost per Hour 및 Total Performance 계산
    total_cost_per_hour = required_instances * target_instance['SpotPrice']
    total_performance = actual_pods * target_instance['CoreMark']

    efficiency = total_performance / (total_cost_per_hour * actual_pods)

    if verbose:
        # 결과 출력
        print("\n=== SpotVerse Nodepool Configuration ===")
        print("[\n    {")
        print(f'        "instance_type": "{instance_info["instance_type"]}",')
        print(f'        "availability_zone": "{instance_info["availability_zone"]}",')
        print(f'        "num_instances": {instance_info["num_instances"]},')
        print(f'        "actual_pods": {actual_pods},')
        print(f'        "excess_pods": {excess_pods},')
        print(f'        "total_cost_per_hour": {total_cost_per_hour:.2f},')
        print(f'        "total_cost_per_pod": {total_cost_per_hour/actual_pods:4f},')
        print(f'        "total_performance": {total_performance:.2f},')
        print(f'        "nodes_used": {required_instances}')
        print(f'        "efficiency": {efficiency:.2f}')
        print("    }\n]")

    # 반환 값에 추가
    instance_info.update({
        "pods": pod_count,
        "cpu": pod_cpu,
        "mem": pod_mem,
        "actual_pods": actual_pods,
        "excess_pods": excess_pods,
        "cost": total_cost_per_hour,
        "performance": total_performance,
        "total_cost_per_pod": total_cost_per_hour/actual_pods,
        "nodes_used": required_instances,
        "efficiency": efficiency,
        "T3": target_instance['T3']
    })

    return instance_info

# === 9. Main Runner ===
if __name__ == '__main__':
    # FILE_PATH = get_aws_spot_prices(target_region='us-east-1', allow_arm=False)
    # FILE_PATH = "merged_coremark_spotdata_250515_2032.csv"
    FILE_PATH = "/Users/taeyoon/Desktop/middleware2025/cmp/simulation/spotdata/050103.csv"
    POD_COUNT = 200
    POD_CPU = 1
    POD_MEM = 4
    WORKLOAD_INTENSITY = "default"

    result = getGoldenNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM, WORKLOAD_INTENSITY, verbose=False)
    print(result['nodepool_config'])
    result = getGoldenNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM, "network", verbose=False)
    print(result['nodepool_config'])
    result = getGoldenNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM, "disk", verbose=False)
    print(result['nodepool_config'])
    result = getGoldenNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM, "disk_network", verbose=False)
    print(result['nodepool_config'])
    
    # getGoldenNodepool 함수 테스트 (verbose=True로 설정하여 상세 출력)
    # result = getGoldenNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM, verbose=True)
    # result2 = getSpotVerseNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM//2, threshold=6, unit='node')
    # result = getSpotVerseNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM, threshold=6, unit='node')
    # result = getSpotVerseNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM, threshold=4, unit='node')
    
    # result2 = getSpotVerseNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM//2, threshold=6, unit='pod')
    # result = getSpotVerseNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM, threshold=6, unit='pod')
    # result = getSpotVerseNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM, threshold=4, unit='pod')
    
    # result = getSpotVerseNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM, threshold=5)
    # result2 = getSpotVerseNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM, threshold=4)