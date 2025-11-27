import boto3
import csv
from datetime import datetime, timedelta, timezone
import json
import time # Rate limit 시 대기를 위해
import pandas as pd

# --- 설정 ---
REGION_NAME = "us-west-2"  # AWS 리전
LOOKBACK_DAYS = 1  # 최근 N일간의 이벤트를 조회
OUTPUT_CSV_FILE = f'ec2_instance_details_{REGION_NAME}.csv' # 출력 CSV 파일명

# EC2 인스턴스 시작과 관련된 주요 이벤트
# RunInstances: 새 인스턴스 시작 시 발생. 인스턴스 ID, 타입, 시작 시점 태그 등 상세 정보 포함.
EVENT_NAME_FOR_INSTANCE_CREATION = 'RunInstances'
# CreateTags: 리소스에 태그를 생성/업데이트할 때 발생.
# 이번 요청은 "EC2 시작 이벤트와 태그 생성 클라우드트레일 이벤트 긁어오기" 후
# "인스턴스ID, 인스턴스 타입, 태그, 시작시간"을 CSV로 정리하는 것입니다.
# 따라서, RunInstances 이벤트를 중심으로 인스턴스 정보를 추출하고,
# 해당 이벤트 내에서 생성 시점의 태그 정보를 가져오는 것을 목표로 합니다.
# CreateTags 이벤트를 별도로 조회하여 병합하는 것은 시작 시점의 태그를 특정하기 어렵고 복잡성을 증가시킬 수 있습니다.

def get_cloudtrail_events_with_retry(client: boto3.client, event_name: str, start_time: datetime, end_time: datetime, max_retries: int = 3, retry_delay_seconds: int = 10) -> list:
    """
    지정된 이벤트 이름에 대해 CloudTrail 이벤트를 가져옵니다.
    API 호출 제한(Rate Exceeded, ThrottlingException) 발생 시 재시도 로직을 포함합니다.
    """
    print(f"'{event_name}' 이벤트 조회를 시작합니다...")
    events_collected = []
    next_token = None
    page_num = 0
    
    while True:
        page_num += 1
        # print(f"  '{event_name}' 이벤트의 페이지 {page_num}을(를) 조회 중입니다...")
        params = {
            'LookupAttributes': [{'AttributeKey': 'EventName', 'AttributeValue': event_name}],
            'StartTime': start_time,
            'EndTime': end_time,
            'MaxResults': 50  # API 페이지 당 최대 결과 수
        }
        if next_token:
            params['NextToken'] = next_token

        current_retry = 0
        while current_retry <= max_retries:
            try:
                response = client.lookup_events(**params)
                fetched_on_page = response.get('Events', [])
                # print(f"  페이지 {page_num}에서 {len(fetched_on_page)}개의 '{event_name}' 이벤트를 가져왔습니다.")
                events_collected.extend(fetched_on_page)
                next_token = response.get('NextToken')
                break # 성공 시 내부 루프 탈출
            except client.exceptions.ClientError as e:
                error_code = e.response.get("Error", {}).get("Code")
                if error_code == "ThrottlingException" or "Rate exceeded" in str(e):
                    if current_retry < max_retries:
                        current_retry += 1
                        print(f"경고: '{event_name}' 이벤트 조회 중 API 호출 제한 발생. {retry_delay_seconds}초 후 재시도합니다... (시도 {current_retry}/{max_retries})")
                        time.sleep(retry_delay_seconds)
                    else:
                        print(f"오류: '{event_name}' 이벤트 조회 중 API 호출 제한이 {max_retries}회 초과되었습니다. 해당 이벤트의 추가 페이지 조회를 중단합니다.")
                        next_token = None # 더 이상 진행하지 않도록 next_token 제거
                        break # 내부 루프 탈출
                else:
                    print(f"오류: '{event_name}' 이벤트 조회 중 Boto3 ClientError 발생: {e}")
                    next_token = None 
                    break 
            except Exception as e:
                print(f"오류: '{event_name}' 이벤트 조회 중 예기치 않은 오류 발생: {e}")
                next_token = None 
                break 
        
        if not next_token:
            # print(f"  '{event_name}' 이벤트에 대한 더 이상 조회할 페이지가 없습니다.")
            break
            
    print(f"'{event_name}' 이벤트 조회 완료. 총 {len(events_collected)}개의 이벤트를 수집했습니다.")
    return events_collected

def format_tags_from_list(tags_list: list) -> str:
    """CloudTrail 이벤트 내의 태그 리스트를 'key1=value1;key2=value2' 형식의 문자열로 변환합니다."""
    if not tags_list:
        return ""
    
    formatted_tags = []
    for tag_item in tags_list:
        # CloudTrail 이벤트의 태그 구조는 {'key': 'KeyName', 'value': 'ValueName'} 또는 {'Key': ..., 'Value': ...} 일 수 있음
        key = tag_item.get('key', tag_item.get('Key'))
        value = tag_item.get('value', tag_item.get('Value'))
        if key is not None and value is not None: # 키와 값이 모두 존재해야 유효한 태그로 간주
             formatted_tags.append(f"{key}={value}")
    return ";".join(formatted_tags)

def main():
    """메인 실행 함수"""
    try:
        # AWS 인증 정보를 환경 변수, 공유 자격 증명 파일 또는 IAM 역할을 통해 Boto3가 자동으로 찾도록 합니다.
        # 특정 프로파일 사용 시: session = boto3.Session(profile_name="your-profile-name")
        # client = session.client('cloudtrail', region_name=REGION_NAME)
        cloudtrail_client = boto3.client('cloudtrail', region_name=REGION_NAME)
    except Exception as e:
        print(f"오류: Boto3 CloudTrail 클라이언트를 초기화하는 중 문제가 발생했습니다: {e}")
        return

    # 조회할 시간 범위 설정 (UTC 기준)
    utc_now = datetime.now(timezone.utc)
    end_time_utc = utc_now
    start_time_utc = utc_now - timedelta(days=LOOKBACK_DAYS)

    print(f"{REGION_NAME} 리전에서 {start_time_utc.isoformat()} 부터 {end_time_utc.isoformat()} 까지의 CloudTrail 이벤트를 조회합니다.")

    # 1. RunInstances 이벤트 조회
    run_instances_events = get_cloudtrail_events_with_retry(
        cloudtrail_client, 
        EVENT_NAME_FOR_INSTANCE_CREATION, 
        start_time_utc, 
        end_time_utc
    )
    
    # 인스턴스ID 기준 병합을 위한 딕셔너리
    instance_dict = {}

    for event_log in run_instances_events:
        event_id = event_log.get('EventId', 'N/A')
        event_time_iso = event_log['EventTime'].isoformat() 
        cloud_trail_event_blob_str = event_log.get('CloudTrailEvent')
        if not cloud_trail_event_blob_str:
            print(f"경고: Event {event_id}에 CloudTrailEvent가 없습니다. 이벤트 로그를 무시합니다.")
            continue
        try:
            cloud_trail_event_blob = json.loads(cloud_trail_event_blob_str)
            event_name = cloud_trail_event_blob.get('eventName', 'N/A') 
            if event_name != EVENT_NAME_FOR_INSTANCE_CREATION:
                print(f"경고: Event {event_id}의 이벤트 이름이 '{EVENT_NAME_FOR_INSTANCE_CREATION}'가 아닙니다. 이벤트 로그를 무시합니다.")
                continue
            response_elements = cloud_trail_event_blob.get('responseElements')
            if not isinstance(response_elements, dict):
                response_elements = {}
            instances_set = response_elements.get('instancesSet')
            if not isinstance(instances_set, dict):
                instances_set = {}
            items = instances_set.get('items')
            if not isinstance(items, list) or not items or not isinstance(items[0], dict):
                items = [{}]
            instance_item = items[0]
            instance_id = instance_item.get('instanceId', 'N/A')
            instance_type = instance_item.get('instanceType', 'N/A')
            tagset = instance_item.get('tagSet')
            if not isinstance(tagset, dict):
                tagset = {}
            tags = format_tags_from_list(tagset.get('items', []))
            placement = instance_item.get('placement')
            if not isinstance(placement, dict):
                placement = {}
            az = placement.get('availabilityZone', '')
            instance_dict[instance_id] = {
                'event_id': event_id,
                'event_time': event_time_iso,
                'instance_id': instance_id,
                'instance_type': instance_type,
                'AZ': az,
                'tags': tags
            }
        except Exception as e:
            print(f"오류: Event {event_id}의 파싱 중 예기치 않은 오류 발생: {e}")
            continue
    
    # 2. CreateTags 이벤트 조회 및 병합
    create_tags_events = get_cloudtrail_events_with_retry(
        cloudtrail_client,
        'CreateTags',
        start_time_utc,
        end_time_utc
    )

    for event_log in create_tags_events:
        event_id = event_log.get('EventId', 'N/A')
        event_time_iso = event_log['EventTime'].isoformat()
        cloud_trail_event_blob_str = event_log.get('CloudTrailEvent')
        if not cloud_trail_event_blob_str:
            print(f"경고: Event {event_id}에 CloudTrailEvent가 없습니다. 이벤트 로그를 무시합니다.")
            continue
        try:
            cloud_trail_event_blob = json.loads(cloud_trail_event_blob_str)
            event_name = cloud_trail_event_blob.get('eventName', 'N/A')
            if event_name != 'CreateTags':
                print(f"경고: Event {event_id}의 이벤트 이름이 'CreateTags'가 아닙니다. 이벤트 로그를 무시합니다.")
                continue
            request_parameters = cloud_trail_event_blob.get('requestParameters')
            if not isinstance(request_parameters, dict):
                request_parameters = {}
            resources_set = request_parameters.get('resourcesSet')
            if not isinstance(resources_set, dict):
                resources_set = {}
            items = resources_set.get('items')
            if not isinstance(items, list) or not items or not isinstance(items[0], dict):
                items = [{}]
            resource_item = items[0]
            instance_id = resource_item.get('resourceId', 'N/A')
            tags_set = request_parameters.get('tagsSet')
            if not isinstance(tags_set, dict):
                tags_set = {}
            tags = format_tags_from_list(tags_set.get('items', []))
            if instance_id in instance_dict:
                run_tags = instance_dict[instance_id]['tags']
                merged_tags = run_tags
                if run_tags and tags:
                    def tagstr_to_dict(tagstr):
                        d = {}
                        for t in tagstr.split(';'):
                            if '=' in t:
                                k, v = t.split('=', 1)
                                d[k] = v
                        return d
                    merged = tagstr_to_dict(run_tags)
                    merged.update(tagstr_to_dict(tags))
                    merged_tags = ';'.join([f"{k}={v}" for k, v in merged.items()])
                elif tags:
                    merged_tags = tags
                instance_dict[instance_id]['tags'] = merged_tags
            else:
                instance_dict[instance_id] = {
                    'event_id': event_id,
                    'event_time': event_time_iso,
                    'instance_id': instance_id,
                    'instance_type': '',
                    'AZ': '',
                    'tags': tags
                }
        except Exception as e:
            print(f"오류: Event {event_id}의 파싱 중 예기치 않은 오류 발생: {e}")
            continue

    # 3. 결과 정렬 및 출력
    # 인스턴스 ID를 기준으로 정렬
    extracted_instance_data = list(instance_dict.values())
    extracted_instance_data.sort(key=lambda x: x['instance_id'])

    # 4. 필터링: 태그가 있고 특정 태그 값을 가진 인스턴스만 선택
    filtered_instance_data = []
    for instance in extracted_instance_data:
        if 'tags' in instance and instance['tags']:
            if 'eks:eks-cluster-name=kubecaps-d2-k8s-cluster' in instance['tags']:
                filtered_instance_data.append(instance)
    print(f"정보: 총 {len(extracted_instance_data)}개 인스턴스 중 {len(filtered_instance_data)}개가 필터링 조건을 만족합니다.")
    extracted_instance_data = filtered_instance_data

    # CSV 파일 출력
    if not extracted_instance_data:
        print("오류: 추출된 인스턴스 데이터가 없습니다. CSV 파일을 생성하지 않습니다.")
        return

    # 5. 태그 key를 열 단위로 확장하기 위해 모든 태그 key 수집
    def tagstr_to_dict(tagstr):
        d = {}
        if tagstr:
            for t in tagstr.split(';'):
                if '=' in t:
                    k, v = t.split('=', 1)
                    d[k] = v
        return d

    tag_keys = set()
    for inst in extracted_instance_data:
        tag_keys.update(tagstr_to_dict(inst.get('tags', '')).keys())

    base_fields = ['event_id', 'event_time', 'instance_id', 'instance_type', 'AZ']
    fieldnames = base_fields + sorted(tag_keys)

    # DataFrame 적재
    rows = []
    for inst in extracted_instance_data:
        row = {field: inst.get(field, '') for field in base_fields}
        tag_dict = tagstr_to_dict(inst.get('tags', ''))
        for k in tag_keys:
            row[k] = tag_dict.get(k, '')
        rows.append(row)
    df = pd.DataFrame(rows, columns=fieldnames)
    # kubecaps-info 열이 비어있는 행 삭제
    df = df.dropna(subset=['kubecaps-info'])

    df.to_csv(OUTPUT_CSV_FILE, index=False, encoding='utf-8')

    print(f"완료: 총 {df.shape[0]}개의 인스턴스 정보가 {OUTPUT_CSV_FILE}에 저장되었습니다.")

if __name__ == "__main__":
    main()