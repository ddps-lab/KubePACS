import boto3
import csv
from datetime import datetime, timedelta, timezone
import json
import numpy as np
import time
import pandas as pd
import os

# 설정
REGION_NAMES = ["us-west-2", "eu-west-1", "us-east-1", "ap-northeast-1"]
CLUSTER_NAMES = ["kubecaps-w2", "kubecaps-w1", "kubecaps-e1", "kubecaps-a1"]
LOOKBACK_DAYS = 2
os.makedirs('region', exist_ok=True)

def get_cloudtrail_events_with_retry(client: boto3.client, event_name: str, start_time: datetime, end_time: datetime, max_retries: int = 3, retry_delay_seconds: int = 10) -> list:
    events_collected = []
    next_token = None

    while True:
        params = {
            'LookupAttributes': [{'AttributeKey': 'EventName', 'AttributeValue': event_name}],
            'StartTime': start_time,
            'EndTime': end_time,
            'MaxResults': 50
        }
        if next_token:
            params['NextToken'] = next_token

        for _ in range(max_retries + 1):
            try:
                response = client.lookup_events(**params)
                events_collected.extend(response.get('Events', []))
                next_token = response.get('NextToken')
                break
            except client.exceptions.ClientError as e:
                if "ThrottlingException" in str(e) or "Rate exceeded" in str(e):
                    time.sleep(retry_delay_seconds)
                else:
                    next_token = None
                    break
            except Exception:
                next_token = None
                break

        if not next_token:
            break
    return events_collected

def format_tags_from_list(tags_list: list) -> str:
    if not tags_list:
        return ""
    return ";".join(f"{tag.get('key', tag.get('Key'))}={tag.get('value', tag.get('Value'))}" for tag in tags_list if tag.get('key', tag.get('Key')) and tag.get('value', tag.get('Value')))

def tagstr_to_dict(tagstr):
    d = {}
    for t in tagstr.split(';'):
        if '=' in t:
            k, v = t.split('=', 1)
            d[k] = v
    return d

for REGION_NAME, CLUSTER_NAME in zip(REGION_NAMES, CLUSTER_NAMES):
    try:
        session = boto3.Session(profile_name='ddpslab')
        cloudtrail_client = session.client('cloudtrail', region_name=REGION_NAME)
    except Exception as e:
        print(f"[{REGION_NAME}] CloudTrail client 생성 실패: {e}")
        continue

    now_utc = datetime.now(timezone.utc)
    start_time = now_utc - timedelta(days=LOOKBACK_DAYS)
    start_time = datetime(2025, 8, 19, 13, 0, 0, tzinfo=timezone.utc)
    print(f"[{REGION_NAME}] 시작 시간: {start_time}")

    run_events = get_cloudtrail_events_with_retry(cloudtrail_client, 'RunInstances', start_time, now_utc)
    tag_events = get_cloudtrail_events_with_retry(cloudtrail_client, 'CreateTags', start_time, now_utc)

    instance_dict = {}

    for event in run_events:
        try:
            event_blob = json.loads(event['CloudTrailEvent'])
            instance = event_blob.get('responseElements', {}).get('instancesSet', {}).get('items', [{}])[0]
            instance_id = instance.get('instanceId', 'N/A')
            instance_dict[instance_id] = {
                'event_id': event.get('EventId'),
                'event_time': event['EventTime'].isoformat(),
                'instance_id': instance_id,
                'instance_type': instance.get('instanceType', ''),
                'AZ': instance.get('placement', {}).get('availabilityZone', ''),
                'tags': format_tags_from_list(instance.get('tagSet', {}).get('items', []))
            }
        except Exception:
            continue
    print(f"[{REGION_NAME}] RunInstances 이벤트 수집 완료")
    for event in tag_events:
        try:
            event_blob = json.loads(event['CloudTrailEvent'])
            params = event_blob.get('requestParameters', {})
            resource_id = params.get('resourcesSet', {}).get('items', [{}])[0].get('resourceId', '')
            tags = format_tags_from_list(params.get('tagsSet', {}).get('items', []))

            if resource_id in instance_dict:
                existing_tags = instance_dict[resource_id]['tags']
                merged = tagstr_to_dict(existing_tags)
                merged.update(tagstr_to_dict(tags))
                instance_dict[resource_id]['tags'] = ';'.join([f"{k}={v}" for k, v in merged.items()])
            else:
                instance_dict[resource_id] = {
                    'event_id': event.get('EventId'),
                    'event_time': event['EventTime'].isoformat(),
                    'instance_id': resource_id,
                    'instance_type': '',
                    'AZ': '',
                    'tags': tags
                }
        except Exception:
            continue
    print(f"[{REGION_NAME}] CreateTags 이벤트 수집 완료")
    extracted = [v for v in instance_dict.values() if f"eks:eks-cluster-name={CLUSTER_NAME}-k8s-cluster" in v.get('tags', '')]
    tag_keys = set()
    for inst in extracted:
        tag_keys.update(tagstr_to_dict(inst.get('tags', '')).keys())

    base_fields = ['event_id', 'event_time', 'instance_id', 'instance_type', 'AZ']
    rows = []
    for inst in extracted:
        row = {field: inst.get(field, '') for field in base_fields}
        tag_dict = tagstr_to_dict(inst.get('tags', ''))
        for k in tag_keys:
            row[k] = tag_dict.get(k, '')
        rows.append(row)

    df = pd.DataFrame(rows, columns=base_fields + sorted(tag_keys))
    df['kubecaps-info'] = df['kubecaps-info'].replace('', np.nan)
    df = df.dropna(subset=['kubecaps-info'])

    grouped = df.groupby('karpenter.k8s.aws/ec2nodeclass')
    result_rows = []

    for nodeclass, group in grouped:
        nodepool_config = []
        for (instance_type, az), subgrp in group.groupby(['instance_type', 'AZ']):
            nodepool_config.append({
                'instance_type': instance_type,
                'availability_zone': az,
                'num_instances': len(subgrp)
            })
        first_row = group.iloc[0]
        result_rows.append({
            'pods': int(first_row['kubecaps-parallelism']),
            'cpu': int(first_row['kubecaps-cpu']),
            'memory': int(first_row['kubecaps-memgb']),
            'nodepool_config': nodepool_config,
            'first_time': first_row['event_time'],
            'region': REGION_NAME
        })

    result_df = pd.DataFrame(result_rows)
    result_df['first_time'] = pd.to_datetime(result_df['first_time'], errors='coerce')
    result_df.sort_values(by=['pods', 'cpu', 'memory'], inplace=True)
    result_df.to_csv(f'./region/result_{REGION_NAME}.csv', index=False, encoding='utf-8')
    print(f"[{REGION_NAME}] 리전 결과 저장 완료 → region/result_{REGION_NAME}.csv")