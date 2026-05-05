from collections import defaultdict
import numpy as np
import os
import json
import pandas as pd
from datetime import datetime

from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.termination import get_termination

from pymoo.optimize import minimize
from pymoo.core.problem import Problem

import matplotlib.pyplot as plt

# Define a custom problem for deployment optimization
class DeploymentProblem(Problem):
    def __init__(self, cost_func, node_sufficient, workload, instances, r):
        super().__init__(n_var=len(instances),
                         n_obj=2,
                         n_constr=0,
                         elementwise_evaluation=True)

        self.r = r
        self.instances = instances
        self.xl = np.zeros(len(self.instances))
        self.xu = np.ones(len(self.instances)) * self.r
        self.cost_func = cost_func
        self.node_sufficient = node_sufficient
        self.workload = workload
        
    def _initialize(self):
        num_nodes = len(self.instances)
        self.x = np.full(num_nodes, 0)
        
    def _evaluate(self, x, out, *args, **kwargs):
    # Initialize variables for total cost and total instances
        total_cost = np.zeros(len(x))
        total_instances = np.zeros(len(x))

        for i in range(len(x)):
            nodes = []
            for j in range(len(x[i])):
                node_type = list(self.instances.keys())[j]
                num_nodes = int(round(x[i][j]))
                total_instances[i] += num_nodes
                nodes += [node_type] * num_nodes
            total_cost[i] = self.cost_func(self.instances, nodes)
            
            suff, ratio = self.node_sufficient(self.workload, nodes, self.instances)
            if not suff:
                total_cost[i],  total_instances[i] =  1e9, -1e9
            if suff and 1 < ratio:
                total_cost[i] = total_cost[i] * ratio
                total_instances[i] = int(total_instances[i] / ratio)
    
        # Set the objectives (minimize cost, maximize number of instances)
        out["F"] = np.column_stack((total_cost, -total_instances))


def node_sufficient(workload, node_combination, instances):
    output = False
    total_pods = sum(service['pods'] for service in workload.values())
    total_memory_pods = sum(service['memory'] for service in workload.values())
    total_cpu_pods = sum(service['cpu'] for service in workload.values())
    total_memory_nodes = 0
    total_cpu_nodes = 0
    
    for node in node_combination:
        total_memory_nodes += instances[node]['memory']
        total_cpu_nodes += instances[node]['cpu']
    # total_cpu_nodes -= round(cpu_usage_of_pods_in_other_ns*0.001, 2)  
    memory_ratio = round(total_memory_nodes / total_memory_pods, 2)
    cpu_ratio = round(total_cpu_nodes / total_cpu_pods, 2)

    max_pod_cpu = total_cpu_pods // total_pods
    max_pod_memory = total_memory_pods // total_pods
    
    if (1 <= memory_ratio and 1 <= cpu_ratio ):
        remaining_pods = total_pods
        for i, node in enumerate(node_combination):
            node_mem = instances[node]['memory']
            node_cpu = instances[node]['cpu']
            pod_mem =  node_mem // max_pod_memory
            pod_cpu = node_cpu // max_pod_cpu
            remaining_pods -= min(pod_mem, pod_cpu)
            
            if (remaining_pods <= 0):
                output = True
                break
    
    return output, max(memory_ratio, cpu_ratio)

def plot_pareto(optimal_f):
    # Extract the cost and number of instances from the objectives
    total_cost = optimal_f[:, 0]
    total_instances = -optimal_f[:, 1]

    # Plot the Pareto optimal solutions
    plt.scatter(total_instances, total_cost)
    plt.ylabel('Total Cost') # minimize
    plt.xlabel('Number of Instances') # maximize
    plt.title('Pareto Optimal Solutions')
    plt.grid(True)
    plt.show()
    
def display_optimal_solution(optimal_x, optimal_f, instances):
    for i in range(len(optimal_x)):
        node_combination = []
        for j in range(len(optimal_x[i])):
            if int(round(optimal_x[i][j])) >= 1:
                node_type = list(instances.keys())[j]
                num_nodes = int(round(optimal_x[i][j]))
                node_combination.extend([node_type] * num_nodes)
        cost = optimal_f[i][0]  # Extract the cost from the objective values

        print("Node Combination:", node_combination)
        print("Total Cost:", cost)

def choose_node_combination(optimal_x, optimal_f, instances, i):
    node_combination = []
    for j in range(len(optimal_x[i])):
        if int(round(optimal_x[i][j])) >= 1:
            node_type = list(instances.keys())[j]
            num_nodes = int(round(optimal_x[i][j]))
            node_combination.extend([node_type] * num_nodes)
    cost = optimal_f[i][0]
    # print(f'Optimal node comb @ {i}', node_combination)
    # print(f'Optimal Cost @ {i}: ', cost)
    return node_combination

def sort_nodes(optimal_x, optimal_f):
    sorted_indices = np.argsort(optimal_f[:, 0])  # Sort based on the first objective (cost)
    sorted_optimal_f = optimal_f[sorted_indices]
    sorted_optimal_x = optimal_x[sorted_indices]
    return sorted_optimal_x, sorted_optimal_f

def calculateResources(flag, services_dict):
    pods_workload = defaultdict(dict)
    
    for service_name, service_info in services_dict.items():
        cpu_per_pod = service_info.get('cpu_per_pod', 0)
        memory_per_pod = service_info.get('memory_per_pod', 0)
        num_pods = service_info.get('num_pods', 0)
        
        pods_workload[service_name]['pods'] = num_pods
        pods_workload[service_name]['memory'] = round(num_pods * memory_per_pod, 2)
        pods_workload[service_name]['cpu'] = round(num_pods * cpu_per_pod, 2)
        
    return pods_workload

def optimize(instances, flag, costFunc, services, verbose=False):
    workload = calculateResources(flag, services)
    # print("workload: ", workload)
    if (len(workload) == 0):
        return []
    total_pods = sum(service['pods'] for service in workload.values())
    print("total_pods: ", total_pods)
    r = max(4, total_pods // len(instances.keys()))
    pop_size = 100
    n_gen = 100

    problem = DeploymentProblem(cost_func = costFunc, node_sufficient = node_sufficient, workload = workload, instances = instances, r= r)

    # Define the algorithm and perform optimization
    algorithm = NSGA2(pop_size=pop_size)
    termination = get_termination("n_gen", n_gen)
    
    # pymoo 내부 병렬 처리 비활성화를 위해 n_threads=1 설정
    res = minimize(problem,
                algorithm,
                termination,
                verbose=verbose,
                seed=96)

    # Get the optimal solutions and objectives
    optimal_x = res.X
    optimal_f = res.F
    
    optimal_x, optimal_f = sort_nodes(optimal_x, optimal_f)
    i = len(optimal_x) // 2
    node_comb = choose_node_combination(optimal_x, optimal_f, instances, i)
    return node_comb
   
def public_cost(instances, nodes):    
    cost = 0
    if (nodes):
        cost = sum(instances[node]['cost'] for node in nodes)
    return cost

def gen_spotConfig(filepath):
    df_filtered = pd.read_csv(filepath)
    current_time = datetime.now()
    json_data = {}
    for _, row in df_filtered.iterrows():
        instance_type = row['InstanceType'] + "/" + row['AZ']
        json_data[instance_type] = {
            "cpu": int(row['vCPU']),
            "memory": int(row['Memory']),
            "date": current_time.strftime('%Y-%m-%d'),
            "cost": float(row['SpotPrice']),
            "T3": float(row['T3']),
            "CoreMark": float(row['CoreMark'])
        }
    # json_filename = f"spotConfig.json"
    # with open(json_filename, 'w') as f:
    #     json.dump(json_data, f, indent=4)
    return json_data

def getSpotKubepool(filepath, pod_count, pod_cpu, pod_mem, verbose=False):
    # config_dir = os.path.dirname(os.path.abspath(__file__))
    # spot_config_path = os.path.join(config_dir, 'spotConfig.json')
    instances_config = gen_spotConfig(filepath)

    print("--- Running Public Cloud Test ---")
    public_results = optimal_nodes = []

    services_input = {f"service_{i}": {"cpu_per_pod": pod_cpu, "memory_per_pod": pod_mem, "num_pods": 1} for i in range(pod_count)}

    optimal_nodes = optimize(
        instances=instances_config.copy(), # 원본 수정을 방지하기 위해 복사본 전달
        flag=False,
        costFunc=public_cost,
        services=services_input,
        verbose=verbose
    )
    node_counts = {}
    for node in optimal_nodes:
        node_counts[node] = node_counts.get(node, 0) + 1
    print("최적화된 노드 구성:")
    print(node_counts)
    total_cpu_usage, total_memory_usage = 0, 0
    for node_type, count in node_counts.items():
        total_cpu_usage += instances_config[node_type]["cpu"] * count
        total_memory_usage += instances_config[node_type]["memory"] * count

    # print("요구 Pod 수: ", pod_count)
    # print("요구 총 CPU: ", pod_cpu * pod_count)
    # print("요구 총 메모리: ", pod_mem * pod_count)
    # print("생성 조합 CPU: ", total_cpu_usage)
    # print("생성 조합 메모리: ", total_memory_usage)    

    return gen_summary(filepath, pod_count, pod_cpu, pod_mem, node_counts)

def gen_summary(filepath, pod_count, pod_cpu, pod_mem, optimal_nodes):
    target_instances = []
    total_cost = 0
    total_assignable_pods = 0
    total_performance = 0
    total_efficiency = 0

    info_df = pd.read_csv(filepath)

    for node, count in optimal_nodes.items():
        instance_type = node.split("/")[0]
        az = node.split("/")[1]

        info = info_df[(info_df['InstanceType'] == instance_type) & (info_df['AZ'] == az)]

        target_instances.append({
            "instance_type": instance_type,
            "availability_zone": az,
            "num_instances": count,
            "T3": info['T3'].values[0],
            "CoreMark": info['CoreMark'].values[0]
        })

        assignable_pods = min(info['vCPU'].values[0] // pod_cpu, info['Memory'].values[0] // pod_mem)

        total_cost += info['SpotPrice'].values[0] * count
        total_assignable_pods += assignable_pods * count

        performance = info['CoreMark'].values[0] * assignable_pods
        total_performance += performance
        
    total_efficiency += total_performance / (total_assignable_pods * total_cost)

    return {
        'pods': pod_count,
        'cpu': pod_cpu,
        'mem': pod_mem,
        'cost': total_cost,
        'performance': total_performance,
        'perf_per_cost': total_performance / total_cost,
        'actual_pods': total_assignable_pods,
        'excess_pods': total_assignable_pods - pod_count,
        'nodepool_config': target_instances
    }
        

if __name__ == "__main__":
    result = getSpotKubepool(filepath="/Users/taeyoon/Desktop/middleware2025/cmp/figure5/spotdata/msa/050103.csv", pod_count=1, pod_cpu=1, pod_mem=1)
    print(result)