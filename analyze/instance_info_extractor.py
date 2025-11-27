import subprocess
import os
import sys
import json # JSON 파싱을 위해 추가 (필요 시)

# --- 설정 ---
# 분석할 인스턴스 ID 목록 (이 부분을 실제 분석 대상 ID로 수정해야 합니다)
# 예시: TARGET_INSTANCE_IDS = ['i-0555a84a0dd27adb8', 'i-0783a17b2a88112c8']
TARGET_INSTANCE_IDS = [
    'i-xxxxxxxxxxxxxxxxx', # <--- 실제 인스턴스 ID로 변경하세요
    'i-yyyyyyyyyyyyyyyyy'  # <--- 실제 인스턴스 ID로 변경하세요
]

# 실행할 스크립트 파일명 (이 스크립트와 같은 디렉토리에 있다고 가정)
GET_CALLISTO_SCRIPT = 'getCallistoEvent.py'
GET_SPOT_PRICE_SCRIPT = 'getSpotPriceEvent.py'
GET_MERGE_USAGE_SCRIPT = 'getMergeUsage.py'

# 스크립트 간 전달/사용될 파일명 (각 스크립트 내부의 상수와 일치해야 함)
# getCallistoEvent.py의 출력 파일이자 getSpotPriceEvent.py, getMergeUsage.py의 입력 파일
INSTANCE_USAGE_FILE = 'instance_usage_data_filtered.csv'
# getSpotPriceEvent.py의 출력 파일이자 getMergeUsage.py의 입력 파일
SPOT_PRICE_FILE = 'spot_price_history.csv'
# getMergeUsage.py의 최종 출력 파일 (getMergeUsage.py 내부의 OUTPUT_FILE 상수 확인 필요)
MERGED_OUTPUT_FILE = 'merged_instance_cost.csv'

# 스크립트가 위치한 디렉토리
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def update_target_instance_ids_in_script(script_path, instance_ids):
    """
    지정된 스크립트 파일 내의 TARGET_INSTANCE_IDS 목록을 업데이트합니다.
    주의: 이 방식은 스크립트 파일을 직접 수정하므로 원본 보존 및 형식 유지에 유의해야 합니다.
    """
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        updated = False
        new_lines = []
        for line in lines:
            # TARGET_INSTANCE_IDS 라인을 찾아서 교체
            if line.strip().startswith('TARGET_INSTANCE_IDS ='):
                # 주석 처리된 라인이나 다른 변수 할당과 혼동되지 않도록 주의
                indent = line[:line.find('TARGET_INSTANCE_IDS')]
                id_list_str = '[' + ', '.join(f"'{id_}'" for id_ in instance_ids) + ']'
                new_lines.append(f"{indent}TARGET_INSTANCE_IDS = {id_list_str}\n")
                print(f"알림: {os.path.basename(script_path)}의 TARGET_INSTANCE_IDS를 업데이트했습니다.")
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            print(f"경고: {os.path.basename(script_path)}에서 'TARGET_INSTANCE_IDS =' 라인을 찾지 못했습니다. 수동 업데이트가 필요할 수 있습니다.")
            return False # 업데이트 실패 시 False 반환

        # 변경된 내용으로 파일 다시 쓰기
        with open(script_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        return True

    except FileNotFoundError:
        print(f"오류: 스크립트 파일을 찾을 수 없습니다 - {script_path}")
        return False
    except Exception as e:
        print(f"오류: {os.path.basename(script_path)} 파일 업데이트 중 오류 발생: {e}")
        return False


def run_script(script_name, args=None):
    """지정된 파이썬 스크립트를 실행합니다."""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    if not os.path.exists(script_path):
        print(f"오류: 스크립트 파일을 찾을 수 없습니다 - {script_path}")
        return False

    command = [sys.executable, script_path]
    if args:
        command.extend(args)

    print(f"\n--- 실행 시작: {script_name} {' '.join(args) if args else ''} ---")
    try:
        # 스크립트를 현재 디렉토리에서 실행 (상대 경로 파일 접근 용이)
        process = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', cwd=SCRIPT_DIR)
        print(f"--- 출력 ({script_name}) ---")
        print(process.stdout)
        if process.stderr:
            # 표준 오류 출력을 경고 또는 정보로 처리할 수 있음 (예: boto3의 rate limit 경고)
            print(f"--- 표준 오류 출력 ({script_name}) ---")
            print(process.stderr)
        print(f"--- 실행 완료: {script_name} ---")
        return True
    except FileNotFoundError:
        print(f"오류: 파이썬 인터프리터를 찾을 수 없습니다. '{sys.executable}'")
        return False
    except subprocess.CalledProcessError as e:
        print(f"오류: {script_name} 실행 중 오류 발생 (반환 코드: {e.returncode})")
        print(f"--- stdout ---")
        print(e.stdout)
        print(f"--- stderr ---")
        print(e.stderr)
        return False
    except Exception as e:
        print(f"오류: {script_name} 실행 중 예기치 않은 오류 발생: {e}")
        return False

def verify_file_creation(filename, script_name):
    """스크립트 실행 후 파일이 생성되었는지 확인합니다."""
    file_path = os.path.join(SCRIPT_DIR, filename)
    if not os.path.exists(file_path):
         print(f"오류: {script_name} 실행 후 예상 출력 파일({filename})이 생성되지 않았습니다.")
         return False
    print(f"성공: {filename} 파일 생성 확인.")
    return True

def main():
    """스크립트 실행을 조율합니다."""
    print("인스턴스 정보 추출 및 비용 분석 파이프라인 시작...")

    # 입력 인스턴스 ID 유효성 검사
    if not TARGET_INSTANCE_IDS or any(id_.startswith('i-x') or id_.startswith('i-y') for id_ in TARGET_INSTANCE_IDS):
         print("오류: TARGET_INSTANCE_IDS 목록이 비어 있거나 플레이스홀더 ID를 포함합니다.")
         print(f"{__file__} 파일 상단의 TARGET_INSTANCE_IDS 목록을 유효한 인스턴스 ID로 수정해주세요.")
         return
    print(f"대상 인스턴스 ID ({len(TARGET_INSTANCE_IDS)}개): {TARGET_INSTANCE_IDS}")

    # 0단계: getCallistoEvent.py의 인스턴스 ID 목록 업데이트
    # 주의: 이 방식은 getCallistoEvent.py 파일을 직접 수정합니다.
    print("\n[0단계] getCallistoEvent.py의 대상 인스턴스 ID 업데이트 시도...")
    callisto_script_path = os.path.join(SCRIPT_DIR, GET_CALLISTO_SCRIPT)
    if not update_target_instance_ids_in_script(callisto_script_path, TARGET_INSTANCE_IDS):
        print("경고: getCallistoEvent.py의 인스턴스 ID 자동 업데이트 실패. 스크립트 내 ID가 올바른지 확인하세요.")
        # 계속 진행할지 여부 결정 (여기서는 경고 후 계속 진행)

    # 1단계: CloudTrail 이벤트 가져오기 (getCallistoEvent.py)
    # 출력: INSTANCE_USAGE_FILE ('instance_usage_data_filtered.csv')
    print("\n[1단계] CloudTrail 이벤트 조회 및 인스턴스 사용 데이터 생성...")
    if not run_script(GET_CALLISTO_SCRIPT):
        print("오류: 1단계 실행 실패. 파이프라인 중단.")
        return
    if not verify_file_creation(INSTANCE_USAGE_FILE, GET_CALLISTO_SCRIPT):
        print("파이프라인 중단.")
        return

    # 2단계: 스팟 가격 기록 가져오기 (getSpotPriceEvent.py)
    # 입력: INSTANCE_USAGE_FILE ('instance_usage_data_filtered.csv')
    # 출력: SPOT_PRICE_FILE ('spot_price_history.csv')
    # 참고: getSpotPriceEvent.py 내부의 INSTANCE_USAGE_CSV 상수가 INSTANCE_USAGE_FILE 값과 일치해야 합니다.
    print("\n[2단계] 스팟 가격 기록 조회...")
    if not run_script(GET_SPOT_PRICE_SCRIPT):
        print("오류: 2단계 실행 실패. 파이프라인 중단.")
        return
    if not verify_file_creation(SPOT_PRICE_FILE, GET_SPOT_PRICE_SCRIPT):
        print("파이프라인 중단.")
        return

    # 3단계: 사용량 및 가격 병합 (getMergeUsage.py)
    # 입력: INSTANCE_USAGE_FILE, SPOT_PRICE_FILE
    # 출력: MERGED_OUTPUT_FILE ('merged_instance_cost.csv')
    # 참고: getMergeUsage.py 내부의 INSTANCE_USAGE_FILE, SPOT_PRICE_FILE, OUTPUT_FILE 상수가
    #       이 스크립트의 INSTANCE_USAGE_FILE, SPOT_PRICE_FILE, MERGED_OUTPUT_FILE 값과 일치해야 합니다.
    print("\n[3단계] 인스턴스 사용량과 스팟/온디맨드 가격 병합 및 비용 계산...")
    if not run_script(GET_MERGE_USAGE_SCRIPT):
        print("오류: 3단계 실행 실패. 파이프라인 중단.")
        return
    if not verify_file_creation(MERGED_OUTPUT_FILE, GET_MERGE_USAGE_SCRIPT):
        # 최종 파일 생성 실패는 경고로 처리할 수도 있음
        print(f"경고: 최종 출력 파일({MERGED_OUTPUT_FILE}) 생성 확인 실패.")
    else:
        print(f"성공: 최종 결과 파일 {MERGED_OUTPUT_FILE} 생성 확인.")

    print("\n파이프라인 실행 완료.")

if __name__ == "__main__":
    main()
