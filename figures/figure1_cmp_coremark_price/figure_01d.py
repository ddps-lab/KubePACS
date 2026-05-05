#!/usr/bin/env python
# coding: utf-8

# In[2]:


import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42


# In[3]:


coremark = pd.read_csv('../common/dataset/aws_coremark_singlecore.csv')


# In[4]:


coremark


# In[5]:


spot_price_url = "https://d26bk4799jlxhe.cloudfront.net/latest_data/latest_aws.json"
price_data = pd.read_json(spot_price_url)
price_data


# In[6]:


virginia_price = price_data[price_data['Region'] == 'us-east-1']
virginia_price.loc[:, 'OndemandPrice'] = virginia_price['OndemandPrice'].round(5)
virginia_price.loc[:, 'SpotPrice'] = virginia_price['SpotPrice'].round(5)
virginia_price = virginia_price[(~virginia_price['InstanceType'].str.contains('metal'))]
virginia_price['InstanceFamily'] = virginia_price['InstanceType'].str.split('.', expand=True)[0]


# In[7]:


virginia_price = virginia_price[['InstanceType', 'InstanceFamily', 'AZ', 'OndemandPrice', 'SpotPrice', 'Time']]


# In[8]:


print(virginia_price.head())
print(coremark.head())


# In[9]:


tmp_price = pd.merge(virginia_price[['InstanceType', 'OndemandPrice', 'SpotPrice']], 
                     coremark[['InstanceType', 'CoreMark', 'InstanceFamily', 'vCPU']], on=['InstanceType'])
tmp_price['OndemandPricePerCore'] = tmp_price['OndemandPrice'] / tmp_price['vCPU']
tmp_price['SpotPricePerCore'] = tmp_price['SpotPrice'] / tmp_price['vCPU']


# In[10]:


combined_price_coremark = pd.merge(
    tmp_price[['InstanceFamily', 'OndemandPricePerCore', 'SpotPricePerCore']], 
    coremark[['CoreMark', 'InstanceFamily', 'Vendor', 'ModelName']],
    on=['InstanceFamily']).round(4).drop_duplicates()

combined_price_coremark['Category'] = combined_price_coremark['InstanceFamily'].str[0]

combined_price_coremark = combined_price_coremark.sort_values(['Vendor', 'Category'])

combined_price_coremark = combined_price_coremark.dropna(subset=['CoreMark'])


# In[11]:


print(combined_price_coremark)


# In[12]:


m8i = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'm8i')]
m8a = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'm8a')]
m8g = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'm8g')]


# In[13]:


new_data = pd.concat([m8i, m8a, m8g])
new_data['InstanceFamily'].unique()


# In[14]:


import matplotlib.lines as mlines
import matplotlib.patches as mpatches

# Plot for 'c' category
font_size = 24
font_family = 'Roboto'
plt.rcParams['font.family'] = font_family
plt.rcParams['font.size'] = font_size
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False

coremark_marker_size = 240
ondemand_marker_size = 150

fig, ax = plt.subplots(figsize=(5.5, 4))

# InstanceFamily 순서 정의
family_order = ['m8i', 'm8a', 'm8g']

# 데이터 정렬
data = new_data.sort_values('InstanceFamily', key=lambda x: pd.Categorical(x, categories=family_order, ordered=True))
grouped_data = data.groupby(['InstanceFamily'], as_index=False)
print(grouped_data['InstanceFamily'].unique())
# CoreMark 평균 구하고 정렬 유지
coremark_mean = grouped_data['CoreMark'].mean()
coremark_mean = coremark_mean.sort_values('InstanceFamily', key=lambda x: pd.Categorical(x, categories=family_order, ordered=True))
print(coremark_mean)
# OndemandPricePerCore 평균 구하고 정렬 유지
ondemand_mean = grouped_data['OndemandPricePerCore'].mean()
ondemand_mean = ondemand_mean.sort_values('InstanceFamily', key=lambda x: pd.Categorical(x, categories=family_order, ordered=True))

# Scatter plot - CoreMark
sns.scatterplot(
    x='InstanceFamily', y='CoreMark', data=coremark_mean,
    marker='*', s=coremark_marker_size, edgecolor='black', color='gray',
    ax=ax, zorder=1
)

# Scatter plot - OndemandPricePerCore


ax.set_xlabel('')
ax.set_ylabel('', fontsize=font_size)
ax.set_ylim(0, 54000)
ax.set_yticks([0, 10000, 20000, 30000, 40000, 50000])
ax.set_yticklabels([])
ax.tick_params(axis='x', which='major', labelsize=font_size) 
ax.tick_params(axis='y', which='major', labelsize=font_size-3, length=0)

# ax.legend_.remove()

ax2 = ax.twinx()

sns.scatterplot(
    x='InstanceFamily', y='OndemandPricePerCore', data=ondemand_mean,
    color='red', edgecolor='black', marker='D', s=ondemand_marker_size, ax=ax2, zorder=3
)
sns.boxplot(x='InstanceFamily', y='SpotPricePerCore', data=data,
            color='white', linewidth=2, linecolor='black',
            medianprops=dict(color="orange", linewidth=2.0), ax=ax2, zorder=0)



ax2.set_xlabel('')
ax2.set_ylabel('Price per Core ($)', fontsize=font_size, fontdict={'family': font_family})
ax2.set_ylim(0, 0.11)
ax2.set_yticks([0, 0.02, 0.04, 0.06, 0.08, 0.1])
ax2.tick_params(axis='y', which='both')
ax2.tick_params(axis='both', which='major', labelsize=font_size-3)

# ax.set_zorder(2)
# ax2.set_zorder(1)
# ax.patch.set_visible(False)
# ax2.patch.set_visible(False)

# ax.vlines(x=0.5, ymin=-10000, ymax=39000, color='grey', linestyle='--', lw=1, clip_on=False)
# ax.vlines(x=1.5, ymin=-10000, ymax=39000, color='grey', linestyle='--', lw=1, clip_on=False)
# Add text below xticks
ax.text(0.167, -0.24, 'Intel', transform=ax.transAxes, ha='center', va='center', fontsize=font_size-3)
ax.text(0.5, -0.24, 'AMD', transform=ax.transAxes, ha='center', va='center', fontsize=font_size-3)
ax.text(0.83, -0.24, 'AWS', transform=ax.transAxes, ha='center', va='center', fontsize=font_size-3)
# ax.text(0.96, -0.15, 'Storage', transform=ax.transAxes, ha='center', va='center', fontsize=14)

fig.tight_layout()

plt.savefig(f'cpu-vendor-coremark-price.pdf', bbox_inches='tight')
plt.show()


# In[ ]:





# In[ ]:




