from datetime import datetime, timezone
import hashlib
import uuid
import lithops
import json
import sys
import os
import lithops
import networkx as nx
import pickle
import community.community_louvain as community_louvain
from dotenv import load_dotenv

from multi_nodepool.kubecaps_util import get_karpenter_instance_ids

load_dotenv()

sys.path.append(os.path.expanduser('~/Desktop/KubeCaps/multi_nodepool'))
from multi_nodepool.kubecaps_creator import create_eks_nodes, TARGET_REGION
from multi_nodepool.kubecaps_scaler import delete_ec2_instance_for_eks
from multi_nodepool.kubecaps_selector import get_aws_spot_prices, getGoldenNodepool

# --- 설정 ---
SPOT_REQUEST_TIMEOUT = 600 # 스팟 요청이 처리되고 인스턴스 ID를 얻기까지 기다리는 최대 시간 (초)
INSTANCE_RUNNING_TIMEOUT = 600 # 인스턴스가 running 상태가 될 때까지 기다리는 최대 시간 (초)
INSTANCE_POLL_INTERVAL = 15 # 인스턴스 상태 확인 간격 (초)

# 생성 POD 사양 정의
FILE_PATH = get_aws_spot_prices(target_region='us-east-1', allow_arm=True)
RUNTIME_CPU = 1
RUNTIME_MEMORY = 8
TOTAL_WORKERS = 30

# 생성할 노드 정의
golden_nodepool = []
# target_instances = golden_nodepool["nodepool_config"]

# print(target_instances)


DOCKER_USER = os.getenv("DOCKER_USER")
DOCKER_PASSWORD = os.getenv("DOCKER_PASSWORD")
DOCKER_IMAGE = os.getenv("DOCKER_IMAGE")

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
KUBECFG_PATH = os.getenv("KUBECFG_PATH")

#lithops 설정
lithops_config = {
    "lithops": {
        "backend": "ddps_eks",
        "storage": "aws_s3",
        "execution_timeout": 3600
    },
    "ddps_eks": {
        "kubecfg_path": KUBECFG_PATH,
        "docker_user": DOCKER_USER,
        "docker_password": DOCKER_PASSWORD,
        "runtime": DOCKER_IMAGE,
        "runtime_cpu": RUNTIME_CPU,
        "runtime_memory": RUNTIME_MEMORY * 1024,
        "max_workers": TOTAL_WORKERS,
        "runtime_timeout": 3600,
        "master_timeout": 3600,
        "execution_timeout": 3600,
        "is_karpenter": True,
        "worker_processes": 1
    },
    "aws": {
        "access_key_id": AWS_ACCESS_KEY_ID,
        "secret_access_key": AWS_SECRET_ACCESS_KEY,
        "region": AWS_REGION
    }
}

# 랜덤 작업 이름 생성   
RANDOM_JOB_NAME = str(uuid.uuid4())

# 랜덤 작업 이름 폴더 생성
os.makedirs(f"results/{RANDOM_JOB_NAME}")

# Karpenter 사용 시 노드 생성 요청 및 실행 대기 생략
if not lithops_config["ddps_eks"]["is_karpenter"]:
    golden_nodepool_filename = f"results/{RANDOM_JOB_NAME}/golden_nodepool.json"
    with open(golden_nodepool_filename, 'w', encoding='utf-8') as f:
        json.dump(golden_nodepool, f, ensure_ascii=False, indent=4)
    print(f"성공적으로 '{golden_nodepool_filename}' 파일에 golden_nodepool 데이터를 저장했습니다.")

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

print("\nStarting Lithops job...")
try:
    START_TIME = datetime.now(timezone.utc)
    BUCKET = "kubecaps-dev-lithops-bucket"
    NUM_FUNCTIONS = int(TOTAL_WORKERS / 3)
    NODES = 1000 #5000
    EDGE_PROB = 0.05 # 0.5
    N_DIJKSTRA = 20 #150

    lithops_config["ddps_eks"]["job_name"] = RANDOM_JOB_NAME
    fexec = lithops.ServerlessExecutor(config=lithops_config, log_level='DEBUG')
    
    get_graph_name = lambda x: x.key.split("/")[-1]

    def gen_graphs(n):
        base_seed = "ddpslab"
        storage = lithops.Storage(config=lithops_config)
        storage.create_bucket(BUCKET)
        try:
            last_index = int(storage.list_objects(BUCKET, f"{RANDOM_JOB_NAME}/graphs/")[-1]["Key"][-1]) + 1
        except (IndexError, KeyError):
            last_index = 0
        graphs = []
        for i in range(last_index, n):
            key = base_seed + str(i)
            h = hashlib.sha256(key.encode()).hexdigest()
            seed = int(h[:8], 16)
            G = nx.erdos_renyi_graph(NODES, EDGE_PROB, seed=seed)
            graphs.append(G)
        for i, graph in enumerate(graphs):
            storage.put_object(BUCKET, f"{RANDOM_JOB_NAME}/graphs/graph{i}", pickle.dumps(graph))


    def compute_pagerank(obj):
        storage = lithops.Storage(config=lithops_config)
        graph = pickle.loads(obj.data_stream.read())
        paqerank = nx.pagerank(graph, alpha=0.99)
        storage.put_object(BUCKET, f"{RANDOM_JOB_NAME}/pagerank/" + get_graph_name(obj), pickle.dumps(paqerank))


    def community_detection(obj):
        storage = lithops.Storage(config=lithops_config)
        graph = pickle.loads(obj.data_stream.read())
        communities = community_louvain.best_partition(graph)
        storage.put_object(BUCKET, f"{RANDOM_JOB_NAME}/communities/" + get_graph_name(obj), pickle.dumps(communities))


    def first_n_dijkstra(obj):
        storage = lithops.Storage(config=lithops_config)
        graph = pickle.loads(obj.data_stream.read())
        pagerank = pickle.loads(storage.get_object(BUCKET, f"{RANDOM_JOB_NAME}/pagerank/" + get_graph_name(obj)))
        important_nodes = sorted(pagerank, key=pagerank.get, reverse=True)[:N_DIJKSTRA]
        shortest_paths = {}
        for i in important_nodes:
            shortest_paths[i] = nx.single_source_dijkstra_path(graph, i)
        storage.put_object(BUCKET, f"{RANDOM_JOB_NAME}/dijkstra/" + get_graph_name(obj), pickle.dumps(shortest_paths))

    gen_graphs(NUM_FUNCTIONS)

    fexec.map(community_detection, BUCKET + f"/{RANDOM_JOB_NAME}/graphs/", timeout=3600)
    fexec.map(compute_pagerank, BUCKET + f"/{RANDOM_JOB_NAME}/graphs/", timeout=3600).get_result()
    fexec.map(first_n_dijkstra, BUCKET + f"/{RANDOM_JOB_NAME}/graphs/", timeout=3600)
    fexec.wait(timeout=3600)
    fexec.dump_stats_to_csv(f"results/{RANDOM_JOB_NAME}")

    END_TIME = datetime.now(timezone.utc)
    print("\nLithops job finished.")
finally:
    # 4. 생성된 인스턴스 종료
    instance_ids_filename = f"results/{RANDOM_JOB_NAME}/instance_ids.json"
    instance_ids = []
    
    if 'END_TIME' not in locals() and 'END_TIME' not in globals():
        print("\nLithops job did not finish successfully, END_TIME is not set.")
        END_TIME =  datetime.now(timezone.utc)

    if lithops_config["ddps_eks"]["is_karpenter"]:
        if START_TIME and END_TIME: # START_TIME도 확인
            instance_ids = get_karpenter_instance_ids(KUBECFG_PATH, START_TIME, END_TIME)
            print("\nKarpenter is used. Fetched instance IDs between START_TIME and END_TIME.")
        else:
            print("\nKarpenter is used, but START_TIME or END_TIME is not set. Skipping fetching instance IDs.")
        print("\nKarpenter is used. No spot instances to delete directly by this script.")
    elif not lithops_config["ddps_eks"]["is_karpenter"] and running_instance_ids:
        instance_ids = running_instance_ids
        print("\nDeleting spot instances...")
        for instance_id in running_instance_ids:
            try:
                delete_ec2_instance_for_eks(instance_id, TARGET_REGION)
                print(f" Initiated termination for instance {instance_id}")
            except Exception as e:
                print(f" Error terminating instance {instance_id}: {e}")
    else:
        print("\nNo running instances to delete.")

    with open(instance_ids_filename, 'w', encoding='utf-8') as f:
        json.dump(instance_ids, f, ensure_ascii=False, indent=4)
print("\nScript finished.")