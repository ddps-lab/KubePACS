import json
import os
from matplotlib import pyplot as plt
import pandas as pd
import boto3
import numpy as np

from alpha_ILP_library_v3 import getGoldenNodepool

# /result 폴더 경로 설정
result_dir = 'region'
dataset_dir = os.path.join(os.path.dirname(__file__), 'dataset')

# 폴더 내의 모든 csv 파일 읽기
csv_files = [f for f in os.listdir(result_dir) if f.endswith('.csv')]
session = boto3.Session(profile_name='spotrank')

def extract_data_from_spotlake(need_extract_time, region):
    bucket_name = 'spotlake'
    prefix = "rawdata/aws/2025"
    s3 = session.client('s3')
    os.makedirs(dataset_dir, exist_ok=True)
    for time in need_extract_time:
        dt = pd.to_datetime(time)
        if dt.tzinfo is None:
            # 타임존 정보가 없으면 붙이고 변환
            utc_time = dt.tz_localize('Asia/Seoul').tz_convert('UTC')
        else:
            # 이미 타임존 있으면 바로 변환
            utc_time = dt.tz_convert('UTC')
        mm = utc_time.strftime('%m')
        d = utc_time.strftime('%d')
        h = utc_time.strftime('%H')
        m = utc_time.strftime('%M')
        key = f"{prefix}/{mm}/{d}/{h}-{m}-00.csv.gz"
        local_path = f"{dataset_dir}/{time}.csv.gz"
        if not os.path.exists(local_path):
            s3.download_file(Bucket=bucket_name, Key=key, Filename=local_path)
        else:
            print(f"{time} already exists download skip")

        spotlake_df = pd.read_csv(local_path)
        merge_spotlake_coremark(spotlake_df, time, region)

def merge_spotlake_coremark(spotlake_df, filename, region):
    coremark_df = pd.read_csv(os.path.join(dataset_dir, 'aws_coremark_singlecore.csv'))
    spotlake_df = spotlake_df[spotlake_df['Region'] == region]
    spotlake_df = pd.merge(spotlake_df, coremark_df, how='left', on="InstanceType")
    if "Time" in spotlake_df.columns:
        spotlake_df = spotlake_df.drop(columns=["Time"])

    # CoreMark 열이 비어있는 행 제거
    spotlake_df = spotlake_df.dropna(subset=["CoreMark"])
    # SpotPrice 무효 행 필터링
    spotlake_df = spotlake_df[spotlake_df['SpotPrice'] > 0]

    spotlake_df.to_csv(os.path.join(dataset_dir, f"{filename}.csv"), index=False)


def fetch_and_cache_az_mapping(region):
    ec2 = session.client('ec2', region_name=region)
    response = ec2.describe_availability_zones(AllAvailabilityZones=True)
    mapping = {az['ZoneName']: az['ZoneId'] for az in response['AvailabilityZones']}
    print(f"[Info] AZ Mapping for {region}: {mapping}")
    with open(f'{region}_azid_mapping.json', 'w') as f:
        json.dump(mapping, f)
    return mapping


def load_az_mapping(region):
    if os.path.exists(f'{region}_azid_mapping.json'):
        with open(f'{region}_azid_mapping.json', 'r') as f:
            return json.load(f)
    else:
        return fetch_and_cache_az_mapping(region)
    
def azname_to_azid(azname, region):
    mapping = load_az_mapping(region)
    return mapping[azname]

def calc_assignable_pod(pod_cpu, pod_memory, instance_cpu, instance_memory):
    return min(instance_cpu // pod_cpu, instance_memory // pod_memory)

# 각 csv 파일 읽어서 출력
for csv_file in csv_files:
    total_cost_csv = 0
    file_path = os.path.join(result_dir, csv_file)
    df = pd.read_csv(file_path)
    #각 열별 first_time 정재
    # first_time 열의 시간을 10분 단위로 내림
    df['first_time'] = pd.to_datetime(df['first_time'])
    df['first_time'] = df['first_time'].dt.floor('10min')
    need_extract_time = df['first_time'].unique().dropna()
    print(need_extract_time)
    extract_data_from_spotlake(need_extract_time, df['region'].iloc[0])
    result_list = []
    # 각 first_time에 맞는 datasets 찾아 계산
    for time in need_extract_time:
        dataset_path = os.path.join(dataset_dir, f"{time}.csv")
        if os.path.exists(dataset_path):
            spotlake_df = pd.read_csv(dataset_path)
            # 해당 시간의 데이터만 필터링
            time_df = df[df['first_time'] == time]
            # print(time_df)
            # 각 행에 대해 계산 수행
            for _, row in time_df.iterrows():
                pods = row['pods']
                cpu = row['cpu']
                memory = row['memory']
                nodepool_config = eval(row['nodepool_config'])
            
                total_performance = 0
                total_cost = 0
                total_assignable_pod = 0

                kubecaps_nodepool = getGoldenNodepool(dataset_path, pods, cpu, memory, left=0, right=1, tolerance=0.01, verbose=False, scale="min", region=row['region'])
                # nodepool_config의 각 인스턴스에 대해 계산
                nodepool_config_list = []
                skip_row = False
                for instance in nodepool_config:
                    instance_type = instance['instance_type']
                    az = azname_to_azid(instance['availability_zone'], row['region'])
                    num_instances = instance['num_instances']
                    
                    # 해당 인스턴스 타입에 맞는 데이터 찾기
                    instance_data = spotlake_df[
                        (spotlake_df['InstanceType'] == instance_type) & (spotlake_df['AZ'] == az)
                    ]
                    
                    if not instance_data.empty:
                        instance['T3'] = instance_data['T3'].iloc[0]
                    else:
                        skip_row = True
                        break
                        
                    nodepool_config_list.append(instance)

                    if not instance_data.empty:
                        if not instance_data['CoreMark'].isna().all():
                            coremark = instance_data['CoreMark'].iloc[0]
                            assignable_pod = calc_assignable_pod(cpu, memory, instance_data['vCPU'].iloc[0], instance_data['Memory'].iloc[0])
                            total_performance += (coremark * assignable_pod * num_instances)
                            total_assignable_pod += (assignable_pod * num_instances)
                        else:
                            print(f"!No CoreMark data for {instance_type} in {az}")
                            break
                        cost = instance_data['SpotPrice'].iloc[0] * num_instances
                        total_cost += cost
                    else:
                        print(f"!No data found for {instance_type} in {az}")
                        skip_row = True
                        break

                if skip_row:
                    continue

                excess_pod = total_assignable_pod - pods
                print(f"Time: {time}, Pods: {pods}, CPU: {cpu}, Memory: {memory}")
                print(f"Karpenter Total Performance: {total_performance}")
                print(f"Karpenter Total Cost: {total_cost}")
                print(f"Karpenter Total Assignable Pod: {total_assignable_pod}")
                print(f"Karpenter Excess Pod: {excess_pod}")
                print(f"Karpenter Efficiency: {total_performance / (total_assignable_pod * total_cost)}")
                # print(f"Karpenter Nodepool: {nodepool_config}")
                # print(f"KubeCaps Nodepool: {kubecaps_nodepool}")
                print(f"KubeCaps Total Performance: {kubecaps_nodepool['performance']}")
                print(f"KubeCaps Total Cost: {kubecaps_nodepool['cost']}")
                print(f"KubeCaps Total Assignable Pod: {kubecaps_nodepool['actual_pods']}")
                print(f"KubeCaps Excess Pod: {kubecaps_nodepool['excess_pods']}")
                print(f"KubeCaps Efficiency: {kubecaps_nodepool['performance'] / (kubecaps_nodepool['actual_pods'] * kubecaps_nodepool['cost'])}")
                print("---")
                result_dict = {"time": time, 
                               "pods": pods, 
                               "cpu": cpu, 
                               "memory": memory, 
                               "karpenter": {
                                   "performance": total_performance,
                                   "cost": total_cost,
                                   "assignable_pod": total_assignable_pod,
                                   "excess_pod": excess_pod,
                                   "efficiency": total_performance /(total_assignable_pod * total_cost),
                                   "nodepool": nodepool_config_list
                               },
                               "kubecaps": {
                                   "performance": kubecaps_nodepool['performance'],
                                   "cost": kubecaps_nodepool['cost'],
                                   "actual_pods": kubecaps_nodepool['actual_pods'],
                                   "excess_pods": kubecaps_nodepool['excess_pods'],
                                   "efficiency": kubecaps_nodepool['performance'] / (kubecaps_nodepool['actual_pods'] * kubecaps_nodepool['cost']),
                                   "nodepool": kubecaps_nodepool['nodepool_config']
                               },
                               "region": row['region']
                               }
                result_list.append(result_dict)
                total_cost_csv += total_cost
    print(f"Total CSV Cost: {total_cost_csv}")
    result_df = pd.DataFrame(result_list)
    result_df.to_csv(os.path.join(result_dir, f"integrated/{csv_file}_result.csv"), index=False)
    # 각 파일의 시나리오 별 데이터 시각화
    # # 시나리오별 데이터 시각화
    # scenarios = result_df.apply(lambda x: f"{x['pods']}-{x['cpu']}-{x['memory']}", axis=1)
    
    # gap = 2  # 시나리오별 간격 조절 (원하면 3~4로 더 넓혀도 됨)
    # x = np.arange(len(scenarios)) * gap
    # width = 0.7  # 막대 너비 (간격 넓히면 조금 더 넓혀도 됨)

    # plt.figure(figsize=(max(18, len(scenarios)*2), 14))  # 세로도 넉넉하게

    # font_title = 24
    # font_label = 20
    # font_tick = 16
    # font_legend = 18

    # performance_diff = (result_df['karpenter'].apply(lambda x: x['performance']) - result_df['kubecaps'].apply(lambda x: x['performance'])) / result_df['kubecaps'].apply(lambda x: x['performance']) * 100
    # cost_diff = (result_df['karpenter'].apply(lambda x: x['cost']) - result_df['kubecaps'].apply(lambda x: x['cost'])) / result_df['kubecaps'].apply(lambda x: x['cost']) * 100
    # efficiency_diff = (result_df['karpenter'].apply(lambda x: x['efficiency']) - result_df['kubecaps'].apply(lambda x: x['efficiency'])) / result_df['kubecaps'].apply(lambda x: x['efficiency']) * 100

    # # 1. Performance % 차이 (1,1)
    # plt.subplot(2, 2, 1)
    # plt.bar(x, performance_diff, width, color='blue')
    # plt.axhline(0, color='red', linewidth=1, linestyle='--')
    # plt.xticks(x, scenarios, rotation=45, fontsize=font_tick)
    # plt.title('Performance Difference (%)\n(Baseline KubeCAPS)', fontsize=font_title)
    # plt.xlabel('Scenario (pods-cpu-memory)', fontsize=font_label)
    # plt.ylabel('Difference (%)', fontsize=font_label)

    # # 2. Cost % 차이 (1,2)
    # plt.subplot(2, 2, 2)
    # plt.bar(x, cost_diff, width, color='blue')
    # plt.axhline(0, color='red', linewidth=1, linestyle='--')
    # plt.xticks(x, scenarios, rotation=45, fontsize=font_tick)
    # plt.title('Cost Difference (%)\n(Baseline KubeCAPS)', fontsize=font_title)
    # plt.xlabel('Scenario (pods-cpu-memory)', fontsize=font_label)
    # plt.ylabel('Difference (%)', fontsize=font_label)

    # # 3. Efficiency % 차이 (2,1)
    # plt.subplot(2, 2, 3)
    # plt.bar(x, efficiency_diff, width, color='blue')
    # plt.axhline(0, color='red', linewidth=1, linestyle='--')
    # plt.xticks(x, scenarios, rotation=45, fontsize=font_tick)
    # plt.title('Efficiency Difference (%)\n(Baseline KubeCAPS)', fontsize=font_title)
    # plt.xlabel('Scenario (pods-cpu-memory)', fontsize=font_label)
    # plt.ylabel('Difference (%)', fontsize=font_label)

    # # 4. Excess Pods (2,1)
    # plt.subplot(2, 2, 4)
    # plt.bar(x - width/2, result_df['karpenter'].apply(lambda x: x['excess_pod']), width, label='Karpenter', alpha=0.7, color='blue')
    # plt.bar(x + width/2, result_df['kubecaps'].apply(lambda x: x['excess_pods']), width, label='KubeCaps', alpha=0.7, color='orange')
    # plt.xticks(x, scenarios, rotation=45, fontsize=font_tick)
    # plt.title('Excess Pod Comparison', fontsize=font_title)
    # plt.xlabel('Scenario (pods-cpu-memory)', fontsize=font_label)
    # plt.ylabel('Excess Pods', fontsize=font_label)
    # plt.legend(fontsize=font_legend)

    # plt.tight_layout()
    # plt.savefig(os.path.join(result_dir, f"{csv_file}_comparison.png"))


    # # Load 분류를 위한 함수 정의
    # def classify_load(row):
    #     pods, cpu, mem = row['pods'], row['cpu'], row['memory']
    #     total_cpu = pods * cpu
    #     total_mem = pods * mem
        
    #     if total_cpu <= 200 and total_mem <= 200:
    #         return 'Low Load'
    #     elif total_cpu <= 800 and total_mem <= 4000:
    #         return 'Medium Load'
    #     else:
    #         return 'High Load'

    # # Load 분류 추가
    # result_df['load_category'] = result_df.apply(classify_load, axis=1)

    # # Load별 데이터 분리
    # filtered_df = result_df[result_df['karpenter'].apply(lambda x: x['excess_pod'] >= 0)]
    # low_load = filtered_df[filtered_df['load_category'] == 'Low Load']
    # medium_load = filtered_df[filtered_df['load_category'] == 'Medium Load']
    # high_load = filtered_df[filtered_df['load_category'] == 'High Load']

    # # Load별 boxplot 그리기
    # fig, axes = plt.subplots(1, 3, figsize=(24, 8))
    # fig.suptitle('Cost and Efficiency Comparison by Load Category', fontsize=font_title)

    # load_names = ['Low', 'Medium', 'High']
    # load_dfs = [low_load, medium_load, high_load]

    # for i, (ax, load_df, load_name) in enumerate(zip(axes, load_dfs, load_names)):
    #     # 데이터 준비
    #     cost_data = [
    #         load_df['karpenter'].apply(lambda x: x['cost']),
    #         load_df['kubecaps'].apply(lambda x: x['cost'])
    #     ]
    #     eff_data = [
    #         load_df['karpenter'].apply(lambda x: x['efficiency']),
    #         load_df['kubecaps'].apply(lambda x: x['efficiency'])
    #     ]
    #     positions_cost = [1, 3]
    #     positions_eff = [1.5, 3.5]

    #     # Cost boxplot (좌측 y축)
    #     bp1 = ax.boxplot(cost_data, positions=positions_cost, widths=0.35, patch_artist=True, boxprops=dict(facecolor='skyblue'))
    #     ax.set_ylabel('Cost ($)', fontsize=font_label)
    #     ax.set_xticks([1.25, 3.25])
    #     ax.set_xticklabels(['Karpenter', 'KubeCAPS'], fontsize=font_tick)
    #     ax.set_title(f'{load_name} Load', fontsize=font_label)
    #     ax.tick_params(axis='y', labelsize=font_tick)

    #     # Efficiency boxplot (우측 y축)
    #     ax2 = ax.twinx()
    #     bp2 = ax2.boxplot(eff_data, positions=positions_eff, widths=0.35, patch_artist=True, boxprops=dict(facecolor='orange'))
    #     ax2.set_ylabel('Efficiency', fontsize=font_label)
    #     ax2.tick_params(axis='y', labelsize=font_tick)

    #     # 중앙 세로 점선
    #     ax.axvline(x=2.25, color='gray', linestyle='--', linewidth=2, alpha=0.7)
    #     ax2.axvline(x=2.25, color='gray', linestyle='--', linewidth=2, alpha=0.7)

    #     # 하단 cost/efficiency 색상 라벨
    #     ax.text(1, -0.15, 'Cost', color='skyblue', fontsize=font_label, ha='center', va='top', transform=ax.get_xaxis_transform())
    #     ax.text(1.5, -0.15, 'Efficiency', color='orange', fontsize=font_label, ha='center', va='top', transform=ax.get_xaxis_transform())
    #     ax.text(3, -0.15, 'Cost', color='skyblue', fontsize=font_label, ha='center', va='top', transform=ax.get_xaxis_transform())
    #     ax.text(3.5, -0.15, 'Efficiency', color='orange', fontsize=font_label, ha='center', va='top', transform=ax.get_xaxis_transform())

    # plt.tight_layout()
    # plt.savefig(os.path.join(result_dir, f"{csv_file}_load_comparison.png"))
    # plt.close()
