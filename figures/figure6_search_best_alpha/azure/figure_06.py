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


# result 폴더 내의 모든 하위 폴더 목록 가져오기
result_dir = "./data"
result_folders = sorted([f for f in os.listdir(result_dir) if os.path.isdir(os.path.join(result_dir, f))])


# In[3]:


result_folders

# In[4]:


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

# In[5]:


import os
import pandas as pd
import numpy as np
from matplotlib.ticker import FuncFormatter, MultipleLocator

# ===== 기본 설정 =====
font_size = 30
font_family = 'roboto'

plt.rcParams['font.family'] = font_family
plt.rcParams['font.size'] = font_size
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False

# ===== 경로 및 파일 설정 =====
result_dir = "./data"
result_folders = sorted([f for f in os.listdir(result_dir) if os.path.isdir(os.path.join(result_dir, f))])
golden_summaryfile = "experiment_summary.csv"

# ===== 워크로드 및 메트릭 설정 =====
cpu_mem_list = [(1, 2), (1, 4), (2, 2)]
metrics = ["E_total"]

fig, axes = plt.subplots(1, len(cpu_mem_list), figsize=(14, 8), sharex=True)
axes = np.atleast_1d(axes)  # <- 항상 배열로 변환하여 TypeError 방지

row_y_lim = (-250000, 6e6)  # y축 고정: 0 ~ 6M

# ===== 플롯 =====
for col_idx, (cpu_val, mem_val) in enumerate(cpu_mem_list):
    for i in range(len(result_folders)):
        golden_summary_path = os.path.join(result_dir, result_folders[i], golden_summaryfile)
        summary_df = pd.read_csv(golden_summary_path)

        for pods_val in [10, 50, 100, 400, 1000]:
            filtered_df = summary_df[
                (summary_df['pods'] == pods_val) &
                (summary_df['cpu'] == cpu_val) &
                (summary_df['mem'] == mem_val)
            ]
            if filtered_df.empty:
                continue
            row = filtered_df.iloc[0]
            best_alpha = row['alpha']
            # print(best_alpha)

            brute_summary_path = os.path.join(
                result_dir, result_folders[i], "specific_result", f"result_{pods_val}_{cpu_val}_{mem_val}.csv"
            )
            brute_summary_df = pd.read_csv(brute_summary_path)

            brute_summary_df["E_perf-cost"] = brute_summary_df["perf_per_cost"]
            brute_summary_df["E_over-alloc"] = pods_val / brute_summary_df["actual_pods"]
            brute_summary_df["E_total"] = brute_summary_df["E_perf-cost"] * brute_summary_df["E_over-alloc"]

            ax = axes[col_idx]
            ax.plot(brute_summary_df["alpha"], brute_summary_df["E_total"], color='black', alpha=0.3)

            truncated_alpha = np.floor(best_alpha * 100) / 100
            match_df = brute_summary_df[brute_summary_df["alpha"].round(4) == truncated_alpha]

            if not match_df.empty:
                best_value = match_df["E_total"].values[0]
                ax.scatter(truncated_alpha, best_value,
                           color='yellow', edgecolor='black', marker='*', s=400, zorder=5, alpha=0.5)

# ===== y축 포매터 =====
def million_formatter(x, pos):
    if x == 0:
        return '0'
    return f'{int(x / 1e6)}M'

# ===== 축 설정 =====
for col_idx, ax in enumerate(axes):
    ax.set_ylim(row_y_lim)
    ax.set_xlim(-0.02, 1.1)

    ax.yaxis.set_major_locator(MultipleLocator(2e6))  # 1M 간격으로 눈금 설정
    ax.yaxis.set_major_formatter(FuncFormatter(million_formatter))

    if col_idx == 0:
        # ax.set_ylabel(r'Configured Node Pool $E_{total}$', fontsize=font_size, labelpad=5)
        ax.set_ylabel(r'Overall efficiency ($E_{\mathrm{Total}}$)', fontsize=font_size, labelpad=5)
    else:
        ax.set_yticklabels([])

    # y축 눈금(tick)만 숨기고 값은 유지
    ax.tick_params(axis='y', length=0)

    ax.set_xticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xticklabels(["0.0", "0.2", "0.4", "0.6", "0.8", "1.0"])
    if col_idx == 1:
        ax.set_xlabel("Alpha", labelpad=5)

# ===== 타이틀 및 범례 =====
for col_idx, (cpu_val, mem_val) in enumerate(cpu_mem_list):
    axes[col_idx].set_title(fr'$Req_{{cpu}}$={cpu_val}, $Req_{{mem}}$={mem_val}', fontsize=font_size-2)

star_legend = plt.Line2D([0], [0], marker='*', color='yellow',
                         markerfacecolor='yellow', markeredgecolor='black',
                         markersize=24, linestyle='None', alpha=1.0)
# 검은 실선(Explored Alpha)과 별(최적 Alpha) 범례를 모두 추가하고, 위아래로 간격을 둡니다.
explored_line_legend = plt.Line2D([0], [0], color='black', linestyle='-', linewidth=2)
axes[-1].legend(
    [explored_line_legend, star_legend],
    ["Each\nExperiment", "Searched\nBest Alpha"],
    loc='upper right',
    handletextpad=0.5,  # 마커와 텍스트 사이 간격 조정
    borderpad=0.2,
    labelspacing=0.8,  # 위아래 간격을 넓힘
    handlelength=1,  # 첫 번째 마커(선)의 너비를 줄임
    borderaxespad=0.5,
    edgecolor='black',
    fontsize=font_size
)



fig.subplots_adjust(left=0.07, right=0.98, top=0.88, bottom=0.2, wspace=0.1)

# ===== 저장 및 출력 =====
plt.savefig('distribution-of-alphas-to-workloads-azure.pdf', format="pdf", dpi=300, bbox_inches='tight')
plt.show()


# In[6]:


import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MultipleLocator

# ===== 기본 설정 =====
font_size = 30
font_family = 'roboto'

plt.rcParams['font.family'] = font_family
plt.rcParams['font.size'] = font_size
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False

# ===== 경로 및 파일 설정 =====
result_dir = "./data"
result_folders = sorted([f for f in os.listdir(result_dir) if os.path.isdir(os.path.join(result_dir, f))])
golden_summaryfile = "experiment_summary.csv"

# ===== 워크로드 및 메트릭 설정 =====
cpu_mem_list = [(1, 2), (1, 4), (2, 2)]
metrics = ["E_total"]

fig, axes = plt.subplots(1, len(cpu_mem_list), figsize=(14, 6), sharex=True)
axes = np.atleast_1d(axes)  # <- 항상 배열로 변환하여 TypeError 방지

row_y_lim = (-250000, 6e6)  # y축 고정: 0 ~ 6M

# ===== 플롯 =====
for col_idx, (cpu_val, mem_val) in enumerate(cpu_mem_list):
    for i in range(len(result_folders)):
        golden_summary_path = os.path.join(result_dir, result_folders[i], golden_summaryfile)
        summary_df = pd.read_csv(golden_summary_path)

        for pods_val in [10, 50, 100, 400, 1000]:
            filtered_df = summary_df[
                (summary_df['pods'] == pods_val) &
                (summary_df['cpu'] == cpu_val) &
                (summary_df['mem'] == mem_val)
            ]
            if filtered_df.empty:
                continue
            row = filtered_df.iloc[0]
            best_alpha = row['alpha']
            # print(best_alpha)

            brute_summary_path = os.path.join(
                result_dir, result_folders[i], "specific_result", f"result_{pods_val}_{cpu_val}_{mem_val}.csv"
            )
            brute_summary_df = pd.read_csv(brute_summary_path)

            brute_summary_df["E_perf-cost"] = brute_summary_df["perf_per_cost"]
            brute_summary_df["E_over-alloc"] = pods_val / brute_summary_df["actual_pods"]
            brute_summary_df["E_total"] = brute_summary_df["E_perf-cost"] * brute_summary_df["E_over-alloc"]

            ax = axes[col_idx]
            ax.plot(brute_summary_df["alpha"], brute_summary_df["E_total"], color='black', alpha=0.3)

            truncated_alpha = np.floor(best_alpha * 100) / 100
            match_df = brute_summary_df[brute_summary_df["alpha"].round(4) == truncated_alpha]

            if not match_df.empty:
                best_value = match_df["E_total"].values[0]
                ax.scatter(truncated_alpha, best_value,
                           color='yellow', edgecolor='black', marker='*', s=400, zorder=5, alpha=0.5)

# ===== y축 포매터 =====
def million_formatter(x, pos):
    if x == 0:
        return '0'
    return f'{int(x / 1e6)}M'

# ===== 축 설정 =====
for col_idx, ax in enumerate(axes):
    ax.set_ylim(row_y_lim)
    ax.set_xlim(-0.02, 1.1)

    ax.yaxis.set_major_locator(MultipleLocator(2e6))  # 1M 간격으로 눈금 설정
    ax.yaxis.set_major_formatter(FuncFormatter(million_formatter))

    if col_idx == 0:
        pass
        # ax.set_ylabel(r'Overall efficiency ($E_{\mathrm{Total}}$)', fontsize=font_size, labelpad=5)
    else:
        ax.set_yticklabels([])

    # y축 눈금(tick)만 숨기고 값은 유지
    ax.tick_params(axis='y', length=0)
    ax.set_yticks([])

    ax.set_xticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xticklabels(["0.0", "0.2", "0.4", "0.6", "0.8", "1.0"])
    if col_idx == 1:
        ax.set_xlabel("Alpha", labelpad=5)

# ===== 타이틀 및 범례 =====
for col_idx, (cpu_val, mem_val) in enumerate(cpu_mem_list):
    axes[col_idx].set_title(fr'$Req_{{cpu}}$={cpu_val}, $Req_{{mem}}$={mem_val}', fontsize=font_size-2)

star_legend = plt.Line2D([0], [0], marker='*', color='yellow',
                         markerfacecolor='yellow', markeredgecolor='black',
                         markersize=24, linestyle='None', alpha=1.0)
# 검은 실선(Explored Alpha)과 별(최적 Alpha) 범례를 모두 추가하고, 위아래로 간격을 둡니다.
explored_line_legend = plt.Line2D([0], [0], color='black', linestyle='-', linewidth=2)
axes[-1].legend(
    [explored_line_legend, star_legend],
    ["Each\nExperiment", "Searched\nBest Alpha"],
    loc='upper right',
    handletextpad=0.5,  # 마커와 텍스트 사이 간격 조정
    borderpad=0.2,
    labelspacing=0.4,  # 위아래 간격을 넓힘
    handlelength=1,  # 첫 번째 마커(선)의 너비를 줄임
    borderaxespad=0.2,
    edgecolor='black',
    fontsize=font_size
)



fig.subplots_adjust(left=0.07, right=0.98, top=0.88, bottom=0.2, wspace=0.1)

# ===== 저장 및 출력 =====
plt.savefig('distribution-of-alphas-to-workloads-azure-short.pdf', format="pdf", dpi=300, bbox_inches='tight')
plt.show()


# In[7]:


# 모든 (파일, 시나리오)별로 alpha=0.0일 때 E_total과 best_alpha의 E_total을 정리
comparison_data = []

for result_folder in result_folders:
    golden_summary_path = os.path.join(result_dir, result_folder, golden_summaryfile)
    if not os.path.exists(golden_summary_path):
        continue
    
    golden_df = pd.read_csv(golden_summary_path)
    
    # 각 시나리오(pods, cpu, mem 조합)별로 처리
    scenarios = golden_df.groupby(['pods', 'cpu', 'mem'])
    
    for (pods, cpu, mem), scenario_row in scenarios:
        # specific_result 파일에서 brute force 결과 가져오기
        specific_path = os.path.join(
            result_dir, result_folder, "specific_result", f"result_{int(pods)}_{int(cpu)}_{int(mem)}.csv"
        )
        if not os.path.exists(specific_path):
            continue
        
        specific_df = pd.read_csv(specific_path)
        
        # E_total 계산: perf_per_cost * (pods / actual_pods)
        specific_df = specific_df.copy()
        specific_df['E_perf_cost'] = specific_df['perf_per_cost']
        specific_df['E_over_alloc'] = pods / specific_df['actual_pods']
        specific_df['E_total'] = specific_df['E_perf_cost'] * specific_df['E_over_alloc']
        
        # alpha=0.0일 때의 E_total
        alpha_zero_row = specific_df[specific_df['alpha'] == 0.0]
        if not alpha_zero_row.empty:
            e_total_alpha_zero = alpha_zero_row['E_total'].values[0]
        else:
            e_total_alpha_zero = None
        
        # best_alpha (E_total이 최대인 alpha)
        best_idx = specific_df['E_total'].idxmax()
        best_alpha = specific_df.loc[best_idx, 'alpha']
        e_total_best_alpha = specific_df.loc[best_idx, 'E_total']
        
        comparison_data.append({
            'result_folder': result_folder,
            'pods': pods,
            'cpu': cpu,
            'mem': mem,
            'alpha_zero_E_total': e_total_alpha_zero,
            'best_alpha': best_alpha,
            'best_alpha_E_total': e_total_best_alpha,
            'improvement_ratio': (e_total_best_alpha / e_total_alpha_zero) if e_total_alpha_zero else None
        })

comparison_df = pd.DataFrame(comparison_data)


print(comparison_df)
print(f"\n평균 improvement_ratio: {comparison_df['improvement_ratio'].mean():.6f}")
print(f"최대 improvement_ratio: {comparison_df['improvement_ratio'].max():.6f}")


# In[ ]:



