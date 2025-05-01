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

def get_bottlerocket_ami_id(region: str) -> str | None:
    try:
        ssm_client = session.client('ssm', region_name=region) # 기본 자격 증명 사용
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

# # 함수 사용 예시 (필요한 경우 주석 해제하여 테스트)
if __name__ == "__main__":
    # 실제 클러스터 이름과 리전으로 변경하세요
    my_cluster_name = "callisto-k8s-cluster-prod-mq2"
    my_region = "ap-northeast-2"

    retrieved_vpc_id = get_eks_vpc_id(my_cluster_name, my_region)
    retrieved_subnets = get_subnets_by_az_for_vpc(retrieved_vpc_id, my_region)
    retrieved_security_groups = get_security_groups_for_vpc(retrieved_vpc_id, my_region)
    retrieved_bottlerocket_ami_id = get_bottlerocket_ami_id("us-east-1")
    retrieved_kube_dns_ip = get_kube_dns_ip("~/.kube/config")

    if retrieved_vpc_id:
        print(f"\n성공적으로 VPC ID를 조회했습니다: {retrieved_vpc_id}")
        print(f"성공적으로 서브넷 정보를 조회했습니다: {retrieved_subnets}")
        print(f"성공적으로 보안 그룹 정보를 조회했습니다: {retrieved_security_groups}")
        print(f"성공적으로 Bottlerocket AMI ID를 조회했습니다: {retrieved_bottlerocket_ami_id}")
        print(f"성공적으로 kube-dns 서비스 IP를 조회했습니다: {retrieved_kube_dns_ip}")
    else:
        print("\nVPC ID 조회에 실패했습니다.")