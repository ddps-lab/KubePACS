from datetime import datetime, timedelta, timezone
import pickle
import boto3
from botocore.exceptions import ClientError
from kubernetes import client, config
import os
import dotenv

dotenv.load_dotenv()

session = boto3.Session(profile_name=os.getenv("AWS_PROFILE"))

def get_eks_vpc_id(cluster_name: str, region: str) -> str | None:
    """
    지정된 EKS 클러스터 이름과 리전을 기반으로 해당 클러스터의 VPC ID를 조회합니다.

    Args:
        cluster_name: 조회할 EKS 클러스터의 이름입니다.
        region: 해당 EKS 클러스터가 위치한 AWS 리전입니다.

    Returns:
        성공적으로 조회된 경우 VPC ID 문자열을 반환하고,
        클러스터를 찾을 수 없거나 오류가 발생한 경우 None을 반환합니다.
    """
    try:
        # 지정된 리전에 대한 EKS 클라이언트 생성
        eks_client = session.client('eks', region_name=region)

        print(f"리전 '{region}'에서 EKS 클러스터 '{cluster_name}'의 정보를 조회합니다...")

        # EKS 클러스터 상세 정보 요청
        response = eks_client.describe_cluster(name=cluster_name)

        # 응답에서 VPC ID 추출
        # response['cluster']['resourcesVpcConfig']['vpcId'] 경로를 안전하게 탐색
        vpc_config = response.get('cluster', {}).get('resourcesVpcConfig', {})
        vpc_id = vpc_config.get('vpcId')

        if vpc_id:
            print(f"클러스터 '{cluster_name}'의 VPC ID: {vpc_id}")
            return vpc_id
        else:
            print(f"오류: 클러스터 '{cluster_name}'의 응답에서 VPC ID 정보를 찾을 수 없습니다.")
            return None

    except ClientError as e:
        # AWS API 오류 처리
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"오류: 리전 '{region}'에서 클러스터 '{cluster_name}'을(를) 찾을 수 없습니다.")
        else:
            print(f"AWS API 오류 발생: {e}")
        return None
    except Exception as e:
        # 기타 예외 처리 (네트워크 문제, 설정 오류 등)
        print(f"VPC ID 조회 중 예상치 못한 오류 발생: {e}")
        return None

import boto3
from botocore.exceptions import ClientError

def get_subnets_by_az_for_vpc(vpc_id: str, region: str) -> dict[str, list[str]] | None:
    """
    지정된 VPC ID와 리전을 기반으로 가용 영역(AZ)별 서브넷 ID 목록을 조회합니다.

    Args:
        vpc_id: 서브넷을 조회할 VPC의 ID입니다.
        region: 해당 VPC가 위치한 AWS 리전입니다.

    Returns:
        성공적으로 조회된 경우 가용 영역 이름을 키로, 해당 영역의 서브넷 ID 리스트를 값으로 하는
        딕셔너리를 반환합니다. 오류 발생 시 None을 반환합니다.
        예: {'ap-northeast-2a': ['subnet-123', 'subnet-456'], 'ap-northeast-2c': ['subnet-789']}
    """
    try:
        # 지정된 리전에 대한 EC2 클라이언트 생성
        # session = boto3.Session(profile_name="your_profile_name") # 필요시 프로필 사용
        # ec2_client = session.client('ec2', region_name=region)
        ec2_client = session.client('ec2', region_name=region) # 기본 자격 증명 사용

        print(f"리전 '{region}'의 VPC '{vpc_id}' 내 서브넷 정보를 조회합니다...")

        # VPC ID로 서브넷 필터링하여 조회
        # 페이지네이션을 고려해야 할 수 있으나, 일반적인 VPC 내 서브넷 수는 많지 않으므로 여기서는 생략
        response = ec2_client.describe_subnets(
            Filters=[
                {
                    'Name': 'vpc-id',
                    'Values': [vpc_id]
                },
            ]
        )

        subnets_by_az = {}
        subnets = response.get('Subnets', [])

        if not subnets:
            print(f"경고: VPC '{vpc_id}' 내에서 서브넷을 찾을 수 없습니다. VPC ID를 확인하거나 해당 VPC에 서브넷이 있는지 확인하세요.")
            # VPC는 존재하지만 서브넷이 없는 경우 빈 딕셔너리 반환
            return {}

        for subnet in subnets:
            az = subnet.get('AvailabilityZone')
            subnet_id = subnet.get('SubnetId')

            if az and subnet_id:
                if az not in subnets_by_az:
                    subnets_by_az[az] = []
                subnets_by_az[az].append(subnet_id)

        print(f"VPC '{vpc_id}'의 가용 영역별 서브넷 정보:")
        for az, ids in subnets_by_az.items():
            print(f" - {az}: {ids}")

        return subnets_by_az

    except ClientError as e:
        # AWS API 오류 처리
        error_code = e.response.get('Error', {}).get('Code')
        if error_code == 'InvalidVpcID.NotFound':
             print(f"오류: VPC ID '{vpc_id}'가 리전 '{region}'에 존재하지 않습니다.")
        else:
             print(f"AWS API 오류 발생 (서브넷 조회 중): {e}")
        # VPC ID가 잘못되었거나 권한 문제일 수 있음
        return None
    except Exception as e:
        # 기타 예외 처리
        print(f"서브넷 조회 중 예상치 못한 오류 발생: {e}")
        return None

def get_security_groups_for_vpc(vpc_id: str, region: str) -> list[str] | None:
    """
    주어진 VPC ID에 연결된 모든 보안 그룹 ID를 조회합니다.

    Args:
        vpc_id: 보안 그룹을 조회할 VPC의 ID.
        region: AWS 리전.

    Returns:
        VPC에 연결된 보안 그룹 ID 목록. 오류 발생 시 None을 반환합니다.
    """
    if not vpc_id:
        print("오류: VPC ID가 제공되지 않았습니다.")
        return None

    try:
        # Boto3 EC2 클라이언트 생성 (세션 사용 가정, 없으면 기본 세션 사용)
        ec2_client = session.client('ec2', region_name=region)
        print(f"리전 '{region}'의 VPC '{vpc_id}'에 대한 보안 그룹 정보를 조회합니다...")

        # VPC ID로 보안 그룹 필터링하여 조회
        response = ec2_client.describe_security_groups(
            Filters=[
                {
                    'Name': 'vpc-id',
                    'Values': [vpc_id]
                },
            ]
        )

        security_groups = response.get('SecurityGroups', [])
        security_group_ids = [sg.get('GroupId') for sg in security_groups if sg.get('GroupId')]

        if not security_group_ids:
            print(f"정보: VPC '{vpc_id}' 내에서 보안 그룹을 찾을 수 없습니다.")
            # 보안 그룹이 없는 것도 정상적인 상황일 수 있으므로 빈 리스트 반환
            return []
        else:
            print(f"VPC '{vpc_id}'의 보안 그룹 ID 목록: {security_group_ids}")
            return security_group_ids

    except ClientError as e:
        # AWS API 오류 처리
        error_code = e.response.get('Error', {}).get('Code')
        if error_code == 'InvalidVpcID.NotFound':
             print(f"오류: VPC ID '{vpc_id}'가 리전 '{region}'에 존재하지 않습니다.")
        else:
             print(f"AWS API 오류 발생 (보안 그룹 조회 중): {e}")
        # VPC ID가 잘못되었거나 권한 문제일 수 있음
        return None
    except Exception as e:
        # 기타 예외 처리
        print(f"보안 그룹 조회 중 예상치 못한 오류 발생: {e}")
        return None

def get_bottlerocket_ami_id(region: str, instance_type: str) -> str | None:
    instance_type = instance_type.lower()
    arm_prefixes = ('a1.', 't4g.', 'm6g.', 'c6g.', 'c6gn', 'r6g.', 'x2gd.', 'im4g.', 'is4g.', 'g5g.', 'hpc7g.', 'm7g.', 'c7g.', 'r7g.', "m8g.", "c8g.", "r8g.", "x8g.", "i8g")

    is_arm64 = False
    for prefix in arm_prefixes:
        if instance_type.startswith(prefix):
            is_arm64 = True
            break

    if is_arm64:
        print(f"인스턴스 유형 '{instance_type}'은(는) ARM64 아키텍처로 확인되었습니다.")
    else:
        print(f"인스턴스 유형 '{instance_type}'은(는) x86_64 아키텍처로 확인되었습니다.")
    try:
        ssm_client = session.client('ssm', region_name=region) # 기본 자격 증명 사용
        if is_arm64:
            parameter_name = "/aws/service/bottlerocket/aws-k8s-1.32/arm64/latest/image_id"
        else:
            parameter_name = "/aws/service/bottlerocket/aws-k8s-1.32/x86_64/latest/image_id"
        print(f"리전 '{region}'에서 SSM 파라미터 '{parameter_name}'의 값을 조회합니다...")

        # SSM 파라미터 값 가져오기 요청
        response = ssm_client.get_parameter(Name=parameter_name)

        # 응답에서 파라미터 값(AMI ID) 추출
        ami_id = response.get('Parameter', {}).get('Value')

        if ami_id:
            print(f"SSM 파라미터 '{parameter_name}'에서 AMI ID '{ami_id}'를 성공적으로 조회했습니다.")
            return ami_id
        else:
            # 일반적으로 get_parameter는 파라미터가 있으면 값을 반환하므로 이 경우는 드묾
            print(f"오류: SSM 파라미터 '{parameter_name}'의 응답에서 'Value'를 찾을 수 없습니다.")
            return None

    except ClientError as e:
        # AWS API 오류 처리
        if e.response['Error']['Code'] == 'ParameterNotFound':
            print(f"오류: 리전 '{region}'에서 SSM 파라미터 '{parameter_name}'을(를) 찾을 수 없습니다.")
        else:
            print(f"AWS SSM API 오류 발생: {e}")
        return None
    except Exception as e:
        # 기타 예외 처리
        print(f"Bottlerocket AMI ID 조회 중 예상치 못한 오류 발생: {e}")
        return None
    

def get_kube_dns_ip(kubeconfig_path):
    """kubernetes 클라이언트로 kube-dns 서비스 IP 조회"""
    config.load_kube_config(config_file=kubeconfig_path)
    v1 = client.CoreV1Api()
    svc = v1.read_namespaced_service(name="kube-dns", namespace="kube-system")
    return svc.spec.cluster_ip

def get_karpenter_instance_ids(kubeconfig_path, start_time, end_time):
    import subprocess
    import re
    from datetime import datetime, timezone, timedelta
    import os # os.path.expanduser 사용

    # Helper 함수: datetime 객체가 timezone 정보를 가지도록 보장 (UTC 기준)
    def ensure_timezone_aware(dt):
        """datetime 객체가 timezone 정보를 가지도록 보장 (UTC 기준)."""
        if not isinstance(dt, datetime):
            raise TypeError("start_time 및 end_time은 datetime 객체여야 합니다.")
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            # timezone 정보가 없는 경우 UTC로 간주
            return dt.replace(tzinfo=timezone.utc)
        # timezone 정보가 있는 경우 UTC로 변환
        return dt.astimezone(timezone.utc)

    # kubeconfig 경로 처리 (예: ~ 확장)
    kubeconfig_path_expanded = os.path.expanduser(kubeconfig_path)
    if not os.path.exists(kubeconfig_path_expanded):
        print(f"오류: Kubeconfig 파일을 찾을 수 없습니다: {kubeconfig_path_expanded}")
        return []

    # start_time과 end_time을 timezone-aware UTC로 변환
    try:
        start_time_utc = ensure_timezone_aware(start_time)
        end_time_utc = ensure_timezone_aware(end_time)
    except TypeError as e:
        print(f"오류: {e}")
        return []

    # kubectl 명령어 구성
    # --since-time 플래그는 로그 시작 시간을 지정하여 가져오는 로그 양을 줄일 수 있음
    # Karpenter 로그는 자체적으로 타임스탬프를 포함하므로 --timestamps=false 사용
    # 약간의 버퍼를 위해 start_time보다 조금 더 이전부터 로그를 가져올 수 있음 (선택 사항)
    # buffer_time = start_time_utc - timedelta(minutes=1)
    cmd = [
        "kubectl",
        "--kubeconfig", kubeconfig_path_expanded,
        "logs",
        "deployment/karpenter", # 'deploy/' 대신 'deployment/' 사용이 더 일반적
        "--namespace", "karpenter",
        # "--since-time", buffer_time.isoformat(timespec='seconds') + 'Z', # 버퍼 사용 시
        "--since=0s", # 가능한 모든 로그를 가져오도록 설정 (시간 필터링은 파이썬에서 수행)
        "--timestamps=false"
    ]

    print(f"Karpenter 로그 조회 명령어 실행: {' '.join(cmd)}")

    instance_ids_found = set()

    try:
        # kubectl 명령어 실행
        # check=False로 설정하여 오류 발생 시 예외 대신 returncode 확인
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, encoding='utf-8')
        print(result)
        # 명령어 실행 결과 확인
        if result.returncode != 0:
            print(f"오류: kubectl 명령어 실행 실패 (종료 코드: {result.returncode})")
            stderr_output = result.stderr.strip()
            print(f"stderr:\n{stderr_output}")
            if "NotFound" in stderr_output or "not found" in stderr_output:
                print("진단: 'deployment/karpenter'를 'karpenter' 네임스페이스에서 찾을 수 없습니다. Karpenter 설치 및 네임스페이스를 확인하세요.")
            elif "error: You must be logged in to the server" in stderr_output:
                 print("진단: Kubernetes 클러스터 인증에 실패했습니다. kubeconfig 파일 또는 인증 상태를 확인하세요.")
            elif "connect: connection refused" in stderr_output:
                 print("진단: Kubernetes API 서버에 연결할 수 없습니다. 클러스터 상태 및 네트워크 연결을 확인하세요.")
            return [] # 오류 발생 시 빈 리스트 반환

        logs = result.stdout
        if not logs:
            print("정보: Karpenter 로그가 비어 있습니다.")
            return []

        # 로그 라인 파싱을 위한 정규 표현식
        # 타임스탬프: ISO 8601 형식 (YYYY-MM-DDTHH:MM:SS.ffffffZ)
        # 인스턴스 ID: i-xxxxxxxxxxxxxxxxx 또는 i-xxxxxxxx (8자리 또는 17자리 hex)
        timestamp_pattern = re.compile(r'"time":"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)"')
        instance_id_pattern = re.compile(r"(i-[0-9a-f]{17})")

        print(f"로그 파싱 시작: 시간 범위 [{start_time_utc.isoformat()}, {end_time_utc.isoformat()}]")
        lines_processed = 0
        ids_in_range = 0

        for line in logs.splitlines():
            lines_processed += 1
            print(f"\\nDEBUG: Processing line {lines_processed}: {line[:300]}...") # Log more characters
            # Use re.search() instead of re.match() to find the pattern anywhere in the line
            timestamp_match = timestamp_pattern.search(line)
            if timestamp_match:
                timestamp_str = timestamp_match.group(1)
                print(f"DEBUG: Matched timestamp_str: {timestamp_str}")
                try:
                    # 타임스탬프 문자열 파싱 (밀리초 유무 처리)
                    if '.' in timestamp_str:
                        # Ensure parsing matches the exact format, including 'Z'
                        if 'Z' in timestamp_str and timestamp_str.endswith('Z'):
                            log_time = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                        else: # If Z is not at the end or missing, this might be an issue or a different format
                            print(f"DEBUG: Timestamp '{timestamp_str}' has '.' but 'Z' is not at the end or is missing. Attempting without 'Z'.")
                            log_time = datetime.strptime(timestamp_str.rstrip('Z'), "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)

                    else:
                        # Ensure parsing matches the exact format, including 'Z'
                        if 'Z' in timestamp_str and timestamp_str.endswith('Z'):
                            log_time = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        else: # If Z is not at the end or missing
                            print(f"DEBUG: Timestamp '{timestamp_str}' does not have '.' and 'Z' is not at the end or is missing. Attempting without 'Z'.")
                            log_time = datetime.strptime(timestamp_str.rstrip('Z'), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)

                    print(f"DEBUG: Parsed log_time: {log_time.isoformat()}, Start: {start_time_utc.isoformat()}, End: {end_time_utc.isoformat()}")

                    # 로그 시간이 지정된 범위 내에 있는지 확인
                    if start_time_utc <= log_time <= end_time_utc:
                        print(f"DEBUG: Timestamp IS IN RANGE.")
                        # 해당 라인에서 인스턴스 ID 검색
                        found_ids = instance_id_pattern.findall(line)
                        print(f"DEBUG: Found instance IDs in line: {found_ids}")
                        if found_ids:
                            for inst_id in found_ids:
                                if inst_id not in instance_ids_found:
                                    print(f"DEBUG: Adding new instance ID: {inst_id} (from line with time {log_time.isoformat()})")
                                    instance_ids_found.add(inst_id)
                                    ids_in_range += 1
                    else:
                        # 더 자세한 비교를 위해 각 값 출력
                        print(f"DEBUG: Timestamp IS OUT OF RANGE. " +
                              f"start_time_utc ({start_time_utc.isoformat()}) <= log_time ({log_time.isoformat()}) is {start_time_utc <= log_time}. " +
                              f"log_time ({log_time.isoformat()}) <= end_time_utc ({end_time_utc.isoformat()}) is {log_time <= end_time_utc}.")

                except ValueError as e_parse:
                    print(f"DEBUG: Timestamp parsing FAILED for '{timestamp_str}': {e_parse}")
                    continue
            else:
                print(f"DEBUG: Timestamp pattern did NOT match for line beginning with: {line[:50]}") # Print start of line
                # Consider if the log format might change or if some lines don't have timestamps

        print(f"로그 파싱 완료: {lines_processed} 라인 처리, {ids_in_range} 개의 유니크한 인스턴스 ID를 시간 범위 내에서 찾음.")

    except FileNotFoundError:
        print(f"오류: 'kubectl' 명령어를 찾을 수 없습니다. 시스템 PATH 환경 변수를 확인하거나 kubectl을 설치하세요.")
        return []
    except Exception as e:
        print(f"Karpenter 로그 처리 중 예상치 못한 오류 발생: {e}")
        import traceback
        traceback.print_exc() # 예상치 못한 오류 디버깅을 위한 스택 트레이스 출력
        return []

    # 찾은 인스턴스 ID 목록을 정렬하여 반환
    final_instance_list = sorted(list(instance_ids_found))

    return final_instance_list

# # 함수 사용 예시 (필요한 경우 주석 해제하여 테스트)
if __name__ == "__main__":
    get_karpenter_instance_ids("~/.kube/config", datetime.now(timezone.utc) - timedelta(hours=1), datetime.now(timezone.utc))
    # 실제 클러스터 이름과 리전으로 변경하세요
    # my_cluster_name = "callisto-k8s-cluster-prod-mq2"
    # my_region = "ap-northeast-2"

    # retrieved_vpc_id = get_eks_vpc_id(my_cluster_name, my_region)
    # retrieved_subnets = get_subnets_by_az_for_vpc(retrieved_vpc_id, my_region)
    # retrieved_security_groups = get_security_groups_for_vpc(retrieved_vpc_id, my_region)
    # retrieved_bottlerocket_ami_id = get_bottlerocket_ami_id("us-east-1")
    # retrieved_kube_dns_ip = get_kube_dns_ip("~/.kube/config")

    # if retrieved_vpc_id:
    #     print(f"\n성공적으로 VPC ID를 조회했습니다: {retrieved_vpc_id}")
    #     print(f"성공적으로 서브넷 정보를 조회했습니다: {retrieved_subnets}")
    #     print(f"성공적으로 보안 그룹 정보를 조회했습니다: {retrieved_security_groups}")
    #     print(f"성공적으로 Bottlerocket AMI ID를 조회했습니다: {retrieved_bottlerocket_ami_id}")
    #     print(f"성공적으로 kube-dns 서비스 IP를 조회했습니다: {retrieved_kube_dns_ip}")
    # else:
    #     print("\nVPC ID 조회에 실패했습니다.")