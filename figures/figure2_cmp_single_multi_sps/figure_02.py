#!/usr/bin/env python
# coding: utf-8

# In[2]:


import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import math
from usualfunc import *


plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42

# off warning

import warnings

# FutureWarning을 무시
warnings.filterwarnings("ignore", category=FutureWarning)
# DeprecationWarning 무시
warnings.filterwarnings("ignore", category=DeprecationWarning)
# SettingWithCopyWarning 무시
# warnings.filterwarnings("ignore", category=pd.errors.SettingWithCopyWarning)

pd.options.mode.chained_assignment = None  # 'warn'에서 None으로 변경하여 경고 비활성화

SUCCESS_CODE = {"pending-fulfillment", "fulfilled"}
def codetobin(instr):
    if instr in SUCCESS_CODE:
        return 1
    return 0

def count_suc(group):
    return (group['Code'].str.contains('success', case=False, na=False)).sum()
def getSpotName(inp):
    return eval(inp)[0]['resourceName']
def dddCode(inp):
    return 1 if inp=="success" else 0
def isBetween(sts, ets, tts):
    return sts <= tts <= ets


# In[4]:


iDict = {
"c6i.large_us-east-1f":50,
"c7gn.large_us-east-1b":25,
"m3.large_us-east-1e":1,
"c6a.large_us-west-2b":50,
"c7i.large_us-west-2a":25,
"c7gn.large_us-west-2d":1,
"m6g.large_ap-northeast-1a":50,
"r7i.large_ap-northeast-1d":25,
"r5a.large_ap-northeast-1d":1,
"c6a.large_eu-west-1c":50,
"c7a.large_eu-west-1a":25,
"c6gd.large_eu-west-1a":1,
 }

dddPath = "./data/ddd.csv"

dddDF = pd.read_csv(dddPath)
dddDF = dddDF.sort_values(by="Timestamp")
dddDF['DDDRequestTime'] = pd.to_datetime(dddDF['DDDRequestTime'], unit="s", utc=True)

dddDF["iName"]=(dddDF["InstanceType"]+"_"+dddDF["AZ"])
dddDF["iName"] = dddDF["iName"].apply(lambda x: str(iDict.get(x, "Unknown")) + "_" + str(x))
dddDF = dddDF[~dddDF["iName"].str.startswith("25")]
dddDF["Region"] = dddDF["AZ"].str[:-1]

regions = [
    "us-west-2",
    "us-east-1",
    "ap-northeast-1",
    "eu-west-1"
]

region_names = {
    "us-west-2": "Oregon",
    "us-east-1": "N. Virginia",
    "ap-northeast-1": "Tokyo",
    "eu-west-1": "Ireland"
}

# 플롯 설정
num_plots = len(regions)
cols = 2
rows = math.ceil(num_plots / cols)
fig, axes = plt.subplots(rows, cols, figsize=(14.5, rows * 3), sharex=True, sharey=False)
axes = axes.flatten()

# 전역 폰트 설정
font_size = 24
font_family = 'Roboto'

plt.rcParams['font.family'] = font_family
plt.rcParams['font.size'] = font_size
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False


for n, i in enumerate(regions):
    dddidf = dddDF[dddDF["Region"] == i]

    # 시작 시간과 끝 시간 설정
    start_time = dddidf.iloc[1]['DDDRequestTime']
    end_time = dddidf.iloc[-2]['DDDRequestTime']

    result = dddidf.groupby(['iName', 'DDDRequestTime']).apply(count_suc).reset_index(name='success_count')
    result['success_count'] = result['success_count'].fillna(0).astype(int)
    result = result.sort_values(by="DDDRequestTime")

    result["success_count"] = result["success_count"].clip(upper=50)

    window_size = 4
    result['smoothed_count'] = result.groupby('iName')['success_count'].transform(
        lambda x: x.rolling(window=window_size, min_periods=1).mean()
    )
    ax = axes[n]
    # ax.set_title(f"{n+1}. {i}", fontsize=20)
    label = region_names[i]
    if n == 2:
        ax.text(0.49, 0.385, f"{label} ({i})",
            fontsize=font_size-3, ha='center', va='center',
            transform=ax.transAxes, alpha=0.8)
    else:
        ax.text(0.5, 0.385, f"{label} ({i})",
            fontsize=font_size-3, ha='center', va='center',
            transform=ax.transAxes, alpha=0.8)

    instlist = list(set(result["iName"]))
    instlist.sort(reverse=True)

    for inst in instlist:
        tmp = result[result["iName"] == inst]
        label = None
        if inst.startswith("50"):
            label = "Instances retaining SPS 3 at 50 nodes"
            ax.step(tmp["DDDRequestTime"], tmp["smoothed_count"], where='post',
                    label=label if n == 0 else None, linewidth=3, color='black')
        elif inst.startswith("1"):
            label = "Instances retaining SPS 3 at 1 node"
            ax.step(tmp["DDDRequestTime"], tmp["smoothed_count"], where='post',
                    label=label if n == 0 else None, linewidth=1.5, linestyle=':', color='black')


    if n == 0:
        ax.legend(
        loc='upper left',
        bbox_to_anchor=(0.0, 0.97),  # x, y 좌표: y=1.0이 완전 위쪽, y=0.85로 살짝 아래
        fontsize=font_size-6,
        frameon=True,
        edgecolor="black"
    )

    if n in [0, 2]:
        ax.set_yticks([0, 10, 20, 30, 40, 50])
        ax.tick_params(axis='y', labelsize=font_size)
    #     ax.set_ylabel("Fulfilled Instances", fontsize=20)
    else:
        ax.set_yticks([])  # y축 눈금 제거

    if n in [2, 3]:
        # 눈금 위치: 3시간 간격
        tick_locs = pd.date_range(start=start_time, end=end_time, freq='6h')
        ax.set_xticks(tick_locs)
        # ax.set_xlabel("Elapsed Time", fontsize=font_size)

        # 각 눈금에 대해 start_time으로부터의 시간 차 계산
        tick_labels = [(t - start_time).total_seconds() / 3600 for t in tick_locs]
        tick_labels = [f"{int(h)}" for h in tick_labels]

        ax.set_xticklabels(tick_labels, fontsize=font_size)
    else:
        ax.set_xticks([])  # 상단 subplot은 눈금 제거
        ax.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)

    # x축 눈금 제거
    # ax.set_xticks([])
    # x축 범위 설정
    ax.set_xlim(start_time, end_time)
    ax.set_ylim(-2, 52)

fig.text(0.06, 0.5, 'Fulfilled Spot Requests (out of 50)', va='center', rotation='vertical', fontsize=font_size)
fig.text(0.5, 0, 'Elapsed Time (hours)', va='center', ha='center', fontsize=font_size)

plt.subplots_adjust(wspace=0.1, hspace=0.15)
# plt.tight_layout()
plt.show()
# plt.show()
fig.savefig("multiple-nodes-sps-real-availability.pdf", format="pdf", bbox_inches='tight')


# In[ ]:




