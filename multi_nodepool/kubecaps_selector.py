import pandas as pd
from pulp import *
import numpy as np
import matplotlib.pyplot as plt
import requests
import json
import pandas as pd
from datetime import datetime
import boto3


azdict = {'use2-az1': 'us-east-2a', 'use2-az2': 'us-east-2b', 'use2-az3': 'us-east-2c', 'aps1-az1': 'ap-south-1a', 'aps1-az3': 'ap-south-1b', 'aps1-az2': 'ap-south-1c', 'usw2-az1': 'us-west-2a', 'usw2-az2': 'us-west-2b', 'usw2-az3': 'us-west-2c', 'usw2-az4': 'us-west-2d', 'usw2-wl1-den-wlz1': 'us-west-2-wl1-den-wlz-1', 'usw2-wl1-las-wlz1': 'us-west-2-wl1-las-wlz-1', 'usw2-wl1-phx-wlz1': 'us-west-2-wl1-phx-wlz-1', 'usw2-wl1-sea-wlz1': 'us-west-2-wl1-sea-wlz-1', 'usw2-wl1-sfo-wlz1': 'us-west-2-wl1-sfo-wlz-1', 'apne3-az3': 'ap-northeast-3a', 'apne3-az1': 'ap-northeast-3b', 'apne3-az2': 'ap-northeast-3c', 'apse1-az1': 'ap-southeast-1a', 'apse1-az2': 'ap-southeast-1b', 'apse1-az3': 'ap-southeast-1c', 'apne2-az1': 'ap-northeast-2a', 'apne2-az2': 'ap-northeast-2b', 'apne2-az3': 'ap-northeast-2c', 'apne2-az4': 'ap-northeast-2d', 'apne2-wl1-cjj-wlz1': 'ap-northeast-2-wl1-cjj-wlz-1', 'cac1-az1': 'ca-central-1a', 'cac1-az2': 'ca-central-1b', 'cac1-az4': 'ca-central-1d', 'euc1-az2': 'eu-central-1a', 'euc1-az3': 'eu-central-1b', 'euc1-az1': 'eu-central-1c', 'euw2-az2': 'eu-west-2a', 'euw2-az3': 'eu-west-2b', 'euw2-az1': 'eu-west-2c', 'euw3-az1': 'eu-west-3a', 'euw3-az2': 'eu-west-3b', 'euw3-az3': 'eu-west-3c', 'eun1-az1': 'eu-north-1a', 'eun1-az2': 'eu-north-1b', 'eun1-az3': 'eu-north-1c', 'sae1-az1': 'sa-east-1a', 'sae1-az2': 'sa-east-1b', 'sae1-az3': 'sa-east-1c', 'apne1-az4': 'ap-northeast-1a', 'apne1-az1': 'ap-northeast-1c', 'apne1-az2': 'ap-northeast-1d', 'apse2-az3': 'ap-southeast-2a', 'apse2-az1': 'ap-southeast-2b', 'apse2-az2': 'ap-southeast-2c', 'use1-az4': 'us-east-1a', 'use1-az6': 'us-east-1b', 'use1-az1': 'us-east-1c', 'use1-az2': 'us-east-1d', 'use1-az3': 'us-east-1e', 'use1-az5': 'us-east-1f', 'usw1-az3': 'us-west-1b', 'usw1-az1': 'us-west-1c', 'euw1-az3': 'eu-west-1a', 'euw1-az1': 'eu-west-1b', 'euw1-az2': 'eu-west-1c'}

CACHE_FILE = 'az_mapping.json'

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
    spot_price_url = "https://spotlake.s3.us-west-2.amazonaws.com/latest_data/latest_aws.json"

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

            # InstanceType이 있고, Region이 target_region인 경우
            if instance_type and region == target_region:
                # SpotPrice가 None이 아닐 때만 float으로 변환, None이면 None 유지
                spot_price_float = float(spot_price_value) if spot_price_value is not None else None
                
                spot_prices.append({
                    'InstanceType': instance_type,
                    'AZ': az, # AZ 정보 추가
                    'SpotPrice': spot_price_float,
                    'T3': t3_value
                })
        
        # 스팟 가격 데이터를 DataFrame으로 변환
        df_spot = pd.DataFrame(spot_prices)
        
        # CoreMark 데이터 읽기
        df_coremark = pd.read_csv('./multi_nodepool/aws_coremark_singlecore.csv')

        # Instance_Type을 기준으로 두 DataFrame 조인
        df_merged = pd.merge(df_spot, df_coremark[['InstanceType', 'CoreMark']], on='InstanceType', how='left')

        df_merged.dropna(subset=['CoreMark'], inplace=True)

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
                df_merged = df_merged[['InstanceType', 'AZ', 'vCPU', 'Memory', 'T3', 'SpotPrice', 'CoreMark']]

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


# === 1. Data Preprocessing ===
def load_and_preprocess(file_path, pod_cpu, pod_mem):
    df = pd.read_csv(file_path)
    df['T3'] = pd.to_numeric(df['T3'], errors='coerce')
    df.dropna(subset=['T3'], inplace=True)
    df['Max_Instance'] = (df['T3'] * 0.1).astype(int)
    df['PodAssignable'] = df.apply(
        lambda row: min(row['vCPU'] // pod_cpu, row['Memory'] // pod_mem), axis=1)
    df = df[df['PodAssignable'] > 0].reset_index(drop=True)
    df['CoreMark'] = pd.to_numeric(df['CoreMark'], errors='coerce')
    df['SpotPrice'] = pd.to_numeric(df['SpotPrice'], errors='coerce')
    df['InstanceKey'] = df['InstanceType'] + '_' + df['AZ']
    return df

# === 2. Problem Setup ===
def define_problem():
    return LpProblem("Pod_Instance_Selection", LpMinimize)

def define_variables(keys):
    return LpVariable.dicts("x", keys, lowBound=0, cat='Integer')

# === 3. Alpha Weighted Objective Function ===
def set_alpha_weighted_objective(prob, x_vars, df, alpha):
    """
    alpha: 비용과 성능 사이의 가중치 (0~1)
    alpha가 0에 가까울수록 성능 최적화에 중점
    alpha가 1에 가까울수록 비용 최적화에 중점
    """
    keys = df['InstanceKey'].tolist()
    spot = dict(zip(keys, df['SpotPrice']))
    perf = dict(zip(keys, df['CoreMark']))
    pod_assign = dict(zip(keys, df['PodAssignable']))

    # min 기반 스케일링
    min_spot = min(spot.values())
    min_perf = min([p * pod_assign[k] for k, p in perf.items()])
    
    # 정규화된 목적함수
    normalized_cost = lpSum([(spot[k] / min_spot) * x_vars[k] for k in keys])
    normalized_perf = lpSum([(perf[k] * pod_assign[k] / min_perf) * x_vars[k] for k in keys])
    
    # 가중치가 적용된 목적함수
    prob += alpha * normalized_cost - (1 - alpha) * normalized_perf, "Alpha_Weighted_Objective"

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
                'PodWeightedCoreMark': pod_weighted_coremark
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
def generate_alpha_solutions(file_path, pod_count, pod_cpu, pod_mem, alpha_values, verbose=False):
    """
    alpha_values: alpha 값 리스트
    verbose: 상세 출력 여부
    """
    alpha_solutions = []
    
    for alpha in alpha_values:
        if verbose or abs(alpha - round(alpha * 10) / 10) < 0.001:  # 소수점 첫째자리까지 일치하는지 확인
            print(f"\nCalculating for alpha = {alpha}")
        df = load_and_preprocess(file_path, pod_cpu, pod_mem)
        keys = df['InstanceKey'].tolist()
        prob = define_problem()
        x_vars = define_variables(keys)
        
        set_alpha_weighted_objective(prob, x_vars, df, alpha)
        add_constraints(prob, x_vars, df, pod_count)
        
        results, summary = solve_and_report(prob, x_vars, df, alpha, verbose=verbose)
        alpha_solutions.append({
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
        # alpha 값을 역순으로 정렬
        sorted_points = sorted(fixed_alpha_points, key=lambda x: x['alpha'], reverse=True)
        alphas = [point['alpha'] for point in sorted_points]
        performances = [point['performance'] for point in sorted_points]
        pod_counts = [sum(result['TotalPodsOnType'] for result in point['results']) for point in sorted_points]
        costs = [point['cost'] for point in sorted_points]
        
        # Pod 1개당 performance 계산
        perf_per_pod = [perf / pod_count for perf, pod_count in zip(performances, pod_counts)]
        # Cost 당 performance 계산
        perf_per_cost = [perf / cost for perf, cost in zip(performances, costs)]
        
        # 성능 그래프 (왼쪽 y축)
        ax1 = plt.gca()
        line1 = ax1.plot(alphas, performances, 'b-', label='Total Performance')
        ax1.scatter(alphas, performances, c='blue', s=50)
        ax1.set_xlabel('Alpha (Cost Weight)')
        ax1.set_ylabel('Total Performance (PodWeighted CoreMark)', color='b')
        ax1.tick_params(axis='y', labelcolor='b')
        
        # x축 반전
        ax1.invert_xaxis()
        
        # Pod 개수 그래프 (오른쪽 y축)
        ax2 = ax1.twinx()
        line2 = ax2.plot(alphas, pod_counts, 'g-', label='Pod Count')
        ax2.scatter(alphas, pod_counts, c='green', s=50)
        ax2.set_ylabel('Total Pod Count', color='g')
        ax2.tick_params(axis='y', labelcolor='g')
        
        # 비용 그래프 (오른쪽 y축)
        ax3 = ax1.twinx()
        line3 = ax3.plot(alphas, costs, 'r-', label='Cost')
        ax3.scatter(alphas, costs, c='red', s=50)
        ax3.set_ylabel('Total Cost ($)', color='r')
        ax3.tick_params(axis='y', labelcolor='r')
        ax3.set_ylim(1, 20)  # Cost y축 범위 설정
        
        # Pod 1개당 performance 그래프 (오른쪽 y축)
        ax4 = ax1.twinx()
        line4 = ax4.plot(alphas, perf_per_pod, 'm-', label='Performance per Pod')
        ax4.scatter(alphas, perf_per_pod, c='magenta', s=50)
        ax4.set_ylabel('Performance per Pod', color='m')
        ax4.tick_params(axis='y', labelcolor='m')
        
        # Cost 당 performance 그래프 (오른쪽 y축)
        ax5 = ax1.twinx()
        line5 = ax5.plot(alphas, perf_per_cost, 'c-', label='Performance per Cost')
        ax5.scatter(alphas, perf_per_cost, c='cyan', s=50)
        ax5.set_ylabel('Performance per Cost', color='c')
        ax5.tick_params(axis='y', labelcolor='c')
        
        # 오른쪽 y축 위치 조정
        ax3.spines['right'].set_position(('outward', 60))
        ax4.spines['right'].set_position(('outward', 120))
        ax5.spines['right'].set_position(('outward', 180))
        
        # 최적 alpha 점 표시 (각각의 색상으로)
        if optimal_point:
            total_pods = sum(result['TotalPodsOnType'] for result in optimal_point['results'])
            perf_per_pod_optimal = optimal_point['performance'] / total_pods
            perf_per_cost_optimal = optimal_point['performance'] / optimal_point['cost']
            
            ax1.scatter(optimal_alpha, optimal_point['performance'], 
                       c='blue', marker='*', s=300, label=f'Optimal Alpha ({optimal_alpha:.3f})')
            ax2.scatter(optimal_alpha, total_pods, 
                       c='green', marker='*', s=300)
            ax3.scatter(optimal_alpha, optimal_point['cost'],
                       c='red', marker='*', s=300)
            ax4.scatter(optimal_alpha, perf_per_pod_optimal,
                       c='magenta', marker='*', s=300)
            ax5.scatter(optimal_alpha, perf_per_cost_optimal,
                       c='cyan', marker='*', s=300)
    
    # 범례 설정
    lines = line1 + line2 + line3 + line4 + line5
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper right')
    
    plt.title('Alpha vs Performance, Pod Count, Cost, and Efficiency Metrics')
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(f'alpha_performance.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    return optimal_point

# === 8. Golden Section Nodepool Generator ===
def getGoldenNodepool(file_path, pod_count, pod_cpu, pod_mem, left=0.0, right=1.0, tolerance=0.01, max_iterations=20, verbose=False, pod_over_limit=0):
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
        pod_over_limit: 허용 가능한 파드 수 초과 비율 (기본값: 0.05)
        
    Returns:
        최적의 alpha 값과 해당 노드풀 구성 정보를 포함한 딕셔너리
    """
    if verbose:
        print("\n=== Testing getGoldenNodepool ===")
        print(f"Pod Count: {pod_count}, CPU: {pod_cpu}, Memory: {pod_mem}")
        print(f"Pod Over Limit: {pod_over_limit}")
    
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
    points1 = generate_alpha_solutions(file_path, pod_count, pod_cpu, pod_mem, alpha_values, verbose=verbose)
    explored_alphas.append(x1)
    
    if not points1:
        f1 = -float('inf')
        explored_podcount.append(0)
    else:
        f1 = points1[0]['performance'] / points1[0]['cost']
        all_results.append(points1[0])
        explored_podcount.append(sum(result['TotalPodsOnType'] for result in points1[0]['results']))
    
    alpha_values = [x2]
    points2 = generate_alpha_solutions(file_path, pod_count, pod_cpu, pod_mem, alpha_values, verbose=verbose)
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
            points1 = generate_alpha_solutions(file_path, pod_count, pod_cpu, pod_mem, alpha_values, verbose=verbose)
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
            points2 = generate_alpha_solutions(file_path, pod_count, pod_cpu, pod_mem, alpha_values, verbose=verbose)
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
    
    # 파드 수 제한을 고려하여 최적의 결과 선택
    max_allowed_pods = pod_count * (1 + pod_over_limit)
    
    # all_results를 순회하면서 최적의 결과 찾기
    best_result = None
    best_performance = -float('inf')
    
    for result in all_results:
        actual_pods = sum(r['TotalPodsOnType'] for r in result['results'])
        if actual_pods <= max_allowed_pods and result['performance'] > best_performance:
            best_result = result
            best_performance = result['performance']
    
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
    az_mapping = load_az_mapping()
    for node in best_results:
        target_instances.append({
            "instance_type": str(node['Type']),
            "availability_zone": str(az_mapping.get(node['AZ'])),
            "num_instances": int(node['Count'])
        })

    # 결과 출력
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
        'alpha': best_alpha,
        'cost': best_cost,
        'performance': best_performance,
        'perf_per_cost': best_perf_per_cost,
        'actual_pods': best_actual_pods,
        'excess_pods': best_excess_pods,
        'iterations': iteration,
        'explored_alphas': explored_alphas,
        'explored_podcount': explored_podcount,
        'nodepool_config': target_instances
    }

# === 9. Main Runner ===
if __name__ == '__main__':
    FILE_PATH = get_aws_spot_prices(target_region='us-east-1', allow_arm=True)
    POD_COUNT = 10
    POD_CPU = 2
    POD_MEM = 8
    
    # getGoldenNodepool 함수 테스트 (verbose=True로 설정하여 상세 출력)
    result = getGoldenNodepool(FILE_PATH, POD_COUNT, POD_CPU, POD_MEM, verbose=True)