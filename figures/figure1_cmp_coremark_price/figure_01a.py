#!/usr/bin/env python
# coding: utf-8

# <!-- 2025-06-03 04:30:00 -->

# In[2]:


import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from matplotlib import ticker
import matplotlib.lines as mlines
import matplotlib.patches as mpatches

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

combined_price_coremark = combined_price_coremark[(
    ~combined_price_coremark['InstanceFamily'].str.contains('n|b|z|flex'))].sort_values(['Vendor', 'Category'])

combined_price_coremark = combined_price_coremark.dropna(subset=['CoreMark'])


# In[11]:


print(combined_price_coremark)
c = combined_price_coremark[(combined_price_coremark['Category'] == 'c')]
m = combined_price_coremark[(combined_price_coremark['Category'] == 'm')]
r = combined_price_coremark[(combined_price_coremark['Category'] == 'r')]


# In[12]:


# Group by Vendor and Family to calculate mean Coremark score
vendor_family_coremark = c.groupby(['Vendor', 'InstanceFamily'])['CoreMark'].mean().reset_index()

# Find minimum Coremark score for each Vendor
min_coremark_by_vendor = vendor_family_coremark.groupby('Vendor')['CoreMark'].min()

# Create a new column for the relative performance
vendor_family_coremark['RelativePerformance'] = vendor_family_coremark.apply(
    lambda row: row['CoreMark'] / min_coremark_by_vendor[row['Vendor']], axis=1
)

# Sort by Vendor and Family for better readability
vendor_family_coremark = vendor_family_coremark.sort_values(['Vendor', 'InstanceFamily'])

# Display the results with formatted output
print(vendor_family_coremark)
print("\nMinimum Coremark scores by vendor:")
for vendor, min_score in min_coremark_by_vendor.items():
    print(f"{vendor}: {min_score:.2f}")


# In[13]:


m["InstanceFamily"].unique()


# In[14]:


m_intel = m[(m['Vendor'] == 'Intel') & (m['InstanceFamily'].isin(['m6i', 'm7i', "m8i"]))]


# In[15]:


print(m_intel)


# In[16]:


font_size = 24
font_family = 'Roboto'
plt.rcParams['font.family'] = font_family
plt.rcParams['font.size'] = font_size
plt.rcParams['font.weight'] = 400
plt.rcParams["axes.labelweight"] = 400
plt.rcParams['axes.unicode_minus'] = False


# In[17]:


# Plot for 'c' category
data = m_intel



coremark_marker_size = 240
ondemand_marker_size = 150
fig, ax = plt.subplots(figsize=(5.5, 4))

grouped_data = data.groupby(['InstanceFamily', 'Vendor'], as_index=False)
print(grouped_data['CoreMark'].mean())
print(grouped_data['OndemandPricePerCore'].mean())

sns.scatterplot(
    x='InstanceFamily', y='CoreMark', data=grouped_data['CoreMark'].mean(),
    hue='Vendor', style='Vendor',
    markers='*', s=coremark_marker_size, edgecolor='black', palette='gray',
    ax=ax, zorder=1
)   

ax.set_xlabel('')
ax.set_ylabel('CoreMark Score', fontsize=font_size)
ax.set_ylim(0, 54000)
ax.set_yticks([0, 10000, 20000, 30000, 40000, 50000])
# ax.set_yticklabels([])
#40K 까지만 표시

ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f'{int(x/1000)}K' if x >= 1000 else f'{int(x)}'))
ax.tick_params(axis='x', which='major', labelsize=font_size) 
ax.tick_params(axis='y', which='major', labelsize=font_size-3)

# Remove legend from main plot
if ax.get_legend() is not None:
    ax.get_legend().remove()

ax2 = ax.twinx()
sns.boxplot(x='InstanceFamily', y='SpotPricePerCore', data=data,
            color='white', linewidth=2, linecolor='black',
            medianprops=dict(color="orange", linewidth=2.0), ax=ax2, zorder=0)

sns.scatterplot(x='InstanceFamily', y='OndemandPricePerCore', data=grouped_data['OndemandPricePerCore'].mean(),
                 color='red', edgecolor='black', marker='D', s=ondemand_marker_size, ax=ax2, zorder=3)
ax2.set_xlabel('')
ax2.set_ylabel('')
ax2.set_ylim(0, 0.11)
ax2.set_yticks([0, 0.02, 0.04, 0.06, 0.08, 0.1])
ax2.set_yticklabels([])
ax2.tick_params(axis='y', which='both', length=0)
ax2.tick_params(axis='both', which='major', labelsize=font_size-3)

ax.set_zorder(2)
ax2.set_zorder(1)
ax.patch.set_visible(False)
ax2.patch.set_visible(False)

# Add text below xticks
ax.text(0.5, -0.24, ' ', transform=ax.transAxes, ha='center', va='center', fontsize=font_size, fontdict={'family': font_family})

fig.tight_layout()
plt.savefig(f'm-family-gen-coremark-price.pdf', bbox_inches='tight')
plt.show()


# In[18]:


# Create separate legend figure
fig_legend = plt.figure(figsize=(10, 0.5))
ax_legend = fig_legend.add_subplot(111)

coremark_legend = mlines.Line2D([], [], color='grey', marker='*', markersize=12,
                                markeredgecolor='black', linestyle='None', label='CoreMark Score (Left Y-axis)')

spotprice_legend = mpatches.Patch(facecolor='white', edgecolor='black', label='Spot Price per Core (Right Y-axis)')

ondemand_legend = mlines.Line2D([], [], color='red', marker='D', markersize=8,
                                markeredgecolor='black', linestyle='None', label='On-demand Price per Core (Right Y-axis)')

legend = ax_legend.legend(handles=[coremark_legend, ondemand_legend, spotprice_legend],
                         loc='center', fontsize=15, edgecolor='black', facecolor='none', 
                         labelspacing=0.3, handletextpad=0.3, borderpad=0.4, frameon=True, ncol=3)
legend.get_frame().set_edgecolor('black')

# Hide axes
ax_legend.axis('off')

fig_legend.tight_layout()
plt.savefig(f'cmp-coremark-price-legend.pdf', bbox_inches='tight')
plt.show()

