#!/usr/bin/env python
# coding: utf-8

# In[20]:


import pandas as pd
import os
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42


# In[21]:


def getMaxInstRatio(nodepool_config):
    lst = eval(nodepool_config)
    maxratio = 0
    for info in lst:
        maxratio = max(maxratio, info['num_instances']/info['T3'])
    return maxratio


# In[22]:


# result 폴더 내의 모든 하위 폴더 목록 가져오기
result_dir = "./data/result_4_region"
result_folders = []
for region in os.listdir(result_dir):
    region_path = os.path.join(result_dir, region)
    for sc in os.listdir(region_path):
        targert_path = os.path.join(region_path, sc)
        result_folders.append(targert_path)


# In[23]:


result_folders


# In[24]:


scenarios = [
    # (pod_count, cpu, mem)
    (10, 1, 2), # tiny
    (10, 2, 2), # tiny cpu-intensive
    (10, 1, 4), # tiny mem-intensive
    (50, 1, 2), # small
    (50, 2, 2), # small cpu-intensive
    (50, 1, 4), # small mem-intensive
    (100, 1, 2), # medium
    (100, 2, 2), # medium cpu-intensive
    (100, 1, 4), # medium mem-intensive
    (400, 1, 2), # large
    (400, 2, 2), # large cpu-intensive
    (400, 1, 4), # large mem-intensive
    (1000, 1, 2), # huge
    (1000, 2, 2), # huge cpu-intensive
    (1000, 1, 4), # huge mem-intensive
    (17, 7, 7), (75, 3, 5), (115, 4, 2), (287, 1, 6), (439, 1, 9)
]


# In[25]:


golden = "golden_section_summary.csv"
greedy = "greedy_summary.csv"
sv_node = "spotverse_node_summary.csv"
sv_pod = "spotverse_pod_summary.csv"
# spotkube = "spotkube_summary.csv"


# In[26]:


# 각 알고리즘별로 데이터프레임을 저장할 딕셔너리 생성
algorithm_dfs = {
    'golden': [],
    'greedy': [],
    'sv_node': [],
    'sv_pod': [],
    # 'spotkube': []
}

# 각 폴더를 순회하며 CSV 파일 읽기
for folder_path in result_folders:
    # 각 알고리즘의 CSV 파일 읽기
    for algo, filename in zip(algorithm_dfs.keys(), [golden, greedy, sv_node, sv_pod]):
    # for algo, filename in zip(algorithm_dfs.keys(), [golden, greedy, sv_node, sv_pod, spotkube]):
        file_path = os.path.join(folder_path, filename)
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            df['date'] = folder_path.split("/")[-1]  # 날짜 정보 추가
            df['efficiency'] = df['performance']/(df['actual_pods']*df['cost'])
            df["PerfPerPod"] = df['performance']/df["actual_pods"]
            algorithm_dfs[algo].append(df)
        else:
            print(f"File not found: {file_path}")


# In[27]:


for i in range(len(algorithm_dfs['golden'])):
    algorithm_dfs['golden'][i]["MaxUsagePerT3"] = algorithm_dfs['golden'][i]["nodepool_config"].apply(getMaxInstRatio)
    # algorithm_dfs['golden'][i]["PerfPerPod"] = algorithm_dfs['golden'][i]["performance"]/algorithm_dfs['golden'][i]["actual_pods"]


for i in range(len(algorithm_dfs['greedy'])):
    algorithm_dfs['greedy'][i]["MaxUsagePerT3"] = algorithm_dfs['greedy'][i]["nodepool_config"].apply(getMaxInstRatio)
    # algorithm_dfs['greedy'][i]["PerfPerPod"] = algorithm_dfs['greedy'][i]["performance"]/algorithm_dfs['greedy'][i]["actual_pods"]

for i in range(len(algorithm_dfs['sv_node'])):
    algorithm_dfs['sv_node'][i]["MaxUsagePerT3"] = algorithm_dfs['sv_node'][i]["nodes_used"]/algorithm_dfs['sv_node'][i]["T3"]
    algorithm_dfs['sv_node'][i]["MaxUsagePerT3"] = algorithm_dfs['sv_node'][i]["MaxUsagePerT3"].clip(upper=1.0)
    # algorithm_dfs['sv_node'][i]["PerfPerPod"] = algorithm_dfs['sv_node'][i]["performance"]/algorithm_dfs['sv_node'][i]["actual_pods"]

for i in range(len(algorithm_dfs['sv_pod'])):
    algorithm_dfs['sv_pod'][i]["MaxUsagePerT3"] = algorithm_dfs['sv_pod'][i]["nodes_used"]/algorithm_dfs['sv_pod'][i]["T3"]
    algorithm_dfs['sv_pod'][i]["MaxUsagePerT3"] = algorithm_dfs['sv_pod'][i]["MaxUsagePerT3"].clip(upper=1.0)
    # algorithm_dfs['sv_pod'][i]["PerfPerPod"] = algorithm_dfs['sv_pod'][i]["performance"]/algorithm_dfs['sv_pod'][i]["actual_pods"]

# for i in range(len(algorithm_dfs['spotkube'])):
#     algorithm_dfs['spotkube'][i]["MaxUsagePerT3"] = algorithm_dfs['spotkube'][i]["nodes_used"]/algorithm_dfs['spotkube'][i]["T3"]



# In[28]:


# 각 알고리즘별로 데이터프레임 병합
merged_dfs = {}
for algo, dfs in algorithm_dfs.items():
    if dfs:  # 빈 리스트가 아닌 경우에만 병합
        merged_dfs[algo] = pd.concat(dfs, ignore_index=True)
    else:
        merged_dfs[algo] = pd.DataFrame()  # 빈 데이터프레임 생성

# 결과 확인
for algo, df in merged_dfs.items():
    print(f"\n{algo} 데이터프레임 크기: {df.shape}")


# In[29]:


merged_dfs['golden'].groupby(['pods', 'cpu', 'mem']).agg({
    'cost': 'mean',
    'efficiency': 'mean',
    'performance': 'mean',
    'PerfPerPod': 'mean',
}).reset_index()


# In[30]:


checktype = merged_dfs['sv_pod']['instance_type'].apply(lambda x: x.split('.')[0])
checktype.value_counts()


# In[31]:


cate = ['golden', 'greedy', 'sv_node', 'sv_pod']
# 각 알고리즘별로 그룹바이 결과를 저장할 리스트
grouped_results = []

# 각 알고리즘에 대해 그룹바이 수행
for algo in cate:
    if not merged_dfs[algo].empty:
        grouped = merged_dfs[algo].groupby(['pods', 'cpu', 'mem']).agg({
            'cost': 'mean',
            'efficiency': 'mean',
            'performance': 'mean',
            'PerfPerPod': 'mean',
        }).reset_index()
        grouped['algorithm'] = algo  # 알고리즘 컬럼 추가
        grouped_results.append(grouped)

# 모든 결과를 하나의 데이터프레임으로 통합
combined_df = pd.concat(grouped_results, ignore_index=True)

# 결과 확인
print(combined_df)


# In[32]:


# golden 알고리즘의 결과를 기준으로 다른 알고리즘들과 비교
golden_df = combined_df[combined_df['algorithm'] == 'golden'].copy()
golden_df = golden_df.rename(columns={'cost': 'golden_cost', 'efficiency': 'golden_efficiency', 'performance': 'golden_performance', 'PerfPerPod': 'golden_PerfPerPod'})

# 다른 알고리즘들과 비교
comparison_df = combined_df.copy()
comparison_df = comparison_df.merge(
    golden_df[['pods', 'cpu', 'mem', 'golden_cost', 'golden_efficiency', 'golden_performance', 'golden_PerfPerPod']], 
    on=['pods', 'cpu', 'mem']
)

# 비율 계산
comparison_df['cost_ratio'] = comparison_df['cost'] / comparison_df['golden_cost']
comparison_df['efficiency_ratio'] = comparison_df['efficiency'] / comparison_df['golden_efficiency']
comparison_df['performance_ratio'] = comparison_df['performance'] / comparison_df['golden_performance']
comparison_df['perf_per_pod_ratio'] = comparison_df['PerfPerPod'] / comparison_df['golden_PerfPerPod'] 


# 결과 정렬 및 출력
result = comparison_df[['pods', 'cpu', 'mem', 'algorithm', 'cost_ratio', 'efficiency_ratio', 'performance_ratio', 'perf_per_pod_ratio']].sort_values(['pods', 'cpu', 'mem', 'algorithm'])
print("각 알고리즘의 golden 대비 비율 (cost_ratio: 비용이 몇 배인지, efficiency_ratio: 효율이 몇 배인지)")
print(result)


# In[33]:


import matplotlib.pyplot as plt
import numpy as np

font_size = 33
font_family = 'Roboto'

plt.rcParams['font.family'] = font_family
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False

# ❶ x축 레이블을 scenarios 순서대로 생성
x_labels = [f"{pod}-{cpu}-{mem}" for (pod, cpu, mem) in scenarios]

# ❷ spotkube 제외
comparison_df = comparison_df[comparison_df['algorithm'] != 'spotkube']

# ❸ 알고리즘 매핑 및 플롯 설정
algo_map = {'KubeCAPS': 'golden', 'KubeCAPS_Greedy': 'greedy', 
            'SpotVerse_Node': 'sv_node', 'SpotVerse_Pod': 'sv_pod'}
colors = ['orange', '#7fa7ff', '#757575', 'lightgray']
markers = ['*', 'o', 's', '^']

plt.figure(figsize=(12, 7.5))

# ❹ x축 위치 벌리기
xtick_positions = np.arange(len(x_labels)) * 1.8

# ❺ 알고리즘별 점 찍기
for i, (label, algo_key) in enumerate(algo_map.items()):
    algo_data = comparison_df[comparison_df['algorithm'] == algo_key].copy()
    algo_data['scenario_str'] = algo_data.apply(lambda row: f"{row['pods']}-{row['cpu']}-{row['mem']}", axis=1)
    algo_data = algo_data.set_index('scenario_str').reindex(x_labels)

    plt.scatter(xtick_positions, algo_data['efficiency_ratio'],
                marker=markers[i], color=colors[i],
                s=540 if algo_key == 'golden' else 400,
                label=label, alpha=1.0)

# 기준선 및 레이블
plt.axhline(y=1.0, color='black', linestyle='--', linewidth=1)
plt.xticks(
    ticks=xtick_positions,
    labels=x_labels,
    rotation=50, fontsize=font_size-3, rotation_mode='anchor', ha='right'
)
plt.yticks(fontsize=font_size)
plt.xlabel('Pods-CPU-Memory', fontsize=font_size, labelpad=5)
plt.ylabel(r'Overall efficiency ($E_{\mathrm{Total}}$)', fontsize=font_size, labelpad=5)

# plt.legend(...)  # 필요시 사용
plt.grid(True, axis='x', alpha=0.2)
plt.tight_layout()

# PDF 저장
plt.savefig('comparison-related-work-benchmark-score.pdf', format="pdf", dpi=300, bbox_inches='tight')
plt.show()


# In[34]:


# Calculate average efficiency improvements of KubeCAPS (golden) compared to baselines
# 각 시나리오별로 개선율을 계산한 후 평균을 구함

# 시나리오 식별을 위한 키 생성
comparison_df['scenario'] = comparison_df['pods'].astype(str) + '-' + comparison_df['cpu'].astype(str) + '-' + comparison_df['mem'].astype(str)

# 각 시나리오별로 golden과 baseline 비교를 위해 pivot
scenarios = comparison_df[comparison_df['algorithm'] == 'golden']['scenario'].unique()

improvements_vs_greedy = []
improvements_vs_sv_node = []
improvements_vs_sv_pod = []

for scenario in scenarios:
    scenario_data = comparison_df[comparison_df['scenario'] == scenario]

    golden_eff = scenario_data[scenario_data['algorithm'] == 'golden']['efficiency_ratio'].values[0]
    greedy_eff = scenario_data[scenario_data['algorithm'] == 'greedy']['efficiency_ratio'].values[0]
    sv_node_eff = scenario_data[scenario_data['algorithm'] == 'sv_node']['efficiency_ratio'].values[0]
    sv_pod_eff = scenario_data[scenario_data['algorithm'] == 'sv_pod']['efficiency_ratio'].values[0]

    # 각 시나리오에서의 개선율 계산
    improvements_vs_greedy.append((golden_eff - greedy_eff) / greedy_eff * 100)
    improvements_vs_sv_node.append((golden_eff - sv_node_eff) / sv_node_eff * 100)
    improvements_vs_sv_pod.append((golden_eff - sv_pod_eff) / sv_pod_eff * 100)

print("=== Average Efficiency Improvements of KubeCAPS over Baselines ===")
print(f"(각 시나리오별 개선율 계산 후 평균)")
print(f"KubeCAPS-Greedy: {np.mean(improvements_vs_greedy):.2f}%")
print(f"SpotVerse-Node: {np.mean(improvements_vs_sv_node):.2f}%")
print(f"SpotVerse-Pod: {np.mean(improvements_vs_sv_pod):.2f}%")

print(f"\n개선율 통계:")
print(f"  vs Greedy: min={np.min(improvements_vs_greedy):.2f}%, max={np.max(improvements_vs_greedy):.2f}%, std={np.std(improvements_vs_greedy):.2f}%")
print(f"  vs SV_Node: min={np.min(improvements_vs_sv_node):.2f}%, max={np.max(improvements_vs_sv_node):.2f}%, std={np.std(improvements_vs_sv_node):.2f}%")
print(f"  vs SV_Pod: min={np.min(improvements_vs_sv_pod):.2f}%, max={np.max(improvements_vs_sv_pod):.2f}%, std={np.std(improvements_vs_sv_pod):.2f}%")


# In[35]:


improvements_vs_greedy


# In[36]:


algo_data


# In[37]:


merged_dfs['golden'][merged_dfs['golden']['excess_pods'] > 1].sort_values('excess_pods', ascending=False)

