import csv
import boto3
from datetime import datetime, timedelta, timezone
import os
from collections import defaultdict
import botocore # boto3 예외 처리를 위해 명시적으로 import 할 수 있습니다.

# --- 스크립트 설정 ---
INSTANCE_USAGE_CSV = 'instance_usage_data.csv' # 인스턴스 유형을 가져올 CSV 파일
REGION_NAME = 'us-east-1'        # 조회할 AWS 리전
DAYS_TO_LOOK_BACK = 2                 # 조회할 과거 기간 (일)
OUTPUT_CSV_FILENAME = 'spot_price_history.csv' # 결과를 저장할 CSV 파일 이름

def get_unique_instance_types_from_csv(csv_filepath):
    """
    CSV 파일을 읽어 두 번째 열에 있는 고유 인스턴스 유형 목록을 반환합니다.

    Args:
        csv_filepath (str): 읽을 CSV 파일의 경로.

    Returns:
        list: 고유 인스턴스 유형 문자열 목록. 파일 읽기 실패 시 빈 목록 반환.
    """
    instance_types = set()
    if not os.path.exists(csv_filepath):
        print(f"오류: CSV 파일을 찾을 수 없습니다 - {csv_filepath}")
        return []

    try:
        # UTF-8 인코딩으로 파일을 엽니다. 다른 인코딩이 필요하면 수정하세요.
        with open(csv_filepath, mode='r', newline='', encoding='utf-8') as infile:
            reader = csv.reader(infile)
            # 제공된 컨텍스트 파일에는 헤더가 없는 것으로 보입니다.
            # 만약 헤더가 있다면 다음 줄의 주석을 해제하세요:
            # next(reader, None)
            for i, row in enumerate(reader):
                # 행에 최소 2개의 열이 있는지 확인합니다.
                if len(row) >= 2:
                    instance_type = row[1].strip() # 두 번째 열(인덱스 1)이 인스턴스 유형입니다. 공백 제거.
                    if instance_type: # 빈 문자열이 아닌 경우에만 추가합니다.
                        instance_types.add(instance_type)
                else:
                    # 행 형식이 예상과 다를 경우 경고를 출력합니다.
                    print(f"경고: {os.path.basename(csv_filepath)} 파일의 {i+1}번째 줄 형식이 잘못되었습니다: {row}")
    except FileNotFoundError:
        # 파일이 중간에 삭제되는 경우 등을 대비해 다시 확인합니다.
        print(f"오류: CSV 파일을 찾을 수 없습니다 - {csv_filepath}")
        return []
    except Exception as e:
        print(f"오류: CSV 파일('{os.path.basename(csv_filepath)}') 읽기 중 오류 발생 - {e}")
        return []

    unique_list = sorted(list(instance_types)) # 결과를 정렬하여 반환
    print(f"CSV 파일에서 찾은 고유 인스턴스 유형 ({len(unique_list)}개): {unique_list}")
    return unique_list

def get_spot_price_history(instance_types, days_to_look_back, region='ap-northeast-2'):
    """
    지정된 리전, 기간 동안 주어진 인스턴스 유형 목록에 대한 스팟 가격 변동 내역을 조회합니다.
    'Linux/UNIX (Amazon VPC)' 제품 설명을 사용합니다.

    Args:
        instance_types (list): 스팟 가격을 조회할 인스턴스 유형 문자열 목록.
        days_to_look_back (int): 조회할 과거 일수.
        region (str): 조회할 AWS 리전 이름.

    Returns:
        list: 각 요소가 가격 변동 기록 딕셔너리인 리스트.
              각 딕셔너리는 'InstanceType', 'AvailabilityZone', 'SpotPrice', 'Timestamp' 키를 포함합니다.
              오류 발생 시 빈 리스트 반환.
    """
    if not instance_types:
        print("조회할 인스턴스 유형이 없습니다.")
        return []

    print(f"{region} 리전에서 지난 {days_to_look_back}일간의 스팟 가격 변동 내역 조회를 시작합니다...")
    try:
        ec2 = boto3.client('ec2', region_name=region)
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(days=days_to_look_back)

        paginator = ec2.get_paginator('describe_spot_price_history')
        all_price_history = []

        # 모든 인스턴스 유형에 대해 페이지네이션하며 조회
        page_iterator = paginator.paginate(
            InstanceTypes=instance_types,
            ProductDescriptions=['Linux/UNIX (Amazon VPC)'],
            StartTime=start_time,
            EndTime=now # EndTime을 명시적으로 현재 시간으로 설정
            # 특정 AZ만 필요한 경우 여기에 AvailabilityZone='...' 파라미터를 추가할 수 있습니다.
        )

        for page in page_iterator:
            all_price_history.extend(page.get('SpotPriceHistory', []))

        if not all_price_history:
            print("지정된 조건에 맞는 스팟 가격 기록을 찾을 수 없습니다.")
            return []

        # 결과를 타임스탬프 기준으로 오름차순 정렬 (선택 사항, CSV 저장 시 순서는 중요하지 않을 수 있음)
        all_price_history.sort(key=lambda x: x['Timestamp'])

        print(f"총 {len(all_price_history)}개의 가격 변동 기록을 찾았습니다.")
        return all_price_history # 모든 기록 반환

    except botocore.exceptions.NoCredentialsError:
        print("오류: AWS 자격 증명을 찾을 수 없습니다. AWS CLI 설정(aws configure), IAM 역할 또는 환경 변수를 확인하세요.")
        return [] # 오류 시 빈 리스트 반환
    except botocore.exceptions.ClientError as e:
        error_code = e.response.get('Error', {}).get('Code')
        error_message = e.response.get('Error', {}).get('Message', str(e))
        print(f"오류: AWS API 호출 중 오류 발생 ({error_code}) - {error_message}")
        return [] # 오류 시 빈 리스트 반환
    except Exception as e:
        print(f"오류: 스팟 가격 조회 중 예기치 않은 오류 발생 - {e}")
        return [] # 오류 시 빈 리스트 반환

def save_price_history_to_csv(price_history, filename):
    """
    스팟 가격 변동 내역 리스트를 CSV 파일로 저장합니다.

    Args:
        price_history (list): 가격 변동 기록 딕셔너리의 리스트.
        filename (str): 저장할 CSV 파일의 이름.
    """
    if not price_history:
        print("저장할 가격 데이터가 없습니다.")
        return

    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            # 컬럼 순서 지정
            fieldnames = ['InstanceType', 'AvailabilityZone', 'SpotPrice', 'Timestamp']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            kst = timezone(timedelta(hours=9)) # KST (UTC+9)
            for record in price_history:
                # 필요한 데이터만 추출하고 Timestamp를 KST로 변환하여 ISO 형식 문자열로 저장
                utc_timestamp = record.get('Timestamp')
                kst_timestamp_str = None
                if utc_timestamp:
                    # Ensure the timestamp is timezone-aware (it should be UTC from AWS)
                    if utc_timestamp.tzinfo is None:
                        utc_timestamp = utc_timestamp.replace(tzinfo=timezone.utc)
                    kst_timestamp = utc_timestamp.astimezone(kst) # Convert to KST
                    kst_timestamp_str = kst_timestamp.isoformat() # Format as ISO string

                row_data = {
                    'InstanceType': record.get('InstanceType'),
                    'AvailabilityZone': record.get('AvailabilityZone'),
                    'SpotPrice': record.get('SpotPrice'),
                    'Timestamp': kst_timestamp_str # Store KST timestamp string
                }
                writer.writerow(row_data)
        print(f"스팟 가격 변동 내역을 '{filename}' 파일로 성공적으로 저장했습니다.")
    except Exception as e:
        print(f"오류: 가격 내역을 CSV 파일('{filename}')로 저장하는 중 오류 발생 - {e}")

# --- 메인 스크립트 실행 로직 ---
if __name__ == "__main__":
    # 스크립트가 위치한 디렉토리를 기준으로 파일 경로 설정
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        current_dir = os.getcwd()

    instance_usage_csv_path = os.path.join(current_dir, INSTANCE_USAGE_CSV)
    output_csv_path = os.path.join(current_dir, OUTPUT_CSV_FILENAME)

    # 1. CSV 파일에서 고유 인스턴스 유형 목록을 가져옵니다.
    unique_instance_types = get_unique_instance_types_from_csv(instance_usage_csv_path)

    if unique_instance_types:
        # 2. 가져온 인스턴스 유형 목록과 설정된 기간을 사용하여 스팟 가격 변동 내역을 조회합니다.
        spot_price_data = get_spot_price_history(
            unique_instance_types,
            days_to_look_back=DAYS_TO_LOOK_BACK,
            region=REGION_NAME
        )

        # 3. 조회 결과를 CSV 파일로 저장합니다.
        if spot_price_data: # 조회된 데이터가 있을 경우에만 저장 시도
            save_price_history_to_csv(spot_price_data, output_csv_path)
        else:
            print("스팟 가격 데이터를 가져오지 못했거나 데이터가 없어 CSV 파일을 생성하지 않습니다.")
    else:
        print(f"'{INSTANCE_USAGE_CSV}'에서 인스턴스 유형을 가져오지 못했거나 파일에 유효한 데이터가 없습니다.")
