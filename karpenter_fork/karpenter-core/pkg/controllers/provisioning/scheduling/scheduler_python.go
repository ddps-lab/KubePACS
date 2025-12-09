package scheduling

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"

	corev1 "k8s.io/api/core/v1"
	"sigs.k8s.io/controller-runtime/pkg/log"

	v1 "sigs.k8s.io/karpenter/pkg/apis/v1"
	"sigs.k8s.io/karpenter/pkg/cloudprovider"
	"sigs.k8s.io/karpenter/pkg/scheduling"
	"sigs.k8s.io/karpenter/pkg/utils/resources"
)
type PythonSolverResult struct {
	InstanceType     string `json:"instance_type"`
	AvailabilityZone string `json:"availability_zone"`
	NumInstances     int    `json:"num_instances"`
}

func (s *Scheduler) solvePython(ctx context.Context, pods []*corev1.Pod) (Results, error) {
	if len(pods) == 0 {
		return Results{}, nil
	}

	// 1. Calculate Pod Requirements (Average)
	var totalCPU, totalMem float64
	for _, p := range pods {
		req := s.cachedPodData[p.UID].Requests
		totalCPU += float64(req.Cpu().MilliValue()) / 1000.0
		totalMem += float64(req.Memory().Value()) / (1024 * 1024 * 1024) // GiB
	}
	avgCPU := totalCPU / float64(len(pods))
	avgMem := totalMem / float64(len(pods))

	if avgCPU == 0 { avgCPU = 0.1 } // Minimum safety
	if avgMem == 0 { avgMem = 0.1 }

	// 2. Prepare Allowed Instances List
	type AllowedInstance struct {
		InstanceType     string `json:"instance_type"`
		AvailabilityZone string `json:"availability_zone"`
	}
	var allowedInstances []AllowedInstance

	for _, nct := range s.nodeClaimTemplates {
		// Only consider templates with the kubepacs strategy
		if val, ok := nct.Annotations["kubepacs.io/strategy"]; !ok || val != "kubepacs" {
			continue
		}
		for _, it := range nct.InstanceTypeOptions {
			for _, offering := range it.Offerings {
				if offering.Available && offering.CapacityType() == v1.CapacityTypeSpot {
					allowedInstances = append(allowedInstances, AllowedInstance{
						InstanceType:     it.Name,
						AvailabilityZone: offering.Zone(),
					})
				}
			}
	}
	}
	
	allowedJson, err := json.Marshal(allowedInstances)
	if err != nil {
		return Results{}, fmt.Errorf("failed to marshal allowed instances: %v", err)
	}
	log.FromContext(ctx).Info(fmt.Sprintf("Allowed instances count: %d", len(allowedInstances)))

	// 3. Get AWS Region
	region := os.Getenv("AWS_REGION")
	if region == "" {
		region = os.Getenv("AWS_DEFAULT_REGION")
	}
	if region == "" {
		region = "us-east-1" // fallback default
	}
	log.FromContext(ctx).Info("Using AWS region for Python solver", "region", region)

	// 4. Call Python Script
	cmd := exec.Command("python3", "-u", "/usr/local/bin/kubepacs_cli.py",
		"--pod-count", fmt.Sprintf("%d", len(pods)),
		"--pod-cpu", fmt.Sprintf("%f", avgCPU),
		"--pod-mem", fmt.Sprintf("%f", avgMem),
		"--region", region,
		"--allowed-instances-file", "-", // Use stdin
	)
	cmd.Dir = "/tmp"
	
	// Pass JSON via Stdin
	cmd.Stdin = bytes.NewReader(allowedJson)

	var out bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &stderr

	log.FromContext(ctx).Info("Calling Python solver", "args", cmd.Args)
	if err := cmd.Run(); err != nil {
		return Results{}, fmt.Errorf("python script execution failed: %v, stderr: %s", err, stderr.String())
	}

	// 5. Parse Output
	if stderr.Len() > 0 {
		log.FromContext(ctx).Info("Python solver stderr", "stderr", stderr.String())
	}
	log.FromContext(ctx).Info("Python solver output", "output", out.String())

	var pythonResults []PythonSolverResult
	if err := json.Unmarshal(out.Bytes(), &pythonResults); err != nil {
		return Results{}, fmt.Errorf("failed to parse python output: %v, output: %s", err, out.String())
	}

	// 6. Create NodeClaims
	var newNodeClaims []*NodeClaim
	podIndex := 0

	for _, res := range pythonResults {
		for i := 0; i < res.NumInstances; i++ {
			// Find a matching NodeClaimTemplate and InstanceType
			var chosenTemplate *NodeClaimTemplate
			var chosenIT *cloudprovider.InstanceType

			// Find template that supports this instance type
			for _, nct := range s.nodeClaimTemplates {
				// Only consider templates with the kubepacs strategy
				if val, ok := nct.Annotations["kubepacs.io/strategy"]; !ok || val != "kubepacs" {
					continue
				}

				for _, it := range nct.InstanceTypeOptions {
					if it.Name == res.InstanceType {
						chosenTemplate = nct
						chosenIT = it
						break
					}
				}
				if chosenTemplate != nil {
					break
				}
			}

			if chosenTemplate == nil {
				log.FromContext(ctx).Error(nil, "Instance type from python solver not found in templates", "instanceType", res.InstanceType)
				continue
			}

			// Create NodeClaim
			nc := NewNodeClaim(
				chosenTemplate,
				s.topology,
				s.daemonOverhead[chosenTemplate],
				s.daemonHostPortUsage[chosenTemplate],
				[]*cloudprovider.InstanceType{chosenIT},
				s.reservationManager,
				s.reservedOfferingMode,
			)

			// Set Zone Requirement
			nc.Requirements.Add(scheduling.NewRequirement(corev1.LabelTopologyZone, corev1.NodeSelectorOpIn, res.AvailabilityZone))
			nc.Requirements.Add(scheduling.NewRequirement(v1.CapacityTypeLabelKey, corev1.NodeSelectorOpIn, v1.CapacityTypeSpot))

			// Assign Pods (Greedy)
			// We need to check capacity, but the python script already did that.
			// We just fill it up.
			
			// Calculate capacity for this node
			podRequest := s.cachedPodData[pods[0].UID].Requests // Use first pod as representative
			nodeCapacity := chosenIT.Capacity
			maxPodsCPU := nodeCapacity.Cpu().MilliValue() / podRequest.Cpu().MilliValue()
			maxPodsMem := nodeCapacity.Memory().Value() / podRequest.Memory().Value()
			capacity := int(maxPodsCPU)
			if int(maxPodsMem) < capacity {
				capacity = int(maxPodsMem)
			}

			podsForNode := []*corev1.Pod{}
			for j := 0; j < capacity && podIndex < len(pods); j++ {
				podsForNode = append(podsForNode, pods[podIndex])
				podIndex++
			}

			for _, p := range podsForNode {
				r, its, ofs, err := nc.CanAdd(ctx, p, s.cachedPodData[p.UID], false)
				if err == nil {
					nc.Add(p, s.cachedPodData[p.UID], r, its, ofs)
				} else {
					log.FromContext(ctx).Error(err, "Failed to add pod to python-selected node")
				}
			}

			if len(nc.Pods) > 0 {
				newNodeClaims = append(newNodeClaims, nc)
				s.remainingResources[nc.NodePoolName] = resources.Subtract(s.remainingResources[nc.NodePoolName], chosenIT.Capacity)
			}
		}
	}

	for _, nc := range newNodeClaims {
		nc.FinalizeScheduling()
	}

	return Results{
		NewNodeClaims: newNodeClaims,
		ExistingNodes: s.existingNodes,
		PodErrors:     nil, // Assume all handled or remaining will be retried
	}, nil
}
