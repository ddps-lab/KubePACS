import yaml
import os
import time
import boto3
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
import datetime
import threading
import copy # YAML 객체 깊은 복사용

# 파일 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
YAML_DIR = os.path.join(BASE_DIR, "base_yaml")
NODECLASS_YAML_PATH = os.path.join(YAML_DIR, "nodeclass.yaml")
NODEPOOL_YAML_PATH = os.path.join(YAML_DIR, "nodepool.yaml")
JOB_YAML_PATH = os.path.join(YAML_DIR, "job.yaml")

# 실험 시나리오: (TARGET_PARALLELISM, pod_cpu_cores, pod_memory_gb)
SCENARIOS = [
    (10, 1, 1),
    (10, 1, 2),  # tiny
    (10, 2, 2),  # tiny cpu-intensive
    (10, 1, 4),  # tiny mem-intensive
    (50, 1, 2),  # small
    (50, 2, 2),  # small cpu-intensive
    (50, 1, 4),  # small mem-intensive
    (100, 1, 2), # medium
    (100, 2, 2), # medium cpu-intensive
    (100, 1, 4), # medium mem-intensive
    (400, 1, 2), # large
    (400, 2, 2), # large cpu-intensive
    (400, 1, 4), # large mem-intensive
    (1000, 1, 2),# huge
    (17, 7, 7), 
    (75, 3, 5),
    (1000, 2, 2),# huge cpu-intensive
    (287, 1, 6), 
    (439, 1, 9),
    (1000, 1, 4), # huge mem-intensive
    (115, 4, 2), 
    (1000, 1, 1),
]

# Kubeconfig 정보
KUBECONFIG_FILENAME = "kubeconfig.yaml"
KUBECONFIG_DIR = os.path.expanduser("~/.kube")
KUBECONFIG_PATH = os.path.join(KUBECONFIG_DIR, KUBECONFIG_FILENAME)
EKS_CLUSTER_NAME = "kubecaps-d2-k8s-cluster"
EKS_REGION = "us-west-2"
AWS_PROFILE_NAME = "default"

# 스레드 동기화를 위한 Lock 객체 (옵션, print문에 주로 사용)
print_lock = threading.Lock()

def locked_print(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)

def get_scenario_suffix(parallelism, cpu, mem_gb, thread_id=None):
    timestamp = datetime.datetime.now().strftime("%H%M%S%f") # 마이크로초까지 추가하여 동시 실행 시 이름 충돌 방지 강화
    if thread_id is not None:
        return f"t{thread_id}-p{parallelism}-c{cpu}-m{mem_gb}gb-{timestamp}"
    return f"p{parallelism}-c{cpu}-m{mem_gb}gb-{timestamp}"

def ensure_kubeconfig(): # 이 함수는 메인 스레드에서 한 번만 호출
    if os.path.exists(KUBECONFIG_PATH):
        locked_print(f"Kubeconfig 파일이 이미 존재합니다: {KUBECONFIG_PATH}")
        return True
    locked_print(f"Kubeconfig 파일 ({KUBECONFIG_PATH}) 이 존재하지 않아 새로 생성합니다.")
    try:
        session = boto3.Session(profile_name=AWS_PROFILE_NAME, region_name=EKS_REGION)
        eks_client = session.client("eks")
        cluster_info = eks_client.describe_cluster(name=EKS_CLUSTER_NAME)["cluster"]
        cluster_name_from_eks = cluster_info["name"]
        cluster_endpoint = cluster_info["endpoint"]
        cluster_ca_data = cluster_info["certificateAuthority"]["data"]
        account_id = session.client('sts').get_caller_identity()['Account']
        context_name = f"arn:aws:eks:{EKS_REGION}:{account_id}:cluster/{cluster_name_from_eks}"

        kubeconfig_content = {
            "apiVersion": "v1",
            "clusters": [{
                "name": context_name,
                "cluster": {
                    "server": cluster_endpoint,
                    "certificate-authority-data": cluster_ca_data,
                }
            }],
            "contexts": [{
                "name": context_name,
                "context": {
                    "cluster": context_name,
                    "user": context_name,
                }
            }],
            "current-context": context_name,
            "kind": "Config",
            "preferences": {},
            "users": [{
                "name": context_name,
                "user": {
                    "exec": {
                        "apiVersion": "client.authentication.k8s.io/v1beta1",
                        "command": "aws",
                        "args": ["--region", EKS_REGION, "eks", "get-token", "--cluster-name", cluster_name_from_eks],
                        "env": [{"name": "AWS_PROFILE", "value": AWS_PROFILE_NAME}] if AWS_PROFILE_NAME else None
                    }
                }
            }]
        }
        if AWS_PROFILE_NAME is None and kubeconfig_content['users'][0]['user']['exec'].get('env'):
            del kubeconfig_content['users'][0]['user']['exec']['env']

        os.makedirs(KUBECONFIG_DIR, exist_ok=True)
        with open(KUBECONFIG_PATH, "w") as f:
            yaml.dump(kubeconfig_content, f)
        locked_print(f"Kubeconfig 저장 완료: {KUBECONFIG_PATH}")
        return True
    except Exception as e:
        locked_print(f"Kubeconfig 생성 오류: {e}")
        return False

def delete_kubernetes_object(k8s_client_config, kind, name, api_version, namespace="default", wait_for_deletion=True, scenario_log_prefix=""):
    locked_print(f"{scenario_log_prefix}[삭제 시도] Kind: {kind}, Name: {name}")
    api_instance = None
    delete_method = None
    read_method = None 

    try:
        if kind == "Job" and api_version == "batch/v1":
            api_instance = client.BatchV1Api(client.ApiClient(k8s_client_config))
            delete_method = lambda: api_instance.delete_namespaced_job(name, namespace, propagation_policy="Foreground")
            read_method = lambda: api_instance.read_namespaced_job(name, namespace)
        elif kind == "NodePool" and api_version == "karpenter.sh/v1":
            api_instance = client.CustomObjectsApi(client.ApiClient(k8s_client_config))
            delete_method = lambda: api_instance.delete_cluster_custom_object("karpenter.sh", "v1", "nodepools", name, body=client.V1DeleteOptions())
            read_method = lambda: api_instance.get_cluster_custom_object("karpenter.sh", "v1", "nodepools", name)
        elif kind == "EC2NodeClass" and api_version == "karpenter.k8s.aws/v1":
            api_instance = client.CustomObjectsApi(client.ApiClient(k8s_client_config))
            delete_method = lambda: api_instance.delete_cluster_custom_object("karpenter.k8s.aws", "v1", "ec2nodeclasses", name, body=client.V1DeleteOptions())
            read_method = lambda: api_instance.get_cluster_custom_object("karpenter.k8s.aws", "v1", "ec2nodeclasses", name)
        else:
            locked_print(f"{scenario_log_prefix}지원되지 않는 리소스 종류 또는 API 버전 (삭제 건너뜀): Kind={kind}, APIVersion={api_version}")
            return False

        try:
            read_method() 
            locked_print(f"{scenario_log_prefix}{kind} '{name}'을(를) 삭제합니다...")
            delete_method()
            if wait_for_deletion:
                locked_print(f"{scenario_log_prefix}{kind} '{name}' 삭제 확인 중...")
                timeout = 180  
                start_time = time.time()
                while time.time() - start_time < timeout:
                    try:
                        read_method()
                        time.sleep(5) 
                    except ApiException as e_read:
                        if e_read.status == 404:
                            locked_print(f"{scenario_log_prefix}{kind} '{name}' 삭제 완료.")
                            return True
                        else:
                            raise 
                locked_print(f"{scenario_log_prefix}{kind} '{name}' 삭제 타임아웃.")
                return False 
            else:
                locked_print(f"{scenario_log_prefix}{kind} '{name}' 삭제 요청 전송됨 (대기 안 함).")
            return True
        except ApiException as e_initial_read:
            if e_initial_read.status == 404:
                locked_print(f"{scenario_log_prefix}{kind} '{name}'이(가) 이미 존재하지 않습니다. 삭제 건너뜁니다.")
                return True
            else:
                locked_print(f"{scenario_log_prefix}{kind} '{name}' 삭제 중 오류 (존재 확인 실패): {e_initial_read}")
                return False
    except Exception as e_main:
        locked_print(f"{scenario_log_prefix}{kind} '{name}' 삭제 처리 중 예외 발생: {e_main}")
        return False

def apply_kubernetes_object(k8s_client_config, k8s_object, always_recreate_if_exists=False, scenario_log_prefix=""):
    kind = k8s_object.get("kind")
    api_version = k8s_object.get("apiVersion")
    name = k8s_object.get("metadata", {}).get("name")
    namespace = k8s_object.get("metadata", {}).get("namespace", "default")
    locked_print(f"{scenario_log_prefix}[적용 시도] Kind: {kind}, Name: {name}")

    if always_recreate_if_exists:
        locked_print(f"{scenario_log_prefix}{kind} '{name}'을(를) 적용하기 전, 기존 리소스가 있다면 삭제합니다.")
        delete_kubernetes_object(k8s_client_config, kind, name, api_version, namespace, wait_for_deletion=True, scenario_log_prefix=scenario_log_prefix)
        locked_print(f"{scenario_log_prefix}{kind} '{name}' 삭제 후 5초 대기...")
        time.sleep(5)

    try:
        locked_print(f"{scenario_log_prefix}{kind} '{name}'을(를) 생성합니다...")
        if kind == "Job" and api_version == "batch/v1":
            api = client.BatchV1Api(client.ApiClient(k8s_client_config))
            api.create_namespaced_job(namespace, k8s_object)
        elif kind == "NodePool" and api_version == "karpenter.sh/v1":
            api = client.CustomObjectsApi(client.ApiClient(k8s_client_config))
            api.create_cluster_custom_object("karpenter.sh", "v1", "nodepools", k8s_object)
        elif kind == "EC2NodeClass" and api_version == "karpenter.k8s.aws/v1":
            api = client.CustomObjectsApi(client.ApiClient(k8s_client_config))
            api.create_cluster_custom_object("karpenter.k8s.aws", "v1", "ec2nodeclasses", k8s_object)
        else:
            locked_print(f"{scenario_log_prefix}지원되지 않는 리소스 종류 또는 API 버전입니다: Kind={kind}, APIVersion={api_version}")
            return False
        locked_print(f"{scenario_log_prefix}{kind} '{name}' 생성 요청 완료.")
        return True
    except ApiException as e_apply:
        if e_apply.status == 409 and not always_recreate_if_exists:
             locked_print(f"{scenario_log_prefix}{kind} '{name}' 생성 중 충돌 발생 (이미 존재함): {e_apply.reason}. 업데이트는 지원되지 않습니다.")
             return True 
        locked_print(f"{scenario_log_prefix}{kind} '{name}' 생성 중 Kubernetes API 오류: {e_apply}")
        return False
    except Exception as e_generic:
        locked_print(f"{scenario_log_prefix}{kind} '{name}' 생성 중 예외 발생: {e_generic}")
        return False

def wait_for_resource_ready(k8s_client_config, kind, name, api_version, namespace="default", timeout_seconds=180, scenario_log_prefix=""):
    locked_print(f"{scenario_log_prefix}[{kind} '{name}' 준비 상태 확인 중 (최대 {timeout_seconds}초)]")
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            if kind == "EC2NodeClass" and api_version == "karpenter.k8s.aws/v1":
                api = client.CustomObjectsApi(client.ApiClient(k8s_client_config))
                obj = api.get_cluster_custom_object("karpenter.k8s.aws", "v1", "ec2nodeclasses", name)
                if obj.get("status") and obj["status"].get("conditions"):
                    for cond in obj["status"]["conditions"]:
                        if cond.get("type") == "Ready" and cond.get("status") == "True":
                            locked_print(f"{scenario_log_prefix}{kind} '{name}' 준비 완료.")
                            return True
            elif kind == "NodePool" and api_version == "karpenter.sh/v1":
                api = client.CustomObjectsApi(client.ApiClient(k8s_client_config))
                obj = api.get_cluster_custom_object("karpenter.sh", "v1", "nodepools", name)
                if obj.get("status") and obj["status"].get("conditions"):
                    for cond in obj["status"]["conditions"]:
                        if cond.get("type") == "Ready" and cond.get("status") == "True":
                            locked_print(f"{scenario_log_prefix}{kind} '{name}' 준비 완료.")
                            return True
            else:
                locked_print(f"{scenario_log_prefix}{kind}의 준비 상태 확인 로직이 구현되지 않았습니다.")
                return True 
            
            locked_print(f"{scenario_log_prefix}{kind} '{name}' 아직 준비 안됨. 5초 후 재시도...")
        except ApiException as e:
            if e.status == 404:
                locked_print(f"{scenario_log_prefix}{kind} '{name}'을(를) 찾을 수 없습니다. 생성 실패 또는 삭제됨.")
                return False
            locked_print(f"{scenario_log_prefix}{kind} '{name}' 상태 확인 중 API 오류: {e.reason}. 5초 후 재시도...")
        except Exception as e_generic:
            locked_print(f"{scenario_log_prefix}{kind} '{name}' 상태 확인 중 예외: {e_generic}. 5초 후 재시도...")
        time.sleep(5)
    locked_print(f"{scenario_log_prefix}{kind} '{name}'이(가) {timeout_seconds}초 내에 준비되지 않았습니다 (타임아웃)." )
    return False

def run_scenario(scenario_params, scenario_index, total_scenarios, k8s_client_config_dict):
    target_parallelism, pod_cpu_cores, pod_memory_gb = scenario_params
    target_completions = target_parallelism
    thread_id = threading.get_ident()
    scenario_suffix = get_scenario_suffix(target_parallelism, pod_cpu_cores, pod_memory_gb, thread_id)
    log_prefix = f"[Scen-{scenario_index+1}/{total_scenarios} (TID:{thread_id}, Suff:{scenario_suffix})] "
    
    locked_print(f"{log_prefix}시작: Parallelism={target_parallelism}, CPU={pod_cpu_cores}, Mem={pod_memory_gb}GB")

    # 각 스레드에서 사용할 Kubernetes API 클라이언트 설정을 재생성 또는 로드
    # 여기서는 메인에서 로드한 설정을 복사하여 사용
    thread_specific_k8s_client_config = copy.deepcopy(k8s_client_config_dict) 

    current_nodeclass_name = f"nodeclass-{scenario_suffix}"
    current_nodepool_name = f"nodepool-{scenario_suffix}"
    current_job_name = f"job-{scenario_suffix}"
    scenario_specific_label_key = "kubecaps-scenario-instance"
    scenario_specific_label_value = scenario_suffix

    job_data_for_cleanup = None

    try:
        locked_print(f"{log_prefix}[단계 1/4] EC2NodeClass 적용: {current_nodeclass_name}")
        if not os.path.exists(NODECLASS_YAML_PATH):
            locked_print(f"{log_prefix}EC2NodeClass YAML 파일({NODECLASS_YAML_PATH}) 없음. 건너뜁니다.")
            return
        with open(NODECLASS_YAML_PATH, 'r') as f:
            nodeclass_yaml_data = yaml.safe_load(f)
        if not nodeclass_yaml_data:
            locked_print(f"{log_prefix}EC2NodeClass YAML ({NODECLASS_YAML_PATH}) 내용이 비어있습니다. 건너뜁니다.")
            return
        
        nodeclass_yaml_data["metadata"]["name"] = current_nodeclass_name
        if "tags" not in nodeclass_yaml_data["spec"]: nodeclass_yaml_data["spec"]["tags"] = {}
        nodeclass_yaml_data["spec"]["tags"]["kubecaps-scenario"] = scenario_suffix 
        nodeclass_yaml_data["spec"]["tags"]["kubecaps-parallelism"] = str(target_parallelism)
        nodeclass_yaml_data["spec"]["tags"]["kubecaps-cpu"] = str(pod_cpu_cores)
        nodeclass_yaml_data["spec"]["tags"]["kubecaps-memgb"] = str(pod_memory_gb)
        nodeclass_yaml_data["spec"]["tags"]["kubecaps-info"] = f"{target_parallelism}-{pod_cpu_cores}-{pod_memory_gb}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        nodeclass_yaml_data["spec"]["tags"][scenario_specific_label_key] = scenario_specific_label_value

        if not apply_kubernetes_object(thread_specific_k8s_client_config, nodeclass_yaml_data, always_recreate_if_exists=True, scenario_log_prefix=log_prefix):
            locked_print(f"{log_prefix}EC2NodeClass '{current_nodeclass_name}' 적용 실패. 중단합니다.")
            return
        if not wait_for_resource_ready(thread_specific_k8s_client_config, "EC2NodeClass", current_nodeclass_name, "karpenter.k8s.aws/v1", scenario_log_prefix=log_prefix):
            locked_print(f"{log_prefix}EC2NodeClass '{current_nodeclass_name}'이 준비되지 않아 중단합니다.")
            return

        locked_print(f"{log_prefix}[단계 2/4] NodePool 적용: {current_nodepool_name}")
        if not os.path.exists(NODEPOOL_YAML_PATH):
            locked_print(f"{log_prefix}NodePool YAML 파일({NODEPOOL_YAML_PATH}) 없음. 건너뜁니다.")
            return
        with open(NODEPOOL_YAML_PATH, 'r') as f:
            nodepool_yaml_data = yaml.safe_load(f)
        if not nodepool_yaml_data:
            locked_print(f"{log_prefix}NodePool YAML ({NODEPOOL_YAML_PATH}) 내용이 비어있습니다. 건너뜁니다.")
            return

        nodepool_yaml_data["metadata"]["name"] = current_nodepool_name
        if "spec" not in nodepool_yaml_data: nodepool_yaml_data["spec"] = {}
        if "template" not in nodepool_yaml_data["spec"]: nodepool_yaml_data["spec"]["template"] = {}
        if "metadata" not in nodepool_yaml_data["spec"]["template"]: nodepool_yaml_data["spec"]["template"]["metadata"] = {}
        if "labels" not in nodepool_yaml_data["spec"]["template"]["metadata"]: nodepool_yaml_data["spec"]["template"]["metadata"]["labels"] = {}
        nodepool_yaml_data["spec"]["template"]["metadata"]["labels"][scenario_specific_label_key] = scenario_specific_label_value
        
        if "spec" in nodepool_yaml_data["spec"]["template"] and "nodeClassRef" in nodepool_yaml_data["spec"]["template"]["spec"]:
            nodepool_yaml_data["spec"]["template"]["spec"]["nodeClassRef"]["name"] = current_nodeclass_name
        else:
            locked_print(f"{log_prefix}NodePool YAML 구조에 nodeClassRef 설정 경로가 올바르지 않습니다. 확인 필요.")
            return
        
        if not apply_kubernetes_object(thread_specific_k8s_client_config, nodepool_yaml_data, always_recreate_if_exists=True, scenario_log_prefix=log_prefix):
            locked_print(f"{log_prefix}NodePool '{current_nodepool_name}' 적용 실패. 중단합니다.")
            return
        if not wait_for_resource_ready(thread_specific_k8s_client_config, "NodePool", current_nodepool_name, "karpenter.sh/v1", scenario_log_prefix=log_prefix):
            locked_print(f"{log_prefix}NodePool '{current_nodepool_name}'이 준비되지 않아 중단합니다.")
            return
        locked_print(f"{log_prefix}NodePool '{current_nodepool_name}' 적용 완료. 노드 준비를 위해 10초 대기...")
        time.sleep(10) 

        locked_print(f"{log_prefix}[단계 3/4] Job 적용: {current_job_name}")
        if not os.path.exists(JOB_YAML_PATH):
            locked_print(f"{log_prefix}Job YAML 파일({JOB_YAML_PATH}) 없음. 건너뜁니다.")
            return
        with open(JOB_YAML_PATH, 'r') as f:
            job_data_for_cleanup = job_data = yaml.safe_load(f)
        if not job_data:
            locked_print(f"{log_prefix}Job YAML ({JOB_YAML_PATH}) 내용이 비어있습니다. 건너뜁니다.")
            return
        
        job_data["metadata"]["name"] = current_job_name
        job_data["spec"]["parallelism"] = target_parallelism
        job_data["spec"]["completions"] = target_completions

        if "template" in job_data["spec"] and "spec" in job_data["spec"]["template"] and \
           job_data["spec"]["template"]["spec"].get("containers"):
            container_resources = {
                "requests": {"cpu": f"{pod_cpu_cores * 1000}m", "memory": f"{pod_memory_gb}Gi"},
                "limits": {"cpu": f"{pod_cpu_cores * 1000}m", "memory": f"{pod_memory_gb}Gi"}
            }
            job_data["spec"]["template"]["spec"]["containers"][0]["resources"] = container_resources
        else:
            locked_print(f"{log_prefix}Job YAML: 컨테이너 리소스 경로 오류.")
            return

        affinity = job_data["spec"]["template"]["spec"].get("affinity", {})
        node_affinity = affinity.get("nodeAffinity", {})
        required_scheduling = node_affinity.get("requiredDuringSchedulingIgnoredDuringExecution", {})
        node_selector_terms = required_scheduling.get("nodeSelectorTerms", [{"matchExpressions": []}])
        if not node_selector_terms or not node_selector_terms[0].get("matchExpressions"): 
            node_selector_terms = [{"matchExpressions": []}]
        node_selector_terms[0]["matchExpressions"].append({
            "key": scenario_specific_label_key,
            "operator": "In",
            "values": [scenario_specific_label_value]
        })
        required_scheduling["nodeSelectorTerms"] = node_selector_terms
        node_affinity["requiredDuringSchedulingIgnoredDuringExecution"] = required_scheduling
        affinity["nodeAffinity"] = node_affinity
        job_data["spec"]["template"]["spec"]["affinity"] = affinity
        
        if not apply_kubernetes_object(thread_specific_k8s_client_config, job_data, always_recreate_if_exists=True, scenario_log_prefix=log_prefix):
             locked_print(f"{log_prefix}Job '{current_job_name}' 적용 실패. 중단합니다.")
             return

        locked_print(f"{log_prefix}Job '{current_job_name}' 완료까지 대기 중...")
        batch_v1 = client.BatchV1Api(client.ApiClient(thread_specific_k8s_client_config))
        job_completed_successfully = False
        timeout_seconds = 600 
        start_time = time.time()
        job_namespace_from_yaml = job_data.get("metadata", {}).get("namespace", "default")
        job_status = None

        while time.time() - start_time < timeout_seconds:
            try:
                job_status_obj = batch_v1.read_namespaced_job_status(current_job_name, job_namespace_from_yaml)
                job_status = job_status_obj.status 
                if job_status.succeeded is not None and job_status.succeeded >= target_completions:
                    locked_print(f"{log_prefix}Job '{current_job_name}' 완료.")
                    job_completed_successfully = True
                    break
                if job_status.failed is not None and job_status.failed > 0:
                    locked_print(f"{log_prefix}Job '{current_job_name}' 실패. (실패 Pod 수: {job_status.failed})")
                    break
                active_pods = job_status.active if job_status.active is not None else 0
                succeeded_pods = job_status.succeeded if job_status.succeeded is not None else 0
                failed_pods = job_status.failed if job_status.failed is not None else 0                    
                locked_print(f"{log_prefix}Job '{current_job_name}' 진행 중... (Active: {active_pods}, Succeeded: {succeeded_pods}, Failed: {failed_pods})")
            except ApiException as e:
                if e.status == 404:
                    locked_print(f"{log_prefix}Job '{current_job_name}'을(를) 찾을 수 없습니다. 생성 실패 또는 이미 삭제됨.")
                    break 
                else:
                    locked_print(f"{log_prefix}Job 상태 확인 중 API 오류: {e.reason}")
                    time.sleep(10) 
                    continue
            time.sleep(10) 
        
        if not job_completed_successfully and (job_status is None or not (job_status.failed is not None and job_status.failed > 0)):
             if job_status:
                 locked_print(f"{log_prefix}Job '{current_job_name}'이(가) {timeout_seconds}초 내에 완료되지 않았습니다. (Active: {job_status.active}, Succeeded: {job_status.succeeded}, Failed: {job_status.failed}) - 타임아웃")
             else:
                 locked_print(f"{log_prefix}Job '{current_job_name}'이(가) {timeout_seconds}초 내에 완료되지 않았습니다. (상태 확인 불가) - 타임아웃")
    finally:
        locked_print(f"{log_prefix}[단계 4/4 - 리소스 정리] 시작")
        job_namespace_to_delete = "default"
        if job_data_for_cleanup:
             job_namespace_to_delete = job_data_for_cleanup.get("metadata", {}).get("namespace", "default")
        delete_kubernetes_object(thread_specific_k8s_client_config, "Job", current_job_name, "batch/v1", job_namespace_to_delete, wait_for_deletion=False, scenario_log_prefix=log_prefix)
        delete_kubernetes_object(thread_specific_k8s_client_config, "NodePool", current_nodepool_name, "karpenter.sh/v1", wait_for_deletion=True, scenario_log_prefix=log_prefix)
        locked_print(f"{log_prefix}NodePool 삭제 완료. 노드 실제 정리를 위해 10초 대기..." ) 
        time.sleep(10)
        delete_kubernetes_object(thread_specific_k8s_client_config, "EC2NodeClass", current_nodeclass_name, "karpenter.k8s.aws/v1", wait_for_deletion=True, scenario_log_prefix=log_prefix)
        locked_print(f"{log_prefix}리소스 정리 완료.")

def main():
    locked_print("[초기화] Kubeconfig 설정 확인")
    if not ensure_kubeconfig():
        return
    
    # 메인 스레드에서 Kubeconfig를 로드하고, 이 설정(딕셔너리 형태)을 각 스레드에 전달합니다.
    # config.load_kube_config()는 전역적으로 설정하므로, 각 스레드가 client.Configuration()을 어떻게 다룰지 고려해야 합니다.
    # 가장 안전한 방법은 각 스레드가 API 클라이언트를 만들 때 config를 새로 로드하거나, config 객체를 깊은 복사하여 사용하는 것입니다.
    # 여기서는 config.load_kube_config()로 로드된 기본 설정을 각 스레드가 client.ApiClient(copy.deepcopy(client.Configuration.get_default_copy())) 와 같이 사용하도록 유도합니다.
    config.load_kube_config(config_file=KUBECONFIG_PATH) 
    default_k8s_config = copy.deepcopy(client.Configuration.get_default_copy()) # 스레드에 전달할 설정 복사본
    locked_print("Kubernetes 클라이언트 주 설정 완료.")

    threads = []
    max_parallel_scenarios = 4
    scenario_batches = [SCENARIOS[i:i + max_parallel_scenarios] for i in range(0, len(SCENARIOS), max_parallel_scenarios)]

    total_scenario_count = len(SCENARIOS)
    completed_scenarios = 0

    for batch_index, scenario_batch in enumerate(scenario_batches):
        locked_print(f"\n--- 시나리오 배치 {batch_index + 1}/{len(scenario_batches)} 시작 ---")
        batch_threads = []
        for scenario_in_batch_index, scenario_params in enumerate(scenario_batch):
            # 전체 시나리오 중 현재 인덱스 계산
            current_overall_scenario_index = batch_index * max_parallel_scenarios + scenario_in_batch_index
            # 스레드 생성 및 시작
            # 각 스레드에 고유한 Kubernetes 클라이언트 설정을 전달해야 합니다.
            thread = threading.Thread(target=run_scenario, args=(scenario_params, current_overall_scenario_index, total_scenario_count, default_k8s_config))
            batch_threads.append(thread)
            thread.start()
        
        # 현재 배치의 모든 스레드가 완료될 때까지 대기
        for thread in batch_threads:
            thread.join()
        
        completed_scenarios += len(scenario_batch)
        locked_print(f"--- 시나리오 배치 {batch_index + 1}/{len(scenario_batches)} 완료 ({completed_scenarios}/{total_scenario_count} 시나리오 처리) ---")

    locked_print("\n모든 시나리오 실행 완료.")

if __name__ == "__main__":
    main()