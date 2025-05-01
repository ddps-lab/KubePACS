import boto3
import base64
import json
from botocore.exceptions import ClientError
import time
import os
import dotenv

dotenv.load_dotenv()

session = boto3.Session(profile_name=os.getenv("AWS_PROFILE"))
ec2 = session.resource('ec2')

def create_node_role(
    region: str,
    cluster_name: str,
):
    eks_client = session.client('eks', region_name=region)
    iam_client = session.client('iam')
    role_name = f"eks-{cluster_name}-node-role"
    instance_profile_name = f"eks-{cluster_name}-node-profile"
    role_arn = None
    instance_profile_arn = None
    role_exists = False
    profile_exists = False

    # --- Check if Role exists ---
    try:
        get_role_response = iam_client.get_role(RoleName=role_name)
        role_arn = get_role_response['Role']['Arn']
        print(f"IAM Role '{role_name}' already exists with ARN: {role_arn}")
        role_exists = True
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
            print(f"IAM Role '{role_name}' does not exist. Creating...")
            role_exists = False
        else:
            print(f"Error checking for role {role_name}: {e}")
            return None

    # --- Create Role if it doesn't exist ---
    if not role_exists:
        try:
            assume_role_policy = json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "ec2.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            })
            tags = [
                {'Key': "Name", 'Value': role_name},
                {'Key': "Cluster", 'Value': cluster_name}
            ]
            create_role_response = iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=assume_role_policy,
                Description=f"Role for EKS {cluster_name} nodes",
                Tags=tags
            )
            role_arn = create_role_response['Role']['Arn']
            print(f"Successfully created role '{role_name}' with ARN: {role_arn}")

            # Attach policies (Consider adding waits or checking for attachment success)
            print("Attaching required policies...")
            policies_to_attach = [
                "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
                "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
                "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
                "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
            ]
            for policy_arn in policies_to_attach:
                try:
                    iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)
                    print(f" Attached policy: {policy_arn}")
                except ClientError as attach_error:
                    print(f"Warning: Failed to attach policy {policy_arn} to role {role_name}: {attach_error}")

        except ClientError as e:
            print(f"Error creating role {role_name}: {e}")
            return None

    # --- Check if Instance Profile exists ---
    try:
        get_profile_response = iam_client.get_instance_profile(InstanceProfileName=instance_profile_name)
        instance_profile_arn = get_profile_response['InstanceProfile']['Arn']
        # Check if the correct role is associated
        associated_roles = get_profile_response['InstanceProfile'].get('Roles', [])
        role_is_associated = any(r['RoleName'] == role_name for r in associated_roles)
        print(f"Instance Profile '{instance_profile_name}' already exists with ARN: {instance_profile_arn}")
        if not role_is_associated and role_arn:
            print(f" Role '{role_name}' is not associated with profile '{instance_profile_name}'. Associating...")
            try:
                 iam_client.add_role_to_instance_profile(InstanceProfileName=instance_profile_name, RoleName=role_name)
                 print(" Role associated successfully.")
            except ClientError as e:
                 print(f"ERROR: Failed to add role '{role_name}' to profile '{instance_profile_name}': {e}")
                 return None
        elif not role_arn:
             print("Warning: Role doesn't exist, cannot associate with instance profile.")

        profile_exists = True

    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
            print(f"Instance Profile '{instance_profile_name}' does not exist. Creating...")
            profile_exists = False
        else:
            print(f"Error checking for instance profile {instance_profile_name}: {e}")
            return None

    # --- Create Instance Profile if it doesn't exist and associate role ---
    if not profile_exists:
        if not role_arn:
             print("ERROR: Role ARN is not available, cannot create instance profile.")
             return None
        try:
            create_profile_response = iam_client.create_instance_profile(InstanceProfileName=instance_profile_name)
            instance_profile_arn = create_profile_response['InstanceProfile']['Arn']
            print(f"Successfully created instance profile '{instance_profile_name}' with ARN: {instance_profile_arn}")

            print(f"Associating role '{role_name}' with instance profile '{instance_profile_name}'...")
            # Might need a short wait before adding role after profile creation
            time.sleep(5)
            iam_client.add_role_to_instance_profile(InstanceProfileName=instance_profile_name, RoleName=role_name)
            print("Role associated successfully.")

        except ClientError as e:
            print(f"Error creating instance profile or adding role: {e}")
            return None

    # --- EKS Access Entry ---
    print(f"Attempting to manage EKS access entry for role {role_name}...")
    try:
        eks_client.create_access_entry(
            clusterName=cluster_name,
            principalArn=role_arn,
            type="EC2_LINUX",
        )
        print(f"Successfully created or verified EKS access entry for role {role_name}.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            print(f"EKS access entry for role {role_name} already exists.")
        else:
            # Re-raise the exception if it's not the one we expect to handle
            print(f"Error managing EKS access entry for role {role_name}: {e}")
            # Depending on desired behavior, you might want to return None or raise e
            # For now, let's print the error and continue, assuming role/profile creation succeeded.
            pass # Or raise e

    if role_arn and instance_profile_arn:
         print("IAM Role and Instance Profile are ready.")
         return {"RoleArn": role_arn, "InstanceProfileArn": instance_profile_arn}
    else:
         print("Failed to prepare IAM Role or Instance Profile.")
         return None

def delete_spot_request_for_eks(
    spot_request_id: str,
    region: str,
):
    ec2_client = session.client('ec2', region_name=region)
    ec2_client.cancel_spot_instance_requests(SpotInstanceRequestIds=[spot_request_id])  
    print(f"Spot Request {spot_request_id} cancelled.")

def delete_ec2_instance_for_eks(
    instance_id: str,
    region: str,
):
    ec2_client = session.client('ec2', region_name=region)
    ec2_client.terminate_instances(InstanceIds=[instance_id])  
    print(f"Instance {instance_id} terminated.")

def create_ondemand_instance_for_eks(
    instance_type: str,
    region: str,
    availability_zone: str,
    num_instances: int,
    cluster_name: str,
    cluster_dns_ip: str,
    ami_id: str,
    subnet_id: str,
    security_group_ids: list[str],
    iam_instance_profile_arn: str,
    custom_node_labels: dict[str, str] | None = None,
    tags: dict[str, str] | None = None
):
    """
    Creates an on-demand EC2 instance for an EKS cluster.

    Args:
        instance_type: The type of instance to create.  
        region: The AWS region to create the instance in.
        availability_zone: The availability zone to create the instance in.
        num_instances: The number of instances to create.
        cluster_name: The name of the EKS cluster.
        cluster_dns_ip: The IP address of the EKS cluster's API server. 
        ami_id: The AMI ID to use for the instance.
        subnet_id: The subnet ID to use for the instance.
        security_group_ids: The security group IDs to use for the instance.
        iam_instance_profile_arn: The IAM instance profile ARN to use for the instance.
        custom_node_labels: The custom node labels to use for the instance.
        tags: The tags to use for the instance. 

    Returns:
        The EC2 instance ID if successful, otherwise None.
    """
    print(f"Requesting on-demand EC2 instance type {instance_type} in {availability_zone} ({region}) for EKS cluster {cluster_name}")
    ec2_client = session.client('ec2', region_name=region)  
    eks_client = session.client('eks', region_name=region)

    # --- Get EKS Cluster Details ---
    try:
        print(f"Fetching details for EKS cluster: {cluster_name} in region {region}...")
        cluster_info = eks_client.describe_cluster(name=cluster_name)
        cluster_data = cluster_info['cluster']
        api_server_endpoint = cluster_data['endpoint']
        cluster_ca_base64 = cluster_data['certificateAuthority']['data']
        print(f"Successfully fetched EKS cluster details.")
    except Exception as e:
        print(f"ERROR: Failed to fetch details for EKS cluster '{cluster_name}' in region '{region}'.") 
        print(f" Error details: {e}")
        print(" Please ensure the cluster name and region are correct and you have permissions.")
        return None

    # --- Bottlerocket TOML User Data ---
    settings = {
        "settings": {
            "kubernetes": {
                "api-server": api_server_endpoint,
                "cluster-certificate": cluster_ca_base64,
                "cluster-name": cluster_name,
                "cluster-dns-ip": cluster_dns_ip,
            },
        }
    }
    node_labels = {}
    if custom_node_labels:
        node_labels.update(custom_node_labels)
    settings["settings"]["kubernetes"]["node-labels"] = node_labels
    user_data_lines = ["[settings]", "[settings.kubernetes]"]
    for key, value in settings["settings"]["kubernetes"].items():
        if key == "node-labels":
            user_data_lines.append("\n[settings.kubernetes.node-labels]")
            for lk, lv in value.items():
                escaped_lk = lk.replace('"', '\\"')
                escaped_lv = lv.replace('"', '\\"')
                user_data_lines.append(f'"{escaped_lk}" = "{escaped_lv}"')
        elif isinstance(value, str):
             escaped_value = value.replace('"', '\\"')
             user_data_lines.append(f'{key} = "{escaped_value}"')
        elif isinstance(value, int):
             user_data_lines.append(f"{key} = {value}")

    user_data_toml = "\n".join(user_data_lines)
    print("\n--- Generated UserData (TOML): ---")       
    print(user_data_toml)
    print("------------------------------------\n")
    
    # --- Launch Specification ---
    launch_specification = {    
        'ImageId': ami_id,
        'InstanceType': instance_type,
        'SecurityGroupIds': security_group_ids,
        'IamInstanceProfile': {
            'Arn': iam_instance_profile_arn
        },  
        'UserData': user_data_toml,
        'Placement': {
            'AvailabilityZone': availability_zone,
        },
        'SubnetId': subnet_id,
        'BlockDeviceMappings': [
            {
                'DeviceName': '/dev/xvda',
                'Ebs': {
                    'VolumeSize': 32,
                    
                }
            }           
        ],
    }   

    # --- Step 1: Request On-Demand Instances ---
    try:
        request_args = {
            'MinCount': num_instances,
            'MaxCount': num_instances,
            **launch_specification,
            'TagSpecifications': [
                {
                    'ResourceType': 'instance',
                    'Tags': [{'Key': k, 'Value': v} for k, v in tags.items()] if tags else []
                }
            ]
        }
        response = ec2_client.run_instances(**request_args)
        instance_ids = [i['InstanceId'] for i in response['Instances']]
        print(f"Successfully requested {num_instances} on-demand instances: {instance_ids}")
        return instance_ids
    except Exception as e:
        print(f"ERROR: Failed to request on-demand instances: {e}")
        return None

def get_instance_id_from_on_demand_request(
    instance_ids: list[str],
    region: str,
    retry_interval_seconds: int = 1,
    timeout_seconds: int = 300
) -> list[str] | None:
    """
    Retrieves the EC2 instance IDs associated with a given on-demand request,
    polling until all instances are running or reaches a timeout.

    Args:
        instance_ids: The list of instance IDs to monitor.
        region: The AWS region where the instances are located.
        retry_interval_seconds: The number of seconds to wait between checks.
        timeout_seconds: The maximum number of seconds to wait for all instances to be running.     
    Returns:
        The list of instance IDs if all instances are running within the timeout, otherwise None.
    """
    ec2_client = session.client('ec2', region_name=region)
    start_time = time.time()

    while True: 
        elapsed_time = time.time() - start_time
        if elapsed_time > timeout_seconds:
            print(f"ERROR: Timeout ({timeout_seconds}s) waiting for on-demand instances to be running.")
            return None

        try:        
            response = ec2_client.describe_instances(InstanceIds=instance_ids)
            instances = response['Reservations'][0]['Instances']

            running_instances = [i['InstanceId'] for i in instances if i['State']['Name'] == 'running']
            pending_instances = [i['InstanceId'] for i in instances if i['State']['Name'] == 'pending'] 
            failed_instances = [i['InstanceId'] for i in instances if i['State']['Name'] == 'failed']           

            if running_instances:
                print(f"Successfully started {len(running_instances)} instances: {running_instances}")
                return running_instances
            elif pending_instances: 
                print(f"Waiting for {len(pending_instances)} pending instances to start...")
            elif failed_instances:
                print(f"ERROR: Failed to start {len(failed_instances)} instances: {failed_instances}")
                return None

        except ClientError as e:            
            print(f"Error describing instances: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return None
        
        time.sleep(retry_interval_seconds)

def create_spot_instance_for_eks(
    instance_type: str,
    region: str,
    availability_zone: str,
    num_instances: int,
    cluster_name: str,
    cluster_dns_ip: str,
    ami_id: str,
    subnet_id: str,
    security_group_ids: list[str],
    iam_instance_profile_arn: str,
    custom_node_labels: dict[str, str] | None = None,
    tags: dict[str, str] | None = None
):
    """
    Requests a Bottlerocket Spot Instance, waits for it to run, tags it (if specified),
    and returns the instance ID.

    1. Requests a Spot Instance configured to join an EKS cluster.
    2. Polls AWS until the Spot request is fulfilled and an instance ID is available.
    3. Waits for the EC2 instance to reach the 'running' state.
    4. Applies specified EC2 tags to the running instance.

    Returns:
        The EC2 instance ID if successful, otherwise None.
    """
    print(f"Requesting Bottlerocket Spot instance type {instance_type} in {availability_zone} ({region}) for EKS cluster {cluster_name}")
    ec2_client = session.client('ec2', region_name=region)
    eks_client = session.client('eks', region_name=region)

    # --- Get EKS Cluster Details ---
    try:
        print(f"Fetching details for EKS cluster: {cluster_name} in region {region}...")
        cluster_info = eks_client.describe_cluster(name=cluster_name)
        cluster_data = cluster_info['cluster']
        api_server_endpoint = cluster_data['endpoint']
        cluster_ca_base64 = cluster_data['certificateAuthority']['data']
        print(f"Successfully fetched EKS cluster details.")
    except Exception as e:
        print(f"ERROR: Failed to fetch details for EKS cluster '{cluster_name}' in region '{region}'.")
        print(f" Error details: {e}")
        print(" Please ensure the cluster name and region are correct and you have permissions.")
        return None

    # --- Bottlerocket TOML User Data ---
    settings = {
        "settings": {
            "kubernetes": {
                "api-server": api_server_endpoint,
                "cluster-certificate": cluster_ca_base64,
                "cluster-name": cluster_name,
                "cluster-dns-ip": cluster_dns_ip,
            },
        }
    }
    node_labels = {}
    if custom_node_labels:
        node_labels.update(custom_node_labels)
    settings["settings"]["kubernetes"]["node-labels"] = node_labels
    user_data_lines = ["[settings]", "[settings.kubernetes]"]
    for key, value in settings["settings"]["kubernetes"].items():
        if key == "node-labels":
            user_data_lines.append("\n[settings.kubernetes.node-labels]")
            for lk, lv in value.items():
                escaped_lk = lk.replace('"', '\\"')
                escaped_lv = lv.replace('"', '\\"')
                user_data_lines.append(f'"{escaped_lk}" = "{escaped_lv}"')
        elif isinstance(value, str):
             escaped_value = value.replace('"', '\\"')
             user_data_lines.append(f'{key} = "{escaped_value}"')
        elif isinstance(value, int):
             user_data_lines.append(f"{key} = {value}")

    user_data_toml = "\n".join(user_data_lines)
    print("\n--- Generated UserData (TOML): ---")
    print(user_data_toml)
    print("------------------------------------\n")
    encoded_user_data = base64.b64encode(user_data_toml.encode('utf-8')).decode('utf-8')

    # --- Launch Specification ---
    launch_specification = {
        'ImageId': ami_id,
        'InstanceType': instance_type,
        'SecurityGroupIds': security_group_ids,
        'IamInstanceProfile': {
            'Arn': iam_instance_profile_arn
        },
        'UserData': encoded_user_data,
        'Placement': {
            'AvailabilityZone': availability_zone,
        },
        'SubnetId': subnet_id,
        'BlockDeviceMappings': [
            {
                'DeviceName': '/dev/xvda',
                'Ebs': {
                    'VolumeSize': 32,
                    'VolumeType': 'gp3',
                    'DeleteOnTermination': True
                },
            },
        ],
    }

    # --- Step 1: Spot Instance Request (No Tags) ---
    spot_request_id = None
    try:
        request_args = {
            'InstanceCount': num_instances,
            'LaunchSpecification': launch_specification,
            'Type': 'one-time',
            'TagSpecifications': [
                {
                    'ResourceType': 'spot-instances-request',
                    'Tags': [{'Key': k, 'Value': v} for k, v in tags.items()] if tags else []
                }
            ]
        }
        response = ec2_client.request_spot_instances(**request_args)
        spot_request_id = response['SpotInstanceRequests'][0]['SpotInstanceRequestId']
        print(f"Successfully submitted Spot Instance request: {spot_request_id}")

    except Exception as e:
        print(f"ERROR: Failed requesting Spot Instance in {availability_zone}: {e}")
        return None

    # --- Step 2: Get Instance ID from Spot Request ---
    instance_id = get_instance_id_from_spot_request(
        spot_request_id=spot_request_id,
        region=region
        # Consider making timeouts configurable if needed
    )

    if not instance_id:
        print(f"ERROR: Failed to get Instance ID for Spot Request {spot_request_id}. Cleaning up Spot Request.")
        try:
            delete_spot_request_for_eks(spot_request_id, region)
        except Exception as cleanup_e:
            print(f"Warning: Failed to clean up spot request {spot_request_id}: {cleanup_e}")
        return None

    print(f"Obtained Instance ID: {instance_id} for Spot Request {spot_request_id}")

    # --- Step 3: Wait for Instance to be Running ---
    if not wait_for_instance_running(instance_id=instance_id, region=region):
        print(f"ERROR: Instance {instance_id} did not reach 'running' state. Manual cleanup might be required.")
        # Depending on requirements, you might want to terminate the instance here
        # try:
        #     delete_ec2_instance_for_eks(instance_id, region)
        # except Exception as term_e:
        #     print(f"Warning: Failed to terminate instance {instance_id} after run timeout: {term_e}")
        return None

    # --- Return Instance ID ---
    print(f"Instance {instance_id} is running.")
    return instance_id

def get_instance_id_from_spot_request(
    spot_request_id: str,
    region: str,
    retry_interval_seconds: int = 1, # How often to check the status (Changed default to 1)
    timeout_seconds: int = 300      # Max time to wait for fulfillment
) -> str | None:
    """
    Retrieves the EC2 instance ID associated with a given Spot Instance Request ID,
    polling until the request is fulfilled or reaches a terminal state.

    Args:
        spot_request_id: The ID of the Spot Instance Request (e.g., 'sir-abcdef12').
        region: The AWS region where the Spot request was made.
        retry_interval_seconds: The number of seconds to wait between checks.
        timeout_seconds: The maximum number of seconds to wait for fulfillment.

    Returns:
        The EC2 instance ID if the request is fulfilled, otherwise None.
    """
    print(f"Polling for Instance ID for Spot Request: {spot_request_id} in region {region}...")
    ec2_client = session.client('ec2', region_name=region)
    start_time = time.time()

    while True:
        # Check for timeout
        if time.time() - start_time > timeout_seconds:
            print(f"ERROR: Timeout ({timeout_seconds}s) waiting for Spot Request {spot_request_id} to be fulfilled.")
            return None

        try:
            response = ec2_client.describe_spot_instance_requests(
                SpotInstanceRequestIds=[spot_request_id]
            )

            if not response or not response.get('SpotInstanceRequests'):
                print(f"Warning: No information found for Spot Request ID: {spot_request_id}. Retrying...")
                time.sleep(retry_interval_seconds)
                continue

            request_info = response['SpotInstanceRequests'][0]
            state = request_info.get('State')
            status_code = request_info.get('Status', {}).get('Code')
            status_message = request_info.get('Status', {}).get('Message', 'N/A')

            print(f" Current State: {state}, Status Code: {status_code}, Message: {status_message}")

            # Check if the request is active and has an instance ID
            if state == 'active':
                instance_id = request_info.get('InstanceId')
                if instance_id:
                    print(f"Spot Request fulfilled. Found Instance ID: {instance_id}")
                    return instance_id
                else:
                    # Should ideally not happen if state is active, but wait just in case
                    print(f"Spot Request is active, but InstanceId is not yet available. Waiting...")
            elif state in ['open', 'pending-fulfillment']:
                 print(f"Spot Request is not yet fulfilled (state: {state}). Waiting...")
            elif state in ['failed', 'cancelled', 'closed']:
                print(f"ERROR: Spot Request {spot_request_id} entered terminal state: {state}. Status: {status_message}")
                return None
            else: # Unknown state?
                print(f"Warning: Encountered unexpected Spot Request state: {state}. Retrying...")

        except ClientError as e:
            # Handle throttling or other transient errors if necessary
            print(f"Error describing spot instance request {spot_request_id}: {e}. Retrying...")
        except Exception as e:
            print(f"An unexpected error occurred: {e}. Retrying...")

        # Wait before the next check
        time.sleep(retry_interval_seconds)

def wait_for_instance_running(
    instance_id: str,
    region: str,
    timeout_seconds: int = 300,
    poll_interval_seconds: int = 10
) -> bool:
    """
    Waits for a specific EC2 instance to reach the 'running' state.

    Args:
        instance_id: The ID of the EC2 instance to monitor.
        region: The AWS region where the instance is located.
        timeout_seconds: Maximum time to wait in seconds.
        poll_interval_seconds: How often to check the instance status in seconds.

    Returns:
        True if the instance reached the 'running' state within the timeout, False otherwise.
    """
    ec2_client = session.client('ec2', region_name=region)
    print(f"Waiting for instance {instance_id} to reach 'running' state (timeout: {timeout_seconds}s)...")
    start_time = time.time()

    while True:
        elapsed_time = time.time() - start_time
        if elapsed_time > timeout_seconds:
            print(f"Timeout: Instance {instance_id} did not reach 'running' state within {timeout_seconds} seconds.")
            return False

        try:
            response = ec2_client.describe_instances(InstanceIds=[instance_id])
            if not response['Reservations']:
                # Instance might not be fully registered yet, continue waiting
                print(f" Instance {instance_id} not found in describe_instances response yet, retrying...")

            else:
                 instance_state = response['Reservations'][0]['Instances'][0]['State']['Name']
                 print(f" Current state of instance {instance_id}: {instance_state}")
                 if instance_state == 'running':
                     print(f"Instance {instance_id} is now running.")
                     return True
                 elif instance_state in ['shutting-down', 'terminated', 'stopping', 'stopped']:
                     print(f"Error: Instance {instance_id} entered terminal state: {instance_state}")
                     return False
                 # Otherwise, keep polling (pending, etc.)

        except ClientError as e:
            # Handle potential errors like 'InvalidInstanceID.NotFound' if checked too early
            # or other API errors
            print(f"Warning: Error checking instance {instance_id} status: {e}. Retrying...")
        except Exception as e:
             print(f"An unexpected error occurred while checking instance {instance_id}: {e}")
             return False # Or retry depending on desired robustness

        time.sleep(poll_interval_seconds)

