#!/usr/bin/env python
# coding: utf-8

# In[6]:


import pandas as pd
import os
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import matplotlib.pyplot as plt
import ast


from matplotlib.ticker import FuncFormatter

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42


# In[7]:


def getMaxInstRatio(nodepool_config):
    lst = eval(nodepool_config)
    maxratio = 0
    for info in lst:
        maxratio = max(maxratio, info['num_instances']/info['T3'])
    return maxratio


# In[8]:


# result 폴더 내의 모든 하위 폴더 목록 가져오기
result_dir = "./data/result_4_region"
result_folders = []
for region in os.listdir(result_dir):
    region_path = os.path.join(result_dir, region)
    for sc in os.listdir(region_path):
        targert_path = os.path.join(region_path, sc)
        result_folders.append(targert_path)

golden = "golden_section_summary.csv"
greedy = "greedy_summary.csv"
sv_node = "spotverse_node_summary.csv"
sv_pod = "spotverse_pod_summary.csv"

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
            algorithm_dfs[algo].append(df)


algonodecounts = {
    'golden': [],
    'greedy': [],
    'sv_node': [],
    'sv_pod': [],
}

for i in range(len(algorithm_dfs['golden'])):
    df = algorithm_dfs['golden'][i].copy()

    # UsagePerT3 컬럼이 이미 있으면 그대로 float으로 캐스팅,
    # 없으면 새로 만들면서 float으로 초기화
    if "UsagePerT3" in df.columns:
        df["UsagePerT3"] = df["UsagePerT3"].astype("float64")
    else:
        df["UsagePerT3"] = 0.0

    for j in range(len(df)):
        lst = eval(df["nodepool_config"][j])
        tmpsum = 0.0
        for idx in range(len(lst)):
            info = lst[idx]
            algonodecounts['golden'].append(info['num_instances'])
            tmpsum += info['num_instances'] / info['T3']
        df.loc[j, "UsagePerT3"] = tmpsum / len(lst)
    algorithm_dfs['golden'][i] = df

for i in range(len(algorithm_dfs['greedy'])):
    df = algorithm_dfs['greedy'][i].copy()

    if "UsagePerT3" in df.columns:
        df["UsagePerT3"] = df["UsagePerT3"].astype("float64")
    else:
        df["UsagePerT3"] = 0.0

    for j in range(len(df)):
        lst = eval(df["nodepool_config"][j])
        tmpsum = 0.0
        for idx in range(len(lst)):
            info = lst[idx]
            algonodecounts['greedy'].append(info['num_instances'])
            tmpsum += info['num_instances'] / info['T3']
        df.loc[j, "UsagePerT3"] = tmpsum / len(lst)

    algorithm_dfs['greedy'][i] = df


for i in range(len(algorithm_dfs['sv_node'])):
    algorithm_dfs['sv_node'][i]["UsagePerT3"] = algorithm_dfs['sv_node'][i]["nodes_used"]/algorithm_dfs['sv_node'][i]["T3"]
    algorithm_dfs['sv_node'][i]["UsagePerT3_cliped"] = algorithm_dfs['sv_node'][i]["UsagePerT3"]
    algorithm_dfs['sv_node'][i]["UsagePerT3_cliped"] = algorithm_dfs['sv_node'][i].apply(
        lambda row: row["UsagePerT3"] if row["T3"] < 50 else min(row["UsagePerT3"], 1.0), 
        axis=1
    )
    for j in range(len(algorithm_dfs['sv_node'][i])):
        algonodecounts['sv_node'].append(algorithm_dfs['sv_node'][i]["nodes_used"][j])

for i in range(len(algorithm_dfs['sv_pod'])):
    algorithm_dfs['sv_pod'][i]["UsagePerT3"] = algorithm_dfs['sv_pod'][i]["nodes_used"]/algorithm_dfs['sv_pod'][i]["T3"]
    algorithm_dfs['sv_pod'][i]["UsagePerT3_cliped"] = algorithm_dfs['sv_pod'][i]["UsagePerT3"].clip(upper=1.0)
    algorithm_dfs['sv_pod'][i]["UsagePerT3_cliped"] = algorithm_dfs['sv_pod'][i].apply(
        lambda row: row["UsagePerT3"] if row["T3"] < 50 else min(row["UsagePerT3"], 1.0), 
        axis=1
    )
    for j in range(len(algorithm_dfs['sv_pod'][i])):
        algonodecounts['sv_pod'].append(algorithm_dfs['sv_pod'][i]["nodes_used"][j])


# In[9]:


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


# In[10]:


# 각 알고리즘별로 노드풀 내 인스턴스 개수들을 집계
# 구조: {algo: [num_instances1, num_instances2, ...]}
nodepool_instance_counts = {}

for algo, df in merged_dfs.items():
    if df.empty:
        continue

    nodepool_instance_counts[algo] = []

    for idx, row in df.iterrows():
        # nodepool_config 컬럼이 있는 경우
        if 'nodepool_config' in df.columns:
            nodepool_config = row['nodepool_config']

            # 문자열을 파싱
            if isinstance(nodepool_config, str):
                try:
                    config_list = ast.literal_eval(nodepool_config)
                except:
                    continue
            else:
                config_list = nodepool_config

            # 각 노드풀 설정에서 num_instances 추출하여 저장
            for config in config_list:
                num_instances = config.get('num_instances', 0)
                nodepool_instance_counts[algo].append(num_instances)
        else:
            # nodepool_config가 없는 경우, num_instances 컬럼 값 직접 저장
            if 'num_instances' in df.columns:
                num_instances = row['num_instances']
                nodepool_instance_counts[algo].append(num_instances)

# 결과 확인
for algo, counts in nodepool_instance_counts.items():
    print(f"{algo}: {len(counts)} entries, mean={sum(counts)/len(counts):.2f}")


font_size = 32
font_family = 'Roboto'

plt.rcParams['font.family'] = font_family
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False

# 데이터 준비
records = []
for algo, counts in nodepool_instance_counts.items():
    for count in counts:
        records.append({'Algorithm': algo, 'InstanceCount': count})
df_nodepool = pd.DataFrame(records)

# 색상 및 마커/해치 지정
box_colors = ['orange', '#7fa7ff', '#757575', 'lightgray']
hatch_patterns = ['/', '\\', '.', 'x']
line_color = 'black'

# 알고리즘 매핑
algorithms = {
    'KubePACS': 'golden',
    'KubePACS\n-Greedy': 'greedy',
    'SpotVerse\n-Node': 'sv_node',
    'SpotVerse\n-Pod': 'sv_pod'
}

# 알고리즘 순서 지정
algo_order = list(algorithms.values())

fig, ax = plt.subplots(figsize=(10, 7.5))

# boxplot 생성 (order 지정)
bp = sns.boxplot(
    data=df_nodepool,
    x='Algorithm',
    y='InstanceCount',
    order=algo_order,
    width=0.7,
    linewidth=2.5,
    fliersize=3,
    ax=ax
)

# boxplot 색상, 테두리, 해치 적용
# ax.patches 대신 artists 사용하거나 직접 박스 찾기
boxes = [patch for patch in ax.patches if patch.__class__.__name__ == 'PathPatch']
if len(boxes) == 0:
    # seaborn 최신 버전에서는 다른 방식으로 접근
    boxes = ax.patches

for i, (color, hatch) in enumerate(zip(box_colors, hatch_patterns)):
    if i < len(boxes):
        boxes[i].set_facecolor(color)
        boxes[i].set_edgecolor(line_color)
        boxes[i].set_linewidth(2.5)
        boxes[i].set_hatch(hatch)

# 박스 내부 선들 색 설정
for line in ax.lines:
    line.set_color(line_color)

# 로그 스케일 및 눈금 조정
ax.set_yscale('log')
ax.set_ylim(0.7, 1200)
log_ticks = [1, 10, 100, 1000]
ax.set_yticks(log_ticks)
ax.set_yticklabels([f"$10^{int(np.log10(t))}$" if t != 1 else "1" for t in log_ticks], fontsize=font_size)
ax.tick_params(which='minor', length=0)

ax.set_xticklabels(algorithms.keys(), fontsize=font_size-2)
ax.set_xlabel('', fontsize=font_size)
ax.set_ylabel('Number of Nodes per Type', fontsize=font_size, labelpad=5)
ax.tick_params(axis='y', labelsize=font_size)

plt.tight_layout()
plt.savefig('compare-type-usage.pdf', dpi=300, bbox_inches='tight')
plt.show()

