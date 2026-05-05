#!/usr/bin/env python
# coding: utf-8

# In[16]:


import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import os
import seaborn as sns

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42


# In[17]:


# result 폴더 내의 모든 하위 폴더 목록 가져오기
result_dir = "./data"
result_folders = sorted([f for f in os.listdir(result_dir) if os.path.isdir(os.path.join(result_dir, f))])


# In[18]:


result_folders


# In[19]:


filenames = {"0.1": "golden_section_tolerance_0.1_summary.csv",
"0.01": "golden_section_tolerance_0.01_summary.csv",
"0.001": "golden_section_tolerance_0.001_summary.csv",
"0.0001": "golden_section_tolerance_0.0001_summary.csv"
}

# 각 폴더의 CSV 파일을 읽어와서 병합하기
merged_df = pd.DataFrame()

for folder in result_folders:
    for unit in filenames.keys():
        file_path = os.path.join(result_dir, folder, filenames[unit])
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            df['folder'] = folder
            df['unit'] = unit
            merged_df = pd.concat([merged_df, df], ignore_index=True)



# In[20]:


merged_df["efficiency"] = merged_df["performance"] / (merged_df["cost"]*merged_df["actual_pods"])


# In[21]:


merged_df


# In[22]:


# unit이 0.0001인 행의 efficiency를 기준으로 정규화하기
def normalize_efficiency(df):
    # groupby를 사용하여 folder, pods, cpu, mem이 같은 그룹을 찾기
    grouped = df.groupby(['folder', 'pods', 'cpu', 'mem'])

    # 각 그룹에 대해 정규화 수행
    for name, group in grouped:
        # unit이 0.0001인 행의 efficiency 값 가져오기
        base_efficiency = group[group['unit'] == '0.0001']['efficiency'].values
        if len(base_efficiency) > 0:
            base_efficiency = base_efficiency[0]
            # 해당 그룹의 모든 행의 efficiency를 base_efficiency로 나누어 정규화
            df.loc[group.index, 'efficiency'] = group['efficiency'] / base_efficiency

normalize_efficiency(merged_df)
merged_df


# In[23]:


merged_df[merged_df["execution_time"]>10]


# In[24]:


print(len(merged_df[(merged_df['efficiency']<1)&(merged_df['unit']!='0.1')]))
merged_df[(merged_df['efficiency']<1)&(merged_df['unit']!='0.1')]


# In[25]:


print(len(merged_df[(merged_df['efficiency']<1)&(merged_df['unit']=='0.1')]))
print(merged_df[(merged_df['efficiency']<1)&(merged_df['unit']=='0.1')]['efficiency'].min())
merged_df[(merged_df['efficiency']<1)&(merged_df['unit']=='0.1')]


# In[26]:


merged_df[merged_df["unit"]=="0.01"]["execution_time"].max()


# In[29]:


# 유닛 리스트 정의
units = ["0.1", "0.01", "0.001", "0.0001"]

# 평균 실행시간 계산
mean_execution_time = merged_df.groupby('unit')['execution_time'].mean()

# efficiency가 1 미만인 데이터 필터링 (boxplot용)
filtered_data = merged_df.copy()

plt.figure(figsize=(14, 6.5))
font_size = 30
font_family = 'Roboto'

plt.rcParams['font.family'] = font_family
plt.rcParams['font.size'] = font_size
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False


# 순서 뒤집힌 유닛 리스트
rev_units = units[::-1]  # ["0.0001","0.001","0.01","0.1"]
# 평균 실행시간도 같은 순서로 재정렬
mean_exec_rev = mean_execution_time.reindex(rev_units)

# 1) ax1(primary): 실행시간
ax1 = plt.gca()
sns.barplot(
    x=mean_exec_rev.index,
    y=mean_exec_rev.values,
    order=rev_units,
    alpha=1.0,
    color='darkgray',
    ax=ax1,
    width=0.6,
    zorder=1
)
ax1.set_xlabel('Tolerance of Alpha', labelpad=5)
ax1.set_ylabel('Mean Execution Time (s)', labelpad=5)
ax1.set_yticks([0, 1000, 2000, 3000, 4000])
ax1.set_yticklabels([f'{x/1000:.1f}' for x in ax1.get_yticks()])

# ax1.tick_params(axis='x', labelsize=18)
# ax1.tick_params(axis='y', labelsize=18)

# 2) ax2(secondary): 효율성
ax2 = ax1.twinx()
sns.boxplot(
    x='unit',
    y='efficiency',
    data=filtered_data,
    order=rev_units,
    ax=ax2,
    linewidth=3,
    zorder=2,
    width=0.8,
    flierprops={'marker': 'o', 'markersize': 6, 'markerfacecolor': 'none'}
)
ax1.set_ylim(0, 4101)

# ax2.set_ylabel('Nodepool Efficiency', labelpad=5)
ax2.set_ylabel(r'Normalized Efficiency', labelpad=5)
ax2.set_yticks([0.50, 0.60, 0.70, 0.80, 0.90, 1.00])
ax2.set_yticklabels(['x0.5', 'x0.6', 'x0.7', 'x0.8', 'x0.9', 'x1.0'])
ax2.set_ylim(0.5, 1.01)
ax2.tick_params(axis='y')

# legend
legend_patch = Patch(facecolor='darkgray', label='Execution Time')
ax1.legend(handles=[legend_patch], loc='lower right', fontsize=font_size-2,
            handletextpad=0.1, markerscale=1.5, edgecolor='black', borderpad=0.3)
plt.tight_layout()

plt.savefig('impact-of-alpha-spacing.pdf', dpi=300, bbox_inches='tight')
plt.show()


# In[14]:


# 각 unit별 데이터 개수 확인
print("각 unit별 데이터 개수:")
print(filtered_data['unit'].value_counts().sort_index())


# In[ ]:





# In[ ]:





# In[ ]:





# In[ ]:





# In[ ]:




