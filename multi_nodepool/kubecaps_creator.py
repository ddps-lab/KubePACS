import dotenv, os
from kubecaps_scaler import create_node_role, create_ondemand_instance_for_eks, create_spot_instance_for_eks
from kubecaps_util import get_bottlerocket_ami_id, get_eks_vpc_id, get_security_groups_for_vpc, get_subnets_by_az_for_vpc, get_kube_dns_ip

dotenv.load_dotenv()

# --- EKS Cluster Specific ---
TARGET_AWS_ACCOUNT = os.getenv("TARGET_AWS_ACCOUNT")
TARGET_CLUSTER = os.getenv("TARGET_CLUSTER")
TARGET_REGION = os.getenv("TARGET_REGION")
TARGET_CLUSTER_DNS = get_kube_dns_ip("~/.kube/config")

# --- Instance Configuration ---
TARGET_AMI_ID = get_bottlerocket_ami_id(TARGET_REGION, "t3.medium") # bottlerocket ami(us-east-1)
TARGET_VPC_ID = get_eks_vpc_id(TARGET_CLUSTER, TARGET_REGION)
TARGET_SUBNET_IDS = get_subnets_by_az_for_vpc(TARGET_VPC_ID, TARGET_REGION)
TARGET_SG_IDS = get_security_groups_for_vpc(TARGET_VPC_ID, TARGET_REGION)
TARGET_IAM_PROFILE_ARN = f"arn:aws:iam::{TARGET_AWS_ACCOUNT}:instance-profile/eks-{TARGET_CLUSTER}-node-profile"

def create_eks_nodes(target_instances: list[dict], job_name: str):
    """
    주어진 사양에 따라 EKS 클러스터에 노드를 생성합니다.

    Args:
        target_instances (list): 각 인스턴스 유형, 가용 영역, 개수를 포함하는 딕셔너리 리스트.
                                예: [{"instance_type": "t3.medium", "availability_zone": "us-east-1a", "num_instances": 1}]
        job_name (str): 작업 이름.

    Returns:
        list: 생성된 스팟 요청 ID 리스트. 실패 시 빈 리스트 반환.
    """
    instance_ids = []

    # Ensure the node role exists (idempotent operation)

    create_node_role(region=TARGET_REGION, cluster_name=TARGET_CLUSTER)

    ondemand_instance_id = create_ondemand_instance_for_eks(
        instance_type="t3.medium",
        region=TARGET_REGION,
        availability_zone="us-east-1a",
        num_instances=1,
        cluster_name=TARGET_CLUSTER,
        cluster_dns_ip=TARGET_CLUSTER_DNS,
        ami_id=TARGET_AMI_ID,
        subnet_id=TARGET_SUBNET_IDS["us-east-1a"][0],
        security_group_ids=TARGET_SG_IDS,
        iam_instance_profile_arn=TARGET_IAM_PROFILE_ARN,
        custom_node_labels={"lithops/jobname": job_name, "lithops/nodetype": "ondemand"},
        tags={"lithops/jobname": job_name, "lithops/nodetype": "ondemand", "Name": f"{TARGET_CLUSTER}-master-{job_name}"}
    )
    
    instance_ids.extend(ondemand_instance_id)

    for instance in target_instances:
        try:
            subnet_id_list = TARGET_SUBNET_IDS.get(instance["availability_zone"])
            if not subnet_id_list:
                print(f"Warning: No subnets found for Availability Zone {instance['availability_zone']}. Skipping instance creation.")
                continue
            subnet_id = subnet_id_list[0] # Use the first available subnet in the AZ

            spot_instance_id = create_spot_instance_for_eks(
                            instance_type=instance["instance_type"],
                            region=instance["availability_zone"][:-1],
                            availability_zone=instance["availability_zone"],
                            num_instances=instance["num_instances"],
                            cluster_name=TARGET_CLUSTER,
                            cluster_dns_ip=TARGET_CLUSTER_DNS,
                            ami_id=get_bottlerocket_ami_id(instance["availability_zone"][:-1], instance["instance_type"]),
                            subnet_id=subnet_id,
                            security_group_ids=TARGET_SG_IDS,
                            iam_instance_profile_arn=TARGET_IAM_PROFILE_ARN,
                            custom_node_labels={"lithops/jobname": job_name, "lithops/nodetype": "spot"},
                            tags={"lithops/jobname": job_name, "lithops/nodetype": "spot", "Name": f"{TARGET_CLUSTER}-worker-{job_name}"}
                        )

            if spot_instance_id:
                print(f"Spot request {spot_instance_id} created for {instance['instance_type']} in {instance['availability_zone']}.")
                instance_ids.extend(spot_instance_id)
            else:
                print(f"Failed to create Spot request for {instance['instance_type']} in {instance['availability_zone']}.")
        except Exception as e:
            print(f"Error creating instance for {instance}: {e}")

    return instance_ids

if __name__ == "__main__":
    # Example usage when run directly
    target_instances_example = [
        {
            "instance_type": "t3.medium",
            "availability_zone": "us-east-1a",
            "num_instances": 1
        }
    ]
    created_spot_requests = create_eks_nodes(target_instances_example, "job2")
    if created_spot_requests:
        print("Successfully created the following spot requests:")
        for req_id in created_spot_requests:
            print(f"- {req_id}")
        print(f"Monitor their status in the AWS console. Once fulfilled, the instances should automatically join the {TARGET_CLUSTER} cluster.")
    else:
        print("No spot requests were successfully created.")