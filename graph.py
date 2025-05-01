import uuid
import lithops
import time
import sys
import os
import lithops
import networkx as nx
import pickle
import community.community_louvain as community_louvain
from dotenv import load_dotenv

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
FILE_PATH = get_aws_spot_prices(target_region='us-east-1', allow_arm=False)
RUNTIME_CPU = 4
RUNTIME_MEMORY = 8
MAX_WORKERS = 40

# 생성할 노드 정의
target_instances = getGoldenNodepool(FILE_PATH, MAX_WORKERS, RUNTIME_CPU, RUNTIME_MEMORY, verbose=False)["nodepool_config"]
print(target_instances)
target_instances = [
    {
        "instance_type": "c3.2xlarge",
        "availability_zone": "us-east-1a",
        "num_instances": 20
    }
]

DOCKER_USER = os.getenv("DOCKER_USER")
DOCKER_PASSWORD = os.getenv("DOCKER_PASSWORD")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
KUBECFG_PATH = os.getenv("KUBECFG_PATH")

#lithops 설정
lithops_config = {
    "lithops": {
        "backend": "k8s",
        "storage": "aws_s3"
    },
    "k8s": {
        "kubecfg_path": KUBECFG_PATH,
        "docker_user": DOCKER_USER,
        "docker_password": DOCKER_PASSWORD,
        "runtime_cpu": RUNTIME_CPU,
        "runtime_memory": RUNTIME_MEMORY * 1024,
        "max_workers": MAX_WORKERS,
        "runtime_timeout": 3600,
        "master_timeout": 3600
    },
    "aws": {
        "access_key_id": AWS_ACCESS_KEY_ID,
        "secret_access_key": AWS_SECRET_ACCESS_KEY,
        "region": AWS_REGION
    }
}

print(lithops_config)

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

print("\nStarting Lithops job...")
try:
    BUCKET = "kubecaps-dev-lithops-bucket"
    NUM_FUNCTIONS = 4
    NODES = 1000 #5000
    EDGE_PROB = 0.05 # 0.5
    N_DIJKSTRA = 20 #150

    lithops_config["k8s"]["job_name"] = RANDOM_JOB_NAME
    fexec = lithops.ServerlessExecutor(config=lithops_config, log_level='DEBUG')
    storage = lithops.Storage(config=lithops_config)

    get_graph_name = lambda x: x.key.split("/")[-1]

    def gen_graphs(n):
        storage.create_bucket(BUCKET)
        try:
            last_index = int(storage.list_objects(BUCKET, "graphs/")[-1]["Key"][-1]) + 1
        except (IndexError, KeyError):
            last_index = 0
        graphs = []
        for i in range(last_index, n):
            G = nx.erdos_renyi_graph(NODES, EDGE_PROB)
            graphs.append(G)
        for i, graph in enumerate(graphs):
            storage.put_object(BUCKET, "graphs/graph{}".format(i), pickle.dumps(graph))


    def compute_pagerank(obj):
        storage = lithops.Storage()
        graph = pickle.loads(obj.data_stream.read())
        paqerank = nx.pagerank(graph, alpha=0.99)
        storage.put_object(BUCKET, "pagerank/" + get_graph_name(obj), pickle.dumps(paqerank))


    def community_detection(obj):
        storage = lithops.Storage()
        graph = pickle.loads(obj.data_stream.read())
        communities = community_louvain.best_partition(graph)
        storage.put_object(BUCKET, "communities/" + get_graph_name(obj), pickle.dumps(communities))


    def first_n_dijkstra(obj):
        storage = lithops.Storage()
        graph = pickle.loads(obj.data_stream.read())
        pagerank = pickle.loads(storage.get_object(BUCKET, "pagerank/" + get_graph_name(obj)))
        important_nodes = sorted(pagerank, key=pagerank.get, reverse=True)[:N_DIJKSTRA]
        shortest_paths = {}
        for i in important_nodes:
            shortest_paths[i] = nx.single_source_dijkstra_path(graph, i)
        storage.put_object(BUCKET, "dijkstra/" + get_graph_name(obj), pickle.dumps(shortest_paths))

    gen_graphs(NUM_FUNCTIONS)

    fexec.map(community_detection, BUCKET + "/graphs/")
    fexec.map(compute_pagerank, BUCKET + "/graphs/").get_result()
    fexec.map(first_n_dijkstra, BUCKET + "/graphs/")
    fexec.wait()
    fexec.dump_stats_to_csv(f"{RANDOM_JOB_NAME}.csv")

    print("\nLithops job finished.")
finally:
    # 4. 생성된 인스턴스 종료 (try...finally 블록으로 이동하여 오류 발생 시에도 실행되도록 함)
    if running_instance_ids:
        print("\nDeleting spot instances...")
        for instance_id in running_instance_ids:
            try:
                delete_ec2_instance_for_eks(instance_id, TARGET_REGION)
                print(f" Initiated termination for instance {instance_id}")
            except Exception as e:
                print(f" Error terminating instance {instance_id}: {e}")
    else:
        print("\nNo running instances to delete.")

print("\nScript finished.")