#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pandas as pd
import os
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42


# In[2]:


def getMaxInstRatio(nodepool_config):
    lst = eval(nodepool_config)
    maxratio = 0
    for info in lst:
        maxratio = max(maxratio, info['num_instances']/info['T3'])
    return maxratio


# In[3]:


# result 폴더 내의 모든 하위 폴더 목록 가져오기
result_dir = "./data/result_4_region_msa"
result_folders = []
for region in os.listdir(result_dir):
    region_path = os.path.join(result_dir, region)
    for sc in os.listdir(region_path):
        targert_path = os.path.join(region_path, sc)
        result_folders.append(targert_path)


# In[4]:


golden = "golden_section_summary.csv"
greedy = "greedy_summary.csv"
sv_node = "spotverse_node_summary.csv"
sv_pod = "spotverse_pod_summary.csv"
spotkube = "spotkube_summary.csv"


# In[5]:


# 각 알고리즘별로 데이터프레임을 저장할 딕셔너리 생성
algorithm_dfs = {
    'golden': [],
    'greedy': [],
    'sv_node': [],
    'sv_pod': [],
    'spotkube': []
}

# 각 폴더를 순회하며 CSV 파일 읽기
for folder_path in result_folders:
    # 각 알고리즘의 CSV 파일 읽기
    for algo, filename in zip(algorithm_dfs.keys(), [golden, greedy, sv_node, sv_pod, spotkube]):
        file_path = os.path.join(folder_path, filename)
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            df['date'] = folder_path.split("/")[-1]  # 날짜 정보 추가
            df['efficiency'] = df['performance']/(df['actual_pods']*df['cost'])
            algorithm_dfs[algo].append(df)


# In[6]:


algonodecounts = {
    'golden': [],
    'greedy': [],
    'sv_node': [],
    'sv_pod': [],
    'spotkube': []
}

for i in range(len(algorithm_dfs['golden'])):
    df = algorithm_dfs['golden'][i].copy()
    df["UsagePerT3"] = 0.0
    df["UsagePerT3"] = df["UsagePerT3"].astype("float64")
    for j in range(len(df)):
        lst = eval(df["nodepool_config"][j])
        tmpsum = 0
        for idx in range(len(lst)):
            info = lst[idx]
            algonodecounts['golden'].append(info['num_instances'])
            tmpsum += info['num_instances']/info['T3']

        df.loc[j, "UsagePerT3"] = tmpsum/len(lst)
    algorithm_dfs['golden'][i] = df

for i in range(len(algorithm_dfs['greedy'])):
    df = algorithm_dfs['greedy'][i].copy()
    df["UsagePerT3"] = 0.0
    df["UsagePerT3"] = df["UsagePerT3"].astype("float64")
    for j in range(len(df)):
        lst = eval(df["nodepool_config"][j])
        tmpsum = 0
        for idx in range(len(lst)):
            info = lst[idx]
            algonodecounts['greedy'].append(info['num_instances'])
            tmpsum += info['num_instances']/info['T3']

        df.loc[j, "UsagePerT3"] = tmpsum/len(lst)

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

for i in range(len(algorithm_dfs['spotkube'][i])):
    df = algorithm_dfs['spotkube'][i].copy()
    df["UsagePerT3"] = 0.0
    df["UsagePerT3"] = df["UsagePerT3"].astype("float64")
    for j in range(len(df)):
        lst = eval(df["nodepool_config"][j])
        tmpsum = 0
        for idx in range(len(lst)):
            info = lst[idx]
            algonodecounts['spotkube'].append(info['num_instances'])
            tmpsum += info['num_instances'] / info['T3']

        df.loc[j, "UsagePerT3"] = tmpsum/len(lst)

    algorithm_dfs['spotkube'][i] = df


# In[7]:


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

print(algonodecounts)


# In[8]:


cate = ['golden', 'greedy', 'sv_node', 'sv_pod', 'spotkube']
# 각 알고리즘별로 그룹바이 결과를 저장할 리스트
grouped_results = []

# 각 알고리즘에 대해 그룹바이 수행
for algo in cate:
    if not merged_dfs[algo].empty:
        grouped = merged_dfs[algo].groupby(['pods', 'cpu', 'mem']).agg({
            'cost': 'mean',
            'efficiency': 'mean',
            'performance': 'mean'
        }).reset_index()
        grouped['algorithm'] = algo  # 알고리즘 컬럼 추가
        grouped_results.append(grouped)

# 모든 결과를 하나의 데이터프레임으로 통합
combined_df = pd.concat(grouped_results, ignore_index=True)

# 결과 확인
print(combined_df)


# In[9]:


# golden 알고리즘의 결과를 기준으로 다른 알고리즘들과 비교
golden_df = combined_df[combined_df['algorithm'] == 'golden'].copy()
golden_df = golden_df.rename(columns={'cost': 'golden_cost', 'efficiency': 'golden_efficiency', 'performance': 'golden_performance'})

# 다른 알고리즘들과 비교
comparison_df = combined_df.copy()
comparison_df = comparison_df.merge(
    golden_df[['pods', 'cpu', 'mem', 'golden_cost', 'golden_efficiency', 'golden_performance']], 
    on=['pods', 'cpu', 'mem']
)

# 비율 계산
comparison_df['cost_ratio'] = comparison_df['cost'] / comparison_df['golden_cost']
comparison_df['efficiency_ratio'] = comparison_df['efficiency'] / comparison_df['golden_efficiency']
comparison_df['performance_ratio'] = comparison_df['performance'] / comparison_df['golden_performance']

# 결과 정렬 및 출력
result = comparison_df[['pods', 'cpu', 'mem', 'algorithm', 'cost_ratio', 'efficiency_ratio']].sort_values(['pods', 'cpu', 'mem', 'algorithm'])
print("각 알고리즘의 golden 대비 비율 (cost_ratio: 비용이 몇 배인지, efficiency_ratio: 효율이 몇 배인지)")
print(result)


# In[10]:


import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.patches import Patch
import pandas as pd
import numpy as np
import ast
import seaborn as sns


font_size = 36
font_family = 'Roboto'

plt.rcParams['font.family'] = font_family
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False

# 라벨과 색상 매핑
algorithm_labels = {
    'golden': 'KubePACS',
    'greedy': 'KubePACS\n-Greedy',
    'sv_node': 'SpotVerse\n-Node',
    'sv_pod': 'SpotVerse\n-Pod',
    'spotkube': 'SpotKube'
}
algo_order = ['golden', 'greedy', 'sv_node', 'sv_pod', 'spotkube']
algo_colors = {
    'golden': 'orange',
    'greedy': '#7fa7ff',
    'sv_node': '#757575',
    'sv_pod': 'lightgray',
    'spotkube': '#37474F'
}
hatch_patterns = ['/', '\\', '.', 'x', '+']  # 해치 패턴

def millions_formatter(x, pos):
    if x == 0:
        return '0'
    return f'{x * 1e-6:.1f}M'

# 각 알고리즘별로 노드풀 내 인스턴스 개수들을 집계
# 구조: {algo: [num_instances1, num_instances2, ...]}
nodepool_instance_counts = {}

for algo, df in merged_dfs.items():
    if df.empty:
        continue

    nodepool_instance_counts[algo] = []

    for idx, row in df.iterrows():
        if algo == 'spotkube':
            print(idx)
        # nodepool_config 컬럼이 있는 경우
        if 'nodepool_config' in df.columns:
            nodepool_config = row['nodepool_config']

            # 문자열을 파싱
            if isinstance(nodepool_config, str):
                try:
                    config_list = eval(nodepool_config)
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
    if len(counts) > 0:
        print(f"{algo}: {len(counts)} entries, mean={sum(counts)/len(counts):.2f}")

# 데이터 준비
records = []
for algo, counts in nodepool_instance_counts.items():
    for count in counts:
        records.append({'Algorithm': algo, 'InstanceCount': count})
df_nodepool = pd.DataFrame(records)

# 데이터 수집 - Efficiency
eff_data, colors = [], []
for algo in algo_order:
    df = merged_dfs.get(algo)
    if df is not None and not df.empty:
        eff_vals = pd.to_numeric(df['efficiency'], errors='coerce').dropna()
        eff_data.append(eff_vals)
        colors.append(algo_colors[algo])

# 플롯 구성 - 두 개의 서브플롯으로 분리
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 7.5))

x_base = np.arange(len(algo_order)) + 1

# 첫 번째 박스플롯 - Efficiency
bp1 = ax1.boxplot(eff_data, positions=x_base, widths=0.6, patch_artist=True)

# 색상 및 해치 적용 - 첫 번째 플롯
for i, patch in enumerate(bp1['boxes']):
    patch.set_facecolor(colors[i])
    patch.set_edgecolor('black')
    patch.set_linewidth(2)
    patch.set_hatch(hatch_patterns[i])

# 박스플롯 선 색상 - 첫 번째 플롯
for element in ['whiskers', 'caps', 'medians']:
    for line in bp1[element]:
        line.set_color('black')

# 첫 번째 플롯 설정
ax1.set_xticks(x_base)
ax1.set_xticklabels([])  # x축 레이블 제거
ax1.set_xlabel('')
ax1.yaxis.set_major_formatter(ticker.FuncFormatter(millions_formatter))
ax1.text(3, -0.02, 'Efficiency', fontsize=font_size, ha='center', va='top', transform=ax1.get_xaxis_transform())
ax1.set_ylabel(r'Overall efficiency ($E_{\mathrm{Total}}$)', fontsize=font_size, labelpad=5)
ax1.tick_params(axis='y', labelsize=font_size)

# 두 번째 박스플롯 - Availability (Number of nodes per type)
# 각 알고리즘별 인스턴스 개수 데이터 준비
node_count_data = []
box_colors = []
for algo in algo_order:
    if algo in nodepool_instance_counts and len(nodepool_instance_counts[algo]) > 0:
        node_count_data.append(nodepool_instance_counts[algo])
        box_colors.append(algo_colors[algo])
    else:
        node_count_data.append([0])  # 데이터가 없는 경우 빈 리스트 대신 0
        box_colors.append(algo_colors[algo])

bp2 = ax2.boxplot(node_count_data, positions=x_base, widths=0.6, patch_artist=True)

# 색상 및 해치 적용 - 두 번째 플롯
for i, patch in enumerate(bp2['boxes']):
    patch.set_facecolor(box_colors[i])
    patch.set_edgecolor('black')
    patch.set_linewidth(2)
    patch.set_hatch(hatch_patterns[i])

# 박스플롯 선 색상 - 두 번째 플롯
for element in ['whiskers', 'caps', 'medians']:
    for line in bp2[element]:
        line.set_color('black')

# 두 번째 플롯 설정 - y축을 오른쪽으로
ax2.set_xticks(x_base)
ax2.set_xticklabels([])  # x축 레이블 제거
ax2.set_xlabel('')
ax2.text(3, -0.02, 'Availability', fontsize=font_size, ha='center', va='top', transform=ax2.get_xaxis_transform())
ax2.yaxis.tick_right()
ax2.yaxis.set_label_position('right')
ax2.set_ylabel('Number of Nodes per Type', fontsize=font_size, labelpad=5)
ax2.tick_params(axis='y', labelsize=font_size)

ax2.set_ylim(-2.5, 52.5)

# 범례 (선택적으로 주석 해제)
legend_handles = [
    Patch(facecolor=algo_colors[a], edgecolor='black', hatch=hatch_patterns[i], label=algorithm_labels[a])
    for i, a in enumerate(algo_order)
]
# ax1.legend(handles=legend_handles, loc='upper center', bbox_to_anchor=(0.5, -0.08), ncol=2, fontsize=font_size - 2, frameon=False)

plt.tight_layout()
plt.savefig('comparison-msa.pdf', format='pdf', dpi=300, bbox_inches='tight')
plt.show()


# In[11]:


import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.patches import Patch
import pandas as pd
import numpy as np


font_size = 34
font_family = 'Roboto'

plt.rcParams['font.family'] = font_family
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False

# 라벨과 색상 매핑
algorithm_labels = {
    'golden': 'KubePACS',
    'greedy': 'KubePACS_Greedy',
    'sv_node': 'SpotVerse_Node',
    'sv_pod': 'SpotVerse_Pod',
    'spotkube': 'SpotKube'
}
algo_order = ['golden', 'greedy', 'sv_node', 'sv_pod', 'spotkube']
algo_colors = {
    'golden': 'orange',
    'greedy': '#7fa7ff',
    'sv_node': '#757575',
    'sv_pod': 'lightgray',
    'spotkube': '#37474F'
}
hatch_patterns = ['/', '\\', '.', 'x', '+']  # 해치 패턴

def millions_formatter(x, pos):
    if x == 0:
        return '0'
    return f'{x * 1e-6:.1f}M'

# 데이터 수집
eff_data, node_count_data, colors = [], [], []
for algo in algo_order:
    df = merged_dfs.get(algo)
    if df is not None and not df.empty:
        eff_vals = pd.to_numeric(df['efficiency'], errors='coerce').dropna()
        # price_vals = pd.to_numeric(df[''], errors='coerce').dropna()
        eff_data.append(eff_vals)
        node_count_data.append(algonodecounts[algo])
        # price_data.append(price_vals)
        colors.append(algo_colors[algo])

# 플롯 구성 - 두 개의 서브플롯으로 분리
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 9))

x_base = np.arange(len(algo_order)) + 1

# 첫 번째 박스플롯 - Efficiency
bp1 = ax1.boxplot(eff_data, positions=x_base, widths=0.6, patch_artist=True)

# 색상 및 해치 적용 - 첫 번째 플롯
for i, patch in enumerate(bp1['boxes']):
    patch.set_facecolor(colors[i])
    patch.set_edgecolor('black')
    patch.set_linewidth(2)
    patch.set_hatch(hatch_patterns[i])

# 박스플롯 선 색상 - 첫 번째 플롯
for element in ['whiskers', 'caps', 'medians']:
    for line in bp1[element]:
        line.set_color('black')

# 첫 번째 플롯 설정
ax1.set_xticks(x_base)
ax1.set_xticklabels([])  # x축 레이블 제거
ax1.set_xlabel('')
ax1.yaxis.set_major_formatter(ticker.FuncFormatter(millions_formatter))
ax1.text(3, -0.02, 'Efficiency', fontsize=font_size, ha='center', va='top', transform=ax1.get_xaxis_transform())
ax1.set_ylabel(r'Overall efficiency ($E_{\mathrm{Total}}$)', fontsize=font_size, labelpad=5)
ax1.tick_params(axis='y', labelsize=font_size)

# 두 번째 박스플롯 - Availability (Number of nodes)
bp2 = ax2.boxplot(node_count_data, positions=x_base, widths=0.6, patch_artist=True)

# 색상 및 해치 적용 - 두 번째 플롯
for i, patch in enumerate(bp2['boxes']):
    patch.set_facecolor(colors[i])
    patch.set_edgecolor('black')
    patch.set_linewidth(2)
    patch.set_hatch(hatch_patterns[i])

# 박스플롯 선 색상 - 두 번째 플롯
for element in ['whiskers', 'caps', 'medians']:
    for line in bp2[element]:
        line.set_color('black')

# 두 번째 플롯 설정 - y축을 오른쪽으로
ax2.set_xticks(x_base)
ax2.set_xticklabels([])  # x축 레이블 제거
ax2.set_xlabel('')
ax2.text(3, -0.02, 'Availability', fontsize=font_size, ha='center', va='top', transform=ax2.get_xaxis_transform())
ax2.yaxis.tick_right()
ax2.yaxis.set_label_position('right')
ax2.set_ylabel('Number of nodes', fontsize=font_size, labelpad=5)
ax2.tick_params(axis='y', labelsize=font_size)

# 범례 (선택적으로 주석 해제)
legend_handles = [
    Patch(facecolor=algo_colors[a], edgecolor='black', hatch=hatch_patterns[i], label=algorithm_labels[a])
    for i, a in enumerate(algo_order)
]
# ax1.legend(handles=legend_handles, loc='upper center', bbox_to_anchor=(0.5, -0.08), ncol=2, fontsize=font_size - 2, frameon=False)

plt.tight_layout()
# plt.savefig('comparison-msa.pdf', format='pdf', dpi=300, bbox_inches='tight')
plt.show()


# In[12]:


# 각 시나리오별로 KubePACS와 다른 알고리즘 비교
print("=== KubePACS vs Baseline 효율성 비교 (종합 평균) ===\n")

# 시나리오 수 확인 (pods 개수로 확인)
num_scenarios = len(merged_dfs['golden'])

# 각 알고리즘별 시나리오별 improvement 저장
improvements_by_algo = {algo: [] for algo in algo_order if algo != 'golden'}

for scenario_idx in range(num_scenarios):
    kubepacs_eff = merged_dfs['golden'].iloc[scenario_idx]['efficiency']

    for algo in algo_order:
        if algo == 'golden':
            continue
        if algo in merged_dfs:
            other_eff = merged_dfs[algo].iloc[scenario_idx]['efficiency']
            improvement = ((kubepacs_eff - other_eff) / other_eff) * 100
            improvements_by_algo[algo].append(improvement)

# 각 알고리즘별 평균 improvement 계산
for algo in algo_order:
    if algo == 'golden':
        continue
    if algo in improvements_by_algo and len(improvements_by_algo[algo]) > 0:
        avg_improvement = sum(improvements_by_algo[algo]) / len(improvements_by_algo[algo])
        print(f"KubePACS는 {algorithm_labels[algo]}보다 평균 {avg_improvement:.2f}% 더 효율적입니다.")

# 전체 baseline 대비 평균 improvement
all_improvements = []
for algo in improvements_by_algo:
    all_improvements.extend(improvements_by_algo[algo])
if all_improvements:
    overall_avg = sum(all_improvements) / len(all_improvements)
    print(f"\n전체 baseline 대비 KubePACS 평균 효율성 향상: {overall_avg:.2f}%")


# In[13]:


# 각 알고리즘별 평균 efficiency 계산
avg_effs = {}
for algo in algo_order:
    if algo in merged_dfs:
        avg_eff = merged_dfs[algo]['efficiency'].mean()
        avg_effs[algo] = avg_eff
        print(f"{algorithm_labels[algo]}: {avg_eff:.2e}")

# 결과를 데이터프레임으로 변환
eff_df = pd.DataFrame(list(avg_effs.items()), columns=['algorithm', 'avg_efficiency'])
eff_df['algorithm'] = eff_df['algorithm'].map(algorithm_labels)
print("\nDataFrame 형태:")
print(eff_df)

# KubePACS와 다른 알고리즘들의 효율성 비교
kubepacs_eff = eff_df[eff_df['algorithm'] == 'KubePACS']['avg_efficiency'].values[0]

for _, row in eff_df[eff_df['algorithm'] != 'KubePACS'].iterrows():
    algo = row['algorithm']
    eff = row['avg_efficiency']
    improvement = ((kubepacs_eff - eff) / eff) * 100
    print(f"KubePACS는 {algo}보다 {improvement:.2f}% 더 효율적입니다.")


# In[14]:


import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D
from matplotlib.legend_handler import HandlerBase

# --- 설정 ---
algo_order = ['golden', 'greedy', 'sv_node', 'sv_pod', 'spotkube']
algorithm_labels = {
    'golden': 'KubePACS',
    'greedy': 'KubePACS_Greedy',
    'sv_node': 'SpotVerse_Node',
    'sv_pod': 'SpotVerse_Pod',
    'spotkube': 'SpotKube'
}
algo_colors = {
    'golden': 'orange',
    'greedy': '#7fa7ff',
    'sv_node': '#757575',
    'sv_pod': 'lightgray',
    'spotkube': '#37474F'
}
hatch_patterns = ['/', '\\', '.', 'x', '+']
algo_marker_map = {
    'golden': '*',
    'greedy': 'o',
    'sv_node': 's',
    'sv_pod': '^'
}

font_size = 35
font_family = 'Roboto'

plt.rcParams['font.family'] = font_family
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False

# --- 사용자 정의 핸들러 ---
class MarkerPatchHandler(HandlerBase):
    def __init__(self, marker=None, color=None, hatch=None, **kwargs):
        self.marker = marker
        self.color = color
        self.hatch = hatch
        super().__init__(**kwargs)

    def create_artists(self, legend, orig_handle,
                       xdescent, ydescent, width, height, fontsize, trans):
        artists = []

        # 마커 (왼쪽)
        if self.marker is not None:
            marker = Line2D(
                [xdescent + width * 0.25], [ydescent + height / 2],
                marker=self.marker,
                markersize=28,
                markerfacecolor=self.color,
                markeredgecolor='black',
                linestyle='None',
                transform=trans
            )
            artists.append(marker)

        # 패치 (오른쪽)
        patch = Rectangle(
            (xdescent + width * 0.65, ydescent + height * -0.1),  # 위치 약간 위로
            width * 0.9,                                        # 가로 길이 증가
            height * 1.1,                                        # 높이 증가
            facecolor=self.color,
            edgecolor='black',
            hatch=self.hatch,
            transform=trans
        )
        artists.append(patch)

        return artists

# --- 핸들 & 핸들러 등록 ---
custom_handles = {}
custom_handler_map = {}

for i, algo in enumerate(algo_order):
    label = algorithm_labels[algo]
    marker = algo_marker_map.get(algo)  # 없는 경우 None
    color = algo_colors[algo]
    hatch = hatch_patterns[i]

    dummy_handle = object()
    custom_handles[label] = dummy_handle
    custom_handler_map[dummy_handle] = MarkerPatchHandler(marker=marker, color=color, hatch=hatch)

# --- 플롯 생성 ---
fig, ax = plt.subplots(figsize=(16, 1))
ax.axis('off')

fig.legend(
    handles=list(custom_handles.values()),
    labels=list([k.replace('_', '-') for k in custom_handles.keys()]),
    loc='upper center',
    ncol=len(custom_handles),
    fontsize=font_size - 2,
    frameon=True,
    edgecolor='black',
    handletextpad=1.5,
    columnspacing=1.2,          # <-- 살짝 키움
    labelspacing=0.8,           # <-- 위아래 줄 간격 (여기선 큰 영향 없음)
    borderaxespad=0.5, 
    handler_map=custom_handler_map
)

plt.tight_layout()
plt.savefig('comparison-legend.pdf', dpi=300, bbox_inches='tight')
plt.show()


# ## UNUSED

# In[15]:


plt.rcParams['font.family'] = 'SUIT'

# x축 레이블 생성
x_labels = [f"{row['pods']}-{row['cpu']}-{row['mem']}" for _, row in comparison_df[comparison_df['algorithm'] == 'golden'].iterrows()]

# spotkube 알고리즘 제외
# comparison_df = comparison_df[comparison_df['algorithm'] != 'spotkube']

# 각 알고리즘별로 데이터 추출
algorithms = comparison_df['algorithm'].unique()
plt.figure(figsize=(12, 8))


# 그레이스케일 색상 설정
colors = ['black', 'gray', 'darkgray', 'lightgray', 'blue']
markers = ['*', 'o', 's', '^', 'x']

# 각 알고리즘별로 점 찍기
for i, algo in enumerate(algorithms):
    algo_data = comparison_df[comparison_df['algorithm'] == algo]
    plt.scatter(x_labels, algo_data['cost_ratio'], 
                marker=markers[i], 
                color=colors[i],
                s=200 if algo != 'golden' else 400,  # 점 크기 증가
                label=algo)

# 1.0 기준선 추가
plt.axhline(y=1.0, color='black', linestyle='--', linewidth=1)

plt.xticks(rotation=45, fontsize=18)
plt.xlabel('Pods-CPU-Memory', fontsize=18)
plt.ylabel('Cost Ratio (baseline = 1.0)', fontsize=18)
plt.title('Cost Ratio Comparison by Algorithm', fontsize=18)
plt.legend(fontsize=18)
plt.grid(False)
plt.tight_layout()
# plt.savefig('comparison-related-work-cost.pdf', format="pdf", dpi=300, bbox_inches='tight')


plt.show()


# In[16]:


# plt.rcParams['font.family'] = 'SUIT'

# # x축 레이블 생성
# x_labels = [f"{row['pods']}-{row['cpu']}-{row['mem']}" for _, row in comparison_df[comparison_df['algorithm'] == 'golden'].iterrows()]

# # 각 알고리즘별로 데이터 추출 (sv_pod 제외)
# algorithms = [algo for algo in comparison_df['algorithm'].unique()]
# plt.figure(figsize=(12, 8))

# # 그레이스케일 색상 설정
# colors = ['black', 'gray', 'darkgray', 'lightgray', 'blue']
# markers = ['*', 'o', 's', '^', 'x']

# # 각 알고리즘별로 점 찍기
# for i, algo in enumerate(algorithms):
#     algo_data = comparison_df[comparison_df['algorithm'] == algo]
#     plt.scatter(x_labels, algo_data['performance_ratio'], 
#                 marker=markers[i], 
#                 color=colors[i],
#                 s=200 if algo != 'golden' else 400,  # 점 크기 증가
#                 label=algo)

# # 1.0 기준선 추가
# plt.axhline(y=1.0, color='black', linestyle='--', linewidth=1)

# plt.xticks(rotation=45, fontsize=18)
# plt.xlabel('Pods-CPU-Memory', fontsize=18)
# plt.ylabel('Efficiency Ratio (baseline = 1.0)', fontsize=18)
# plt.title('Efficiency Ratio Comparison by Algorithm', fontsize=18)
# plt.legend(fontsize=18)
# plt.grid(False)
# plt.tight_layout()
# plt.show()


# In[17]:


# plt.rcParams['font.family'] = 'SUIT'

# # x축 레이블 생성
# x_labels = [f"{row['pods']}-{row['cpu']}-{row['mem']}" for _, row in comparison_df[comparison_df['algorithm'] == 'golden'].iterrows()]

# # 각 알고리즘별로 데이터 추출 (sv_pod 제외)
# algorithms = [algo for algo in comparison_df['algorithm'].unique() if algo != 'sv_pod']
# plt.figure(figsize=(15, 8))

# # 그레이스케일 색상 설정
# colors = ['black', 'gray', 'darkgray', 'blue']
# markers = ['*', 'o', 's', 'x']

# # 각 알고리즘별로 점 찍기
# for i, algo in enumerate(algorithms):
#     algo_data = comparison_df[comparison_df['algorithm'] == algo]
#     plt.scatter(x_labels, algo_data['performance_ratio'], 
#                 marker=markers[i], 
#                 color=colors[i],
#                 s=200 if algo != 'golden' else 400,  # 점 크기 증가
#                 label=algo)

# # 1.0 기준선 추가
# plt.axhline(y=1.0, color='black', linestyle='--', linewidth=1)

# plt.xticks(rotation=45, fontsize=18)
# plt.xlabel('Pods-CPU-Memory', fontsize=18)
# plt.ylabel('Performance Ratio (baseline = 1.0)', fontsize=18)
# plt.title('Performance Ratio Comparison by Algorithm', fontsize=18)
# plt.legend(fontsize=18)
# plt.grid(False)
# plt.tight_layout()
# plt.show()


# In[18]:


merged_dfs['greedy'].groupby(['pods', 'cpu', 'mem']).agg({
    'cost': 'mean',
    'efficiency': 'mean'
}).reset_index()


# In[19]:


merged_dfs['sv_node'].groupby(['pods', 'cpu', 'mem']).agg({
    'cost': 'mean',
    'efficiency': 'mean'
}).reset_index()


# In[20]:


merged_dfs['sv_pod'].groupby(['pods', 'cpu', 'mem']).agg({
    'cost': 'mean',
    'efficiency': 'mean'
}).reset_index()


# In[ ]:




