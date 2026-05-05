#!/usr/bin/env python
# coding: utf-8

# 06-03 01:10 UTC+9

# In[12]:


import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42


# In[13]:


coremark = pd.read_csv('../common/dataset/aws_coremark_singlecore.csv')


# In[14]:


spot_price_url = "https://d26bk4799jlxhe.cloudfront.net/latest_data/latest_aws.json"
price_data = pd.read_json(spot_price_url)
price_data


# In[15]:


virginia_price = price_data[price_data['Region'] == 'us-east-1']
virginia_price.loc[:, 'OndemandPrice'] = virginia_price['OndemandPrice'].round(5)
virginia_price.loc[:, 'SpotPrice'] = virginia_price['SpotPrice'].round(5)
virginia_price = virginia_price[(~virginia_price['InstanceType'].str.contains('metal'))]
virginia_price['InstanceFamily'] = virginia_price['InstanceType'].str.split('.', expand=True)[0]


# In[16]:


virginia_price = virginia_price[['InstanceType', 'InstanceFamily', 'AZ', 'OndemandPrice', 'SpotPrice', 'Time']]


# In[17]:


print(virginia_price.head())
print(coremark.head())


# In[18]:


tmp_price = pd.merge(virginia_price[['InstanceType', 'OndemandPrice', 'SpotPrice']], 
                     coremark[['InstanceType', 'CoreMark', 'InstanceFamily', 'vCPU']], on=['InstanceType'])
tmp_price['OndemandPricePerCore'] = tmp_price['OndemandPrice'] / tmp_price['vCPU']
tmp_price['SpotPricePerCore'] = tmp_price['SpotPrice'] / tmp_price['vCPU']


# In[19]:


combined_price_coremark = pd.merge(
    tmp_price[['InstanceFamily', 'OndemandPricePerCore', 'SpotPricePerCore']], 
    coremark[['CoreMark', 'InstanceFamily', 'Vendor', 'ModelName']],
    on=['InstanceFamily']).round(4).drop_duplicates()

combined_price_coremark['Category'] = combined_price_coremark['InstanceFamily'].str[0]

combined_price_coremark = combined_price_coremark[(
    ~combined_price_coremark['InstanceFamily'].str.contains('n|b|z|flex'))].sort_values(['Vendor', 'Category'])

combined_price_coremark = combined_price_coremark.dropna(subset=['CoreMark'])


# In[20]:


m5 = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'm5')]
m6i = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'm6i')]
m7i = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'm7i')]
c5 = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'c5')]
c6i = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'c6i')]
c7i = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'c7i')]
r5 = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'r5')]
r6i = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'r6i')]
r7i = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'r7i')]
i4i = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'i4i')]
i7i = combined_price_coremark[(combined_price_coremark['InstanceFamily'] == 'i7i')]


# In[21]:


new_data = pd.concat([m7i, c7i, r7i, i7i])
new_data


# In[23]:


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
family_order = ['m6i', 'm7i', 'c6i', 'c7i', 'r6i', 'r7i', 'i4i', 'i7i']

# 데이터 정렬
data = new_data.sort_values('InstanceFamily', key=lambda x: pd.Categorical(x, categories=family_order, ordered=True))
grouped_data = data.groupby(['InstanceFamily'], as_index=False)

# CoreMark 평균 구하고 정렬 유지
coremark_mean = grouped_data['CoreMark'].mean()
coremark_mean = coremark_mean.sort_values('InstanceFamily', key=lambda x: pd.Categorical(x, categories=family_order, ordered=True))
print(coremark_mean)
# OndemandPricePerCore 평균 구하고 정렬 유지
ondemand_mean = grouped_data['OndemandPricePerCore'].mean()
ondemand_mean = ondemand_mean.sort_values('InstanceFamily', key=lambda x: pd.Categorical(x, categories=family_order, ordered=True))
print(ondemand_mean)
# Scatter plot - CoreMark
sns.scatterplot(
    x='InstanceFamily', y='CoreMark', data=coremark_mean,
    marker='*', s=coremark_marker_size, edgecolor='black', color='gray',
    ax=ax, zorder=1
)

# Scatter plot - OndemandPricePerCore



ax.set_xlabel('')
ax.set_ylabel('', fontsize=font_size, fontdict={'family': 'SUIT'})
ax.set_ylim(0, 54000)
ax.set_yticks([0, 10000, 20000, 30000, 40000, 50000])
ax.set_yticklabels([])
ax.tick_params(axis='x', which='major', labelsize=font_size) 
ax.tick_params(axis='y', which='major', labelsize=font_size-3, length=0)

ax2 = ax.twinx()

sns.scatterplot(
    x='InstanceFamily', y='OndemandPricePerCore', data=ondemand_mean,
    color='red', edgecolor='black', marker='D', s=ondemand_marker_size, ax=ax2, zorder=3
)
sns.boxplot(x='InstanceFamily', y='SpotPricePerCore', data=data,
            color='white', linewidth=2, linecolor='black',
            medianprops=dict(color="orange", linewidth=2.0), ax=ax2, zorder=0)


ax2.set_xlabel('')
ax2.set_ylabel('', fontsize=font_size)
ax2.set_yticklabels([])
ax2.set_ylim(0, 0.11)
ax2.set_yticks([0, 0.02, 0.04, 0.06, 0.08, 0.1])
ax2.tick_params(axis='y', which='both', length=0)
ax2.tick_params(axis='both', which='major', labelsize=font_size-3)


ax.set_zorder(2)
ax2.set_zorder(1)
ax.patch.set_visible(False)
ax2.patch.set_visible(False)

# ax.vlines(x=0.49, ymin=-10000, ymax=39000, color='grey', linestyle='--', lw=1, clip_on=False)
# ax.vlines(x=1.53, ymin=-10000, ymax=39000, color='grey', linestyle='--', lw=1, clip_on=False)
# ax.vlines(x=2.5, ymin=-10000, ymax=39000, color='grey', linestyle='--', lw=1, clip_on=False)
# Add text below xticks
ax.text(0.12, -0.24, 'General', transform=ax.transAxes, ha='center', va='center', fontsize=font_size-3)
ax.text(0.37, -0.24, 'Compute', transform=ax.transAxes, ha='center', va='center', fontsize=font_size-3)
ax.text(0.63, -0.24, 'Memory', transform=ax.transAxes, ha='center', va='center', fontsize=font_size-3)
ax.text(0.87, -0.24, 'Storage', transform=ax.transAxes, ha='center', va='center', fontsize=font_size-3)

fig.tight_layout()

plt.savefig(f'intel-coremark-price.pdf', bbox_inches='tight')
plt.show()


# In[ ]:





# In[ ]:




