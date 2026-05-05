#!/usr/bin/env python
# coding: utf-8

# In[6]:


import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib as mpl
import numpy as np
import pandas as pd
import glob
import os
import re

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42


# ### 데이터 적재

# In[7]:


RESULT_PATH = "./data"

# RESULT_PATH 하위의 모든 golden_section_summary.csv 파일 찾기
csv_files = glob.glob(os.path.join(RESULT_PATH, "**", "golden_section_summary.csv"), recursive=True)

# 모든 CSV 파일을 읽어서 하나의 DataFrame으로 합치기
df_list = []
for file in csv_files:
    df_temp = pd.read_csv(file)
    df_list.append(df_temp)

df = pd.concat(df_list, ignore_index=True)

df


# ### 데이터 분류

# In[8]:


# 인스턴스 옵션 추출
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


# 각 노드풀의 인스턴스 타입 옵션 분석을 위한 함수
def analyze_nodepool_options(nodepool_config):
    total_instances = 0
    option_counts = {
        'network': 0,
        'disk': 0, 
        'disk_network': 0,
        'general': 0
    }

    for node in nodepool_config:
        instance_family = node['instance_type'].split('.')[0]  # 예: c6gd -> c6g
        _, option = extract_base_and_option(instance_family)

        # 옵션에 따른 분류
        if 'd' in option and 'n' in option:
            option_counts['disk_network'] += 1
        elif 'n' in option:
            option_counts['network'] += 1
        elif 'd' in option:
            option_counts['disk'] += 1
        else:
            option_counts['general'] += 1

        total_instances += 1

    # 비율 계산
    ratios = {
        f'ratio_{key}': count/total_instances 
        for key, count in option_counts.items()
    }

    return ratios

# 데이터프레임의 각 행에 대해 비율 계산
ratios_list = []
for _, row in df.iterrows():
    nodepool_config = eval(row['nodepool_config'])  # 문자열을 리스트로 변환
    ratios = analyze_nodepool_options(nodepool_config)
    ratios_list.append(ratios)

# 비율 컬럼 추가
ratio_df = pd.DataFrame(ratios_list)
df = pd.concat([df, ratio_df], axis=1)


# In[9]:


df


# ### 시각화

# In[10]:


# y축 (아래가 Disk & Network, 위가 Default)
font_size = 30
font_family = 'Roboto'

plt.rcParams['font.family'] = font_family
plt.rcParams['font.size'] = font_size
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False


workload_intensities_to_plot = ['disk_network', 'disk', 'network', 'default']
y_labels = ['Disk &\nNetwork', 'Disk', 'Network', 'General']
y = np.arange(len(y_labels))

# Stack 구성 순서: General → Disk → Network → Disk & Network
component_labels = ['General', 'Disk', 'Network', 'Disk & Network']
colors = ['#DDDDDD', '#777777', '#AAAAAA', '#444444']
hatches = ['/', '.', '\\', 'x']

# column_mapping 예시 (이 부분은 이미 정의되어 있어야 함)
# 예: column_mapping = {'General': 'ratio_default', ...}
# 아래 코드를 실행하기 전에 column_mapping 과 grouped_ratios 는 정의되어 있어야 합니다.

column_mapping = {
    'General': 'ratio_general',
    'Network': 'ratio_network',
    'Disk': 'ratio_disk',
    'Disk & Network': 'ratio_disk_network'
}
grouped_ratios = df.groupby('workload_intensity')[['ratio_general', 'ratio_network', 'ratio_disk', 'ratio_disk_network']].mean()

# 데이터 구성
stack_data = []
for label in component_labels:
    col = column_mapping[label]
    values = [grouped_ratios.loc[i, col] if i in grouped_ratios.index else 0 for i in workload_intensities_to_plot]
    stack_data.append(values)

stack_data = np.array(stack_data)  # 역순 필요 없음

# 그리기
fig, ax = plt.subplots(figsize=(14, 7.5))
left = np.zeros(len(y))
bars = []

for i in range(len(component_labels)):
    bar = ax.barh(
        y, stack_data[i],
        left=left,
        color=colors[i],
        edgecolor='black',
        hatch=hatches[i],
        label=component_labels[i]
    )
    bars.append(bar)

    # 퍼센트 텍스트 추가
    for j in range(len(y)):
        value = stack_data[i][j]
        if value > 0.002:  # 0.2% 이상일 때만 표시
            ax.text(
                left[j] + value / 2,
                y[j],
                f'{value * 100:.1f}%',
                ha='center',
                va='center',
                fontsize=font_size - 4,
                color='black',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='gray', alpha=0.8),
            )

    left += stack_data[i]

# y축 설정
ax.set_yticks(y)
ax.set_yticklabels(y_labels)

# x축 비율
ax.set_xlim(0, 1.0)
ax.set_xlabel('Ratio', labelpad=5)

# 범례
legend_patches = [
    mpatches.Patch(facecolor=colors[i], hatch=hatches[i], edgecolor='black', label=component_labels[i])
    for i in range(len(component_labels))
]

ax.legend(
    handles=legend_patches,
    loc='upper center',
    ncol=4,
    frameon=True,
    bbox_to_anchor=(0.45, 1.25),
    handletextpad=0.4,
    columnspacing=1,
    edgecolor="black"
)

plt.tight_layout()
plt.savefig('network-disk-intensive-workload-stack.pdf', dpi=300, bbox_inches='tight')
plt.show()


# 

# 
