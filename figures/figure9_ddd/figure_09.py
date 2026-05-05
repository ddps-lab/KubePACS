#!/usr/bin/env python
# coding: utf-8

# In[2]:


import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42


# In[3]:


targets = pd.read_csv('data/targets.csv')


# In[4]:


targets


# In[5]:


targets['T3'] = targets['T3'].astype(int).astype(str)
targets['key'] = targets['InstanceType'] + '_' + targets['AZ'] + '_' + (targets['T3'])


# In[6]:


dddDF = pd.read_csv('data/spot_result.csv')


# In[7]:


def codeToBin(code):
    if code == "success":
        return 1
    else:
        return 0

dddDF.loc[:,"bincode"] = dddDF["Code"].apply(codeToBin)
dddDF


# In[8]:


dddDF['DDDRequestTime'] = pd.to_datetime(dddDF['DDDRequestTime'], unit='s', utc=True)


dddDF_grouped = dddDF.groupby(['InstanceType', 'AZ', 'DDDRequestTime'], as_index=False)['bincode'].sum()
dddDF_grouped.sort_values(by='DDDRequestTime', inplace=True)
dddDF_grouped


# In[9]:


actualDDD = dddDF_grouped[:len(dddDF_grouped)-4]
actualDDD


# In[10]:


def toRegion(az):
    return az[:-1]


# In[11]:


actualDDD.loc[:,"Region"] = actualDDD["AZ"].apply(toRegion)
actualDDD


# In[12]:


order = ["us-east-1", "us-west-2", "ap-northeast-1", "eu-west-1"]
region_dfs = [targets[targets['Region'] == region] for region in order]


# In[13]:


result_df = pd.DataFrame(columns=region_dfs[0].columns)

for region in order:
    merged_df = pd.merge(actualDDD[actualDDD['Region']==region].reset_index(drop=True), 
                     targets[targets['Region']==region].reset_index(drop=True), 
                     left_index=True, right_index=True)
    result_df = pd.concat([result_df, merged_df])
result_df["T3"] = result_df["T3"].astype(int)


# In[14]:


import seaborn as sns

plt.figure(figsize=(10, 6))
sns.boxplot(x='T3', y='bincode', data=result_df)  # ci=None: 신뢰구간 생략
plt.title('Average Success by T3', fontsize=18)
plt.xlabel('T3', fontsize=18)
plt.ylabel('Average Success', fontsize=18)
plt.show()


# In[15]:


plt.figure(figsize=(10, 6))
sns.barplot(x='T3', y='bincode', data=result_df, errorbar=None)  # ci=None: 신뢰구간 생략
plt.title('Average Success by T3', fontsize=18)
plt.xlabel('T3', fontsize=18)
plt.ylabel('Average Success', fontsize=18)
plt.show()


# In[27]:


font_size = 30
font_family = 'Roboto'

plt.rcParams['font.family'] = font_family
plt.rcParams['font.size'] = font_size
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False

# 고유 T3 개수만큼 색상 생성
result_df['T3_str'] = result_df['T3'].astype(str)
unique_t3 = result_df['T3_str'].unique()
palette = sns.color_palette("husl", len(unique_t3))

# 팔레트를 직접 지정
plt.figure(figsize=(14, 7.5))
sns.violinplot(
    x='T3',
    y='bincode',
    data=result_df,
    bw_adjust=0.66,
    hue='T3_str',   
    palette=dict(zip(unique_t3, palette)),
    legend=False
)

plt.xlabel('T3 Value of Each Requested Instance Type', labelpad=5, fontsize=font_size-1.7)
ax = plt.gca()
ax.set_ylabel('Number of Fulfilled Nodes (out of 50)', labelpad=5, fontsize=font_size-1.7)
ax.yaxis.set_label_coords(-0.05, 0.44)
plt.ylim(0, 51)

plt.tight_layout()
plt.savefig('t3-values-to-successful-requests-count.pdf', format="pdf", dpi=300, bbox_inches='tight')
plt.show()


# In[ ]:




