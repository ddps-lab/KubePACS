import csv
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import bisect
import os # 경로 관련 작업을 위해 os 모듈 추가
import boto3 # boto3 추가
import json # Pricing API 응답 처리를 위해 추가

# --- 설정 ---
# 입력 파일 경로 (스크립트와 같은 디렉토리에 있다고 가정)
try:
    script_dir = os.path.dirname(os.path.abspath(__file__)) # 스크립트가 있는 디렉토리
except NameError:
    script_dir = os.getcwd() # 대화형 환경 등

INSTANCE_USAGE_FILE = os.path.join(script_dir, 'instance_usage_data.csv')
SPOT_PRICE_FILE = os.path.join(script_dir, 'spot_price_history.csv')
OUTPUT_FILE = os.path.join(script_dir, 'instance_usage_with_cost.csv')
TARGET_REGION = 'us-east-1' # 온디맨드 가격 조회 대상 리전 (예: 서울)
PRICING_API_REGION = 'us-east-1' # Pricing API 엔드포인트 리전

# --- 함수 정의 ---

def parse_datetime(dt_str):
    """ISO 8601 형식의 문자열을 timezone-aware datetime 객체로 변환합니다."""
    try:
        # Python 3.7+ 에서는 fromisoformat 사용 가능
        # 타임존 정보가 포함된 ISO 형식 문자열 처리 ('Z' 또는 +HH:MM)
        if dt_str.endswith('Z'):
            dt_str = dt_str[:-1] + '+00:00'
        dt = datetime.fromisoformat(dt_str)
        # 만약 datetime 객체가 timezone naive이면 UTC로 설정 (AWS API는 보통 UTC 반환)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        print(f"오류: 날짜/시간 형식 변환 실패 - {dt_str}")
        return None
    except TypeError: # dt_str이 None이거나 다른 타입일 경우
        # print(f"오류: 잘못된 날짜/시간 입력 타입 - {dt_str}") # None은 흔하므로 로그 줄임
        return None


def load_spot_price_history(filepath):
    """
    스팟 가격 기록 CSV 파일을 읽어 메모리에 로드합니다.
    데이터 구조: defaultdict(list)
    Key: (instance_type, availability_zone)
    Value: [(timestamp, price), (timestamp, price), ...] (시간순 정렬)
    """
    price_history = defaultdict(list)
    if not os.path.exists(filepath):
        print(f"오류: 스팟 가격 파일을 찾을 수 없습니다 - {filepath}")
        return None # 파일을 찾을 수 없으면 None 반환

    try:
        with open(filepath, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            header = next(reader, None) # 헤더 읽기 (있다고 가정)
            if not header or len(header) != 4: # 헤더 형식 검사
                print(f"경고: {filepath} 파일의 헤더가 예상과 다릅니다. ['InstanceType', 'AvailabilityZone', 'SpotPrice', 'Timestamp'] 형식을 기대합니다.")
                # 헤더가 잘못되었어도 처리를 시도하거나 여기서 중단할 수 있음
                # 여기서는 계속 진행하되, 인덱스로 접근 시 오류 발생 가능

            # 헤더 컬럼 인덱스 찾기 (더 안전한 방법)
            try:
                type_idx = header.index('InstanceType')
                az_idx = header.index('AvailabilityZone')
                price_idx = header.index('SpotPrice')
                ts_idx = header.index('Timestamp')
            except (ValueError, AttributeError):
                 print(f"오류: {filepath} 파일 헤더에서 필요한 컬럼을 찾을 수 없습니다.")
                 return None # 필수 컬럼 없으면 중단


            for i, row in enumerate(reader):
                if len(row) == 4:
                    instance_type = row[type_idx]
                    az = row[az_idx]
                    price_str = row[price_idx]
                    timestamp_str = row[ts_idx]

                    timestamp = parse_datetime(timestamp_str)
                    try:
                        price = float(price_str)
                    except ValueError:
                        print(f"오류: 스팟 가격 변환 실패 (행 {i+2}): {row}") # 헤더 포함 +2
                        continue # 이 행 건너뛰기

                    if timestamp:
                        price_history[(instance_type, az)].append((timestamp, price))
                    else:
                        print(f"경고: 스팟 가격 타임스탬프 변환 실패로 행 건너뜀 (행 {i+2}): {row}")
                else:
                    print(f"경고: 잘못된 형식의 스팟 가격 행 건너뜀 (행 {i+2}) in {filepath}: {row}")

    except FileNotFoundError: # 위에서 체크했지만 이중 확인
        print(f"오류: 파일을 찾을 수 없습니다 - {filepath}")
        return None
    except Exception as e:
        print(f"오류: {filepath} 파일 읽기 중 오류 발생: {e}")
        return None

    # 각 키에 대해 타임스탬프 기준으로 정렬
    for key in price_history:
        price_history[key].sort(key=lambda x: x[0])

    print(f"스팟 가격 정보 로드 완료: {len(price_history)}개의 (타입, AZ) 조합")
    return price_history

def calculate_instance_cost(instance_type, az, start_time, end_time, price_history):
    """
    주어진 인스턴스 사용 기간 동안의 스팟 비용을 계산합니다.
    종료 시간이 시작 시간보다 이전이거나, 유효한 가격 정보가 없는 경우 0.0을 반환합니다.
    """
    if end_time is None or start_time is None or end_time <= start_time:
        # print(f"정보: 유효하지 않은 사용 기간 ({start_time} -> {end_time}) 또는 종료 시간 없음. 스팟 비용 0 처리.")
        return 0.0

    key = (instance_type, az)
    if key not in price_history or not price_history[key]:
        # print(f"경고: {instance_type} ({az})에 대한 스팟 가격 정보 없음. 비용 0으로 처리.")
        return 0.0 # 해당 인스턴스/AZ 가격 정보 없으면 비용 0 처리

    specific_history = price_history[key]
    timestamps = [item[0] for item in specific_history]
    prices = [item[1] for item in specific_history]

    total_cost = 0.0

    # 사용 시작 시점 또는 그 이전의 가장 마지막 가격 인덱스 찾기
    start_idx = bisect.bisect_right(timestamps, start_time)
    if start_idx == 0:
        # 시작 시간이 첫 기록보다 이전 -> 첫 기록 시점부터 계산 시작
        # print(f"정보: 시작 시간({start_time})이 {key}의 첫 가격 기록({timestamps[0]})보다 이전입니다. 첫 기록부터 비용 계산 시작.")
        current_time = timestamps[0]
        # 사용 시작 시간이 첫 기록 시간보다 늦으면, 실제 시작 시간부터 계산
        if start_time > current_time:
             current_time = start_time
        current_price = prices[0]
        relevant_idx_start = 1 # 다음 가격 변동부터 순회
        # 만약 end_time이 첫 가격 변동 시점보다 이전이면 비용은 0
        if end_time <= timestamps[0]:
             # print(f"정보: 종료 시간({end_time})이 {key}의 첫 가격 기록({timestamps[0]}) 이전이므로 비용 0.")
            return 0.0
    else:
        # start_time 시점의 가격 적용
        current_price = prices[start_idx - 1]
        current_time = start_time # 실제 시작 시간부터 계산
        # start_time 이후의 첫 가격 변동 인덱스 찾기
        relevant_idx_start = start_idx


    # 가격 변동 지점 순회하며 비용 계산
    for i in range(relevant_idx_start, len(timestamps)):
        change_time = timestamps[i]
        next_price = prices[i]

        # 가격 변동 시점이 인스턴스 종료 시점 이전인 경우
        if change_time < end_time:
            # 현재 시간부터 가격 변동 시점까지의 기간 계산
            segment_end_time = change_time
        else:
            # 현재 가격이 적용되는 마지막 구간 (종료 시점까지)
            segment_end_time = end_time

        duration = segment_end_time - current_time
            # duration이 음수가 아닌지 확인 (데이터 오류 가능성)
        if duration.total_seconds() >= 0:
                cost_segment = (duration.total_seconds() / 3600) * current_price
                total_cost += cost_segment
            # print(f"Debug Cost: {key} | {current_time} -> {segment_end_time} | Duration: {duration.total_seconds():.0f}s | Price: {current_price:.6f} | SegCost: {cost_segment:.6f} | TotalCost: {total_cost:.6f}")
        else:
             print(f"경고: 시간 계산 오류 발생 (음수 기간) - {key}, {current_time} -> {segment_end_time}")

        current_time = change_time # 다음 계산을 위해 현재 시간 업데이트
        current_price = next_price # 다음 계산을 위해 가격 업데이트

        # 가격 변동 시점이 종료 시간 이후면 루프 종료
        if change_time >= end_time:
            break

    # 루프 종료 후, 마지막 가격이 적용되는 구간 처리 (위 로직에서 처리됨)
    # 만약 루프를 돌지 않았다면 (시작 이후 가격 변동 X)
    if relevant_idx_start >= len(timestamps) and current_time < end_time:
        duration = end_time - current_time
        if duration.total_seconds() > 0:
            cost_segment = (duration.total_seconds() / 3600) * current_price
            total_cost += cost_segment
             # print(f"Debug Cost (No Change): {key} | {current_time} -> {end_time} | Duration: {duration.total_seconds():.0f}s | Price: {current_price:.6f} | SegCost: {cost_segment:.6f} | TotalCost: {total_cost:.6f}")

    return total_cost


def get_ondemand_prices(instance_types, region, pricing_region='us-east-1'):
    """
    AWS Pricing API를 사용하여 지정된 인스턴스 유형의 온디맨드 시간당 가격을 조회합니다.
    Linux, Shared Tenancy 기준 가격을 조회합니다.

    Args:
        instance_types (list): 가격을 조회할 인스턴스 유형 목록.
        region (str): 대상 리전 (예: 'ap-northeast-2').
        pricing_region (str): Pricing API 엔드포인트 리전 (기본값 'us-east-1').

    Returns:
        dict: {'instance_type': ondemand_price} 형태의 딕셔너리. 오류 시 빈 딕셔너리 반환.
              가격을 찾지 못한 유형은 포함되지 않습니다.
    """
    ondemand_prices = {}
    if not instance_types:
        return ondemand_prices

    print(f"'{pricing_region}' Pricing API를 통해 '{region}' 리전의 온디맨드 가격 조회를 시작합니다...")
    try:
        pricing_client = boto3.client('pricing', region_name=pricing_region)
        location = get_region_location(region) # 리전 코드를 Location 필터 값으로 변환
        if not location:
            print(f"오류: 리전 코드 '{region}'에 해당하는 Location 정보를 찾을 수 없습니다.")
            return {}

        # 필터 목록 생성 (여러 유형 동시 조회 시도, API 제한 고려 필요)
        # 한 번에 너무 많은 유형 조회는 오류 유발 가능성 있음
        # 여기서는 유형별로 조회하는 안전한 방식 사용
        processed_types = set()
        for instance_type in instance_types:
             if instance_type in processed_types: # 중복 조회 방지
                  continue
             processed_types.add(instance_type)
             try:
                 paginator = pricing_client.get_paginator('get_products')
                 page_iterator = paginator.paginate(
                    ServiceCode='AmazonEC2',
                    Filters=[
                        {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': location},
                        {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                        {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'}, # Linux 기준
                        {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},        # 공유 테넌시 기준
                        {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},     # 추가 소프트웨어 없음
                        {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'}     # Used 용량 상태
                    ]
                    # MaxResults=1 # Paginator 사용 시 MaxResults는 paginate 인자에 전달
                 )

                 found_price = False
                 for page in page_iterator:
                    price_list = page.get('PriceList', [])
                    for price_data_str in price_list:
                        price_data = json.loads(price_data_str)
                        product_instance_type = price_data.get('product', {}).get('attributes', {}).get('instanceType')

                        # 응답의 인스턴스 타입이 요청한 타입과 일치하는지 확인 (필터가 완벽하지 않을 수 있음)
                        if product_instance_type != instance_type:
                            continue

                        terms = price_data.get('terms', {})
                        ondemand_terms = terms.get('OnDemand', {})

                        if ondemand_terms:
                            # OnDemand 텀의 첫 번째 항목 (가장 가능성 높은 유효한 텀)
                            first_term_key = list(ondemand_terms.keys())[0]
                            price_dimensions = ondemand_terms[first_term_key].get('priceDimensions', {})

                            if price_dimensions:
                                # PriceDimensions의 첫 번째 항목 (시간당 가격일 가능성 높음)
                                first_dimension_key = list(price_dimensions.keys())[0]
                                price_per_unit = price_dimensions[first_dimension_key].get('pricePerUnit', {})
                                usd_price_str = price_per_unit.get('USD')

                                if usd_price_str:
                                    try:
                                        ondemand_prices[instance_type] = float(usd_price_str)
                                        found_price = True
                                        # print(f"Debug: Found price for {instance_type}: {usd_price_str}")
                                        break # 해당 타입 가격 찾았으므로 내부 루프 탈출
                                    except (ValueError, TypeError):
                                         print(f"경고: {instance_type}의 온디맨드 가격 파싱 실패 (값: {usd_price_str}).")
                                else:
                                     # 다른 PriceDimension 확인 필요할 수 있음 (복잡도 증가)
                                     pass
                        if found_price: break # 페이지 내에서 찾았으면 다음 페이지 불필요
                    if found_price: break # 페이지 처리 중 찾았으면 다음 페이지 불필요

                 if not found_price:
                      print(f"정보: {instance_type} ({region}, Linux) 온디맨드 가격 정보를 API에서 찾을 수 없습니다.")

             except botocore.exceptions.ClientError as ce:
                  if ce.response['Error']['Code'] == 'ThrottlingException':
                      print(f"경고: Pricing API 호출 제한 발생 ({instance_type}). 잠시 후 재시도하거나 요청 빈도 조절 필요.")
                      # 재시도 로직 추가 가능 (단순화를 위해 여기서는 생략)
                  else:
                      print(f"오류: {instance_type} 온디맨드 가격 조회 중 AWS API 오류 발생: {ce}")
             except Exception as e:
                  print(f"오류: {instance_type} 온디맨드 가격 조회 중 예기치 않은 오류 발생: {e}")
                  # 개별 인스턴스 조회 실패 시 계속 진행

        print(f"온디맨드 가격 조회 완료: {len(ondemand_prices)} / {len(processed_types)} 고유 유형의 가격 확인.")
        return ondemand_prices

    except botocore.exceptions.NoCredentialsError:
        print("오류: AWS 자격 증명을 찾을 수 없습니다. Pricing API 접근이 불가능합니다.")
        return {}
    except Exception as e:
        print(f"오류: Pricing API 클라이언트 생성 또는 호출 중 예기치 않은 오류 발생: {e}")
        return {}

def get_region_location(region_name):
    """AWS 리전 코드를 Pricing API Location 필터 값으로 변환합니다."""
    # AWS 공식 문서 또는 DescribeRegions API를 참고하여 매핑
    # 예시: https://docs.aws.amazon.com/general/latest/gr/rande.html#ec2_region
    # 예시: https://docs.aws.amazon.com/pricing/latest/userguide/regions-finding-prices.html
    region_map = {
        'us-east-1': 'US East (N. Virginia)',
        'us-east-2': 'US East (Ohio)',
        'us-west-1': 'US West (N. California)',
        'us-west-2': 'US West (Oregon)',
        'af-south-1': 'Africa (Cape Town)',
        'ap-east-1': 'Asia Pacific (Hong Kong)',
        'ap-south-1': 'Asia Pacific (Mumbai)',
        'ap-northeast-3': 'Asia Pacific (Osaka)',
        'ap-northeast-2': 'Asia Pacific (Seoul)',
        'ap-southeast-1': 'Asia Pacific (Singapore)',
        'ap-southeast-2': 'Asia Pacific (Sydney)',
        'ap-northeast-1': 'Asia Pacific (Tokyo)',
        'ca-central-1': 'Canada (Central)',
        'eu-central-1': 'Europe (Frankfurt)',
        'eu-west-1': 'Europe (Ireland)',
        'eu-west-2': 'Europe (London)',
        'eu-south-1': 'Europe (Milan)',
        'eu-west-3': 'Europe (Paris)',
        'eu-north-1': 'Europe (Stockholm)',
        'me-south-1': 'Middle East (Bahrain)',
        'sa-east-1': 'South America (Sao Paulo)'
        # 필요한 리전 추가
    }
    location = region_map.get(region_name)
    if not location:
        print(f"경고: 리전 코드 '{region_name}'에 대한 Location 매핑을 찾을 수 없습니다. Location 필터링 없이 진행될 수 있습니다.")
    return location


def calculate_ondemand_cost(duration_seconds, hourly_price):
    """시간당 온디맨드 가격과 사용 시간(초)으로 비용을 계산합니다."""
    if duration_seconds is None or hourly_price is None or hourly_price < 0:
        return 0.0
    try:
        # duration_seconds가 음수일 수 없음 (호출 전에 체크 필요)
        if duration_seconds < 0:
             print(f"경고: 온디맨드 비용 계산 시 음수 Duration ({duration_seconds}) 감지. 0으로 처리.")
             duration_seconds = 0.0
        duration_hours = float(duration_seconds) / 3600.0
        cost = duration_hours * float(hourly_price)
        return cost
    except (ValueError, TypeError):
        print(f"오류: 온디맨드 비용 계산 실패 (Duration: {duration_seconds}, Price: {hourly_price})")
        return 0.0


# --- 메인 로직 ---

def main():
    print("스크립트 시작...")
    print(f"인스턴스 사용 데이터 파일: {INSTANCE_USAGE_FILE}")
    print(f"스팟 가격 기록 파일: {SPOT_PRICE_FILE}")
    print(f"출력 파일: {OUTPUT_FILE}")
    print(f"대상 리전: {TARGET_REGION}")

    # 0. 인스턴스 사용 데이터에서 필요한 인스턴스 유형 목록 추출 및 데이터 로드
    instance_types_needed = set()
    all_instance_data = []
    original_header = []
    instance_type_idx, az_idx, start_idx, end_idx, state_idx, duration_idx = -1, -1, -1, -1, -1, -1

    if not os.path.exists(INSTANCE_USAGE_FILE):
        print(f"오류: 인스턴스 사용 데이터 파일을 찾을 수 없습니다 - {INSTANCE_USAGE_FILE}")
        return

    try:
        with open(INSTANCE_USAGE_FILE, 'r', newline='', encoding='utf-8') as infile:
            reader = csv.reader(infile)
            original_header = next(reader, None) # 헤더 읽기
            if not original_header:
                 print(f"오류: {INSTANCE_USAGE_FILE} 파일이 비어 있거나 헤더가 없습니다.")
                 return

            # 필수 컬럼 인덱스 찾기
            try:
                instance_id_idx = original_header.index('instanceID') # 또는 InstanceID
                instance_type_idx = original_header.index('instanceType')
                az_idx = original_header.index('AZ') # 또는 AvailabilityZone
                start_idx = original_header.index('startTime')
                end_idx = original_header.index('stopTime')
                state_idx = original_header.index('status')
                duration_idx = original_header.index('durationSec') # 또는 DurationSeconds
            except ValueError as e:
                print(f"오류: {INSTANCE_USAGE_FILE} 헤더에서 필수 컬럼을 찾을 수 없습니다: {e}. 필요한 컬럼: instanceID, instanceType, AZ, startTime, stopTime, status, durationSec")
                return

            for i, row in enumerate(reader):
                 # 컬럼 수가 헤더와 일치하는지 확인
                 if len(row) == len(original_header):
                     instance_type = row[instance_type_idx].strip()
                     if instance_type:
                         instance_types_needed.add(instance_type)
                     all_instance_data.append(row) # 유효한 행만 저장
                 else:
                      print(f"경고: 행 {i+2}의 컬럼 수가 헤더와 다릅니다 ({len(row)} vs {len(original_header)}). 건너뜀니다: {row}")

    except FileNotFoundError: # 위에서 체크했지만 이중 확인
        print(f"오류: 파일을 찾을 수 없습니다 - {INSTANCE_USAGE_FILE}")
        return
    except Exception as e:
        print(f"오류: {INSTANCE_USAGE_FILE} 파일 읽기 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return

    if not all_instance_data:
        print("처리할 유효한 인스턴스 데이터가 없습니다. 스크립트를 종료합니다.")
        return
    if not instance_types_needed:
         print("인스턴스 사용 데이터에서 유효한 인스턴스 유형을 찾을 수 없습니다.")
         # 필요하다면 여기서 종료

    print(f"온디맨드 가격 조회가 필요한 고유 인스턴스 유형 ({len(instance_types_needed)}개): {sorted(list(instance_types_needed))}")

    # 1. 온디맨드 가격 정보 로드
    ondemand_prices = {}
    if instance_types_needed: # 조회할 유형이 있을 때만 API 호출
        ondemand_prices = get_ondemand_prices(list(instance_types_needed), TARGET_REGION, PRICING_API_REGION)
    if not ondemand_prices and instance_types_needed:
        print("경고: 온디맨드 가격 정보를 하나도 가져오지 못했습니다. 온디맨드 관련 컬럼은 N/A 또는 0으로 채워집니다.")
        # 스크립트를 계속 진행

    # 2. 스팟 가격 기록 로드
    spot_price_history = load_spot_price_history(SPOT_PRICE_FILE)
    if spot_price_history is None:
        # 스팟 가격 파일이 없어도 온디맨드 비용만 계산할 수 있도록 계속 진행할 수 있음
        print("경고: 스팟 가격 정보를 로드하지 못했습니다. 스팟 비용은 0으로 처리됩니다.")
        spot_price_history = defaultdict(list) # 빈 딕셔너리로 초기화


    # 3. 인스턴스 사용 데이터 다시 처리하며 비용 계산하여 새 파일에 쓰기
    processed_count = 0
    error_count = 0
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.writer(outfile)

            # 출력 파일 헤더 작성 (기존 헤더 + 온디맨드 관련 컬럼)
            # 원본 헤더 순서를 최대한 유지하고 뒤에 추가
            output_header = original_header + ['SpotCost', 'OnDemandPricePerHour', 'OnDemandCost']
            # 컬럼명 조정 (필요시)
            output_header[az_idx] = 'AvailabilityZone' # AZ -> AvailabilityZone 통일
            output_header[duration_idx] = 'DurationSeconds' # durationSec -> DurationSeconds 통일
            writer.writerow(output_header)

            # 저장된 원본 데이터 처리
            for i, row in enumerate(all_instance_data):
                 # row는 이미 유효성 검사를 거쳤다고 가정
                instance_id = row[instance_id_idx]
                instance_type = row[instance_type_idx]
                az = row[az_idx]
                start_time_str = row[start_idx]
                end_time_str = row[end_idx]
                state = row[state_idx]
                duration_sec_str = row[duration_idx]

                start_time = parse_datetime(start_time_str)
                end_time = parse_datetime(end_time_str)

                 # DurationSeconds 파싱 (실행 중인 경우 end_time이 없어 계산 불가)
                duration_seconds = None
                if start_time and end_time and end_time > start_time:
                    try:
                        # 직접 계산하거나 기존 값 사용
                        # duration_seconds = (end_time - start_time).total_seconds()
                        if duration_sec_str and duration_sec_str.lower() not in ['nan', '', 'none']:
                            duration_seconds = float(duration_sec_str)
                        else: # duration 값이 없으면 직접 계산
                            duration_seconds = (end_time - start_time).total_seconds()

                    except (ValueError, TypeError):
                        print(f"경고: DurationSeconds 계산/변환 오류 (행 {i+2}): {duration_sec_str}. 직접 계산 시도.")
                if start_time and end_time:
                            duration_seconds = (end_time - start_time).total_seconds()


                # 스팟 비용 계산
                spot_cost = 0.0
                if start_time and end_time and duration_seconds is not None and duration_seconds > 0:
                    spot_cost = calculate_instance_cost(instance_type, az, start_time, end_time, spot_price_history)
                formatted_spot_cost = f"{spot_cost:.6f}"

                # 온디맨드 가격 조회 및 비용 계산
                ondemand_price = ondemand_prices.get(instance_type) # 미리 로드한 가격 사용
                ondemand_cost = 0.0
                if ondemand_price is not None and duration_seconds is not None and duration_seconds > 0:
                    ondemand_cost = calculate_ondemand_cost(duration_seconds, ondemand_price)

                formatted_ondemand_price = f"{ondemand_price:.6f}" if ondemand_price is not None else "N/A"
                formatted_ondemand_cost = f"{ondemand_cost:.6f}"

                # DurationSeconds 포맷팅 (소수점 2자리 또는 빈 문자열)
                formatted_duration = f"{duration_seconds:.2f}" if duration_seconds is not None else ''

                # 결과 쓰기 (원본 데이터 + 추가 컬럼)
                output_row = row[:duration_idx] + [formatted_duration] + row[duration_idx+1:] + \
                            [formatted_spot_cost, formatted_ondemand_price, formatted_ondemand_cost]
                writer.writerow(output_row)
                processed_count += 1

    print("-" * 30)
    print(f"처리 완료.")
    print(f"총 처리된 행: {processed_count}")
    # print(f"오류/건너뛴 행: {error_count}") # 에러 카운팅 로직 필요시 추가
    print(f"결과가 {OUTPUT_FILE}에 저장되었습니다.")

if __name__ == "__main__":
    main()
