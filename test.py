import uuid
import lithops
import time
import sys
import os
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

<<<<<<< HEAD
sys.path.append('~/Desktop/KubeCaps/multi_nodepool')
=======
sys.path.append('/Users/taeyoon/Desktop/KubeCaps/multi_nodepool')
>>>>>>> 05e8e39052def73c978b197282c1ebee8cb43e0e
from multi_nodepool.kubecaps_creator import create_eks_nodes, TARGET_REGION
from multi_nodepool.kubecaps_scaler import delete_spot_instance_for_eks, get_instance_id_from_spot_request, wait_for_instance_running



# --- 설정 ---
SPOT_REQUEST_TIMEOUT = 600 # 스팟 요청이 처리되고 인스턴스 ID를 얻기까지 기다리는 최대 시간 (초)
INSTANCE_RUNNING_TIMEOUT = 600 # 인스턴스가 running 상태가 될 때까지 기다리는 최대 시간 (초)
INSTANCE_POLL_INTERVAL = 15 # 인스턴스 상태 확인 간격 (초)

# 생성 POD 사양 정의
RUNTIME_CPU = 1
RUNTIME_MEMORY = 512
MAX_WORKERS = 4

# 생성할 노드 정의
target_instances = [
    {
        "instance_type": "t3.medium",
        "availability_zone": "us-east-1a",
        "num_instances": 1
    },
    {
        "instance_type": "t2.medium",
        "availability_zone": "us-east-1b",
        "num_instances": 1
    }
]


#lithops 설정
lithops_config = {
    "lithops": {
        "backend": "k8s",
        "storage": "aws_s3"
    },
    "k8s": {
        "kubecfg_path": "/Users/taeyoon/.kube/config",
        "docker_user": os.getenv("DOCKER_USER"),
        "docker_password": os.getenv("DOCKER_PASSWORD"),
        "runtime_cpu": RUNTIME_CPU,
        "runtime_memory": RUNTIME_MEMORY,
        "max_workers": MAX_WORKERS
    },
    "aws": {
        "access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
        "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "region": os.getenv("AWS_REGION")
    }
}

def hello(name):
    return 'Hello {}!'.format(name)


RANDOM_JOB_NAME = str(uuid.uuid4())

# 1. EKS 노드 생성 요청 및 실행 대기
print("Requesting EKS nodes and waiting for them to be ready...")
# create_eks_nodes는 이제 성공한 인스턴스의 ID 목록 또는 실패 시 None을 반환한다고 가정합니다.
created_instance_ids_or_none = create_eks_nodes(target_instances, RANDOM_JOB_NAME)

# 성공적으로 생성되고 실행 상태가 된 인스턴스 ID만 필터링
running_instance_ids = []
if created_instance_ids_or_none:
    running_instance_ids = [inst_id for inst_id in created_instance_ids_or_none if inst_id is not None]

if not running_instance_ids:
    print("Failed to create or start any nodes. Exiting.")
    sys.exit(1) # 실패 시 종료

print(f"Successfully started instances: {running_instance_ids}")

# 3. 리톱스 작업 실행 (이미 running_instance_ids 목록이 준비됨)
# if not running_instance_ids: # 이 검사는 위에서 이미 수행됨
#     print("\nNo instances became ready. Cannot start Lithops job. Exiting.")
#     sys.exit(1)

# optional: 클러스터에 노드가 실제로 등록될 때까지 추가적인 대기 시간을 둘 수 있습니다.
print("\nGiving nodes a moment to register with the cluster...")
time.sleep(30) # 예: 30초 대기

print("\nStarting Lithops job...")
try:
    lithops_config["k8s"]["job_name"] = RANDOM_JOB_NAME
    fexec = lithops.ServerlessExecutor(config=lithops_config, log_level='DEBUG')

    fut = fexec.call_async(hello, 'World')
    result = fut.result()
    print(result)

    print("\nLithops job finished.")
    time.sleep(60)

finally:
    # 4. 생성된 인스턴스 종료 (try...finally 블록으로 이동하여 오류 발생 시에도 실행되도록 함)
    if running_instance_ids:
        print("\nDeleting spot instances...")
        for instance_id in running_instance_ids:
            try:
                delete_spot_instance_for_eks(instance_id, TARGET_REGION)
                print(f" Initiated termination for instance {instance_id}")
            except Exception as e:
                print(f" Error terminating instance {instance_id}: {e}")
    else:
        print("\nNo running instances to delete.")

print("\nScript finished.")