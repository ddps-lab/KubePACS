package scheduling

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"

	"github.com/samber/lo"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/log"

	v1 "sigs.k8s.io/karpenter/pkg/apis/v1"
	"sigs.k8s.io/karpenter/pkg/cloudprovider"
	"sigs.k8s.io/karpenter/pkg/scheduling"
	"sigs.k8s.io/karpenter/pkg/scheduling/dynamicresources"
)

const (
	defaultKubepacsStrategyAnnotation    = "kubepacs.io/strategy"
	defaultKubepacsStrategyValue         = "kubepacs"
	defaultKubepacsScenarioInstanceLabel = "kubepacs-scenario-instance"
	defaultKubepacsSolverPath            = "/usr/local/bin/kubepacs_cli.py"
)

type PythonSolverResult struct {
	InstanceType     string `json:"instance_type"`
	AvailabilityZone string `json:"availability_zone"`
	NumInstances     int    `json:"num_instances"`
}

type allowedInstance struct {
	InstanceType     string `json:"instance_type"`
	AvailabilityZone string `json:"availability_zone"`
}

// kubepacsGroup is the set of pending pods assigned to one KubePACS NodePool.
type kubepacsGroup struct {
	template *NodeClaimTemplate
	pods     []*corev1.Pod
}

func isKubepacsTemplate(nct *NodeClaimTemplate) bool {
	val, ok := nct.Annotations[kubepacsStrategyAnnotation()]
	return ok && val == kubepacsStrategyValue()
}

func podMatchesKubepacsTemplate(p *corev1.Pod, nct *NodeClaimTemplate) bool {
	if !isKubepacsTemplate(nct) {
		return false
	}

	scenarioInstance, ok := nct.Labels[kubepacsScenarioInstanceLabel()]
	if !ok {
		return true
	}

	return p.Spec.NodeSelector != nil && p.Spec.NodeSelector[kubepacsScenarioInstanceLabel()] == scenarioInstance
}

// kubepacsTemplateForPod returns the KubePACS NodePool template a pod belongs to, or nil when no KubePACS NodePool can
// host it. Templates are ordered by NodePool weight, so the highest-weight compatible KubePACS NodePool wins. A pod
// belongs to a NodePool only when it tolerates the NodePool taints and its requirements are compatible with the
// NodePool requirements; this keeps pods of one KubePACS NodePool from being solved against another.
func kubepacsTemplateForPod(p *corev1.Pod, podData *PodData, templates []*NodeClaimTemplate) *NodeClaimTemplate {
	for _, nct := range templates {
		if !podMatchesKubepacsTemplate(p, nct) {
			continue
		}
		if err := scheduling.Taints(nct.Spec.Taints).ToleratesPod(p); err != nil {
			continue
		}
		if podData != nil {
			if err := nct.Requirements.Compatible(podData.Requirements, scheduling.AllowUndefinedWellKnownLabels); err != nil {
				continue
			}
		}
		return nct
	}
	return nil
}

// groupKubepacsPods splits pods by their KubePACS NodePool, preserving template order. Pods without a KubePACS NodePool
// are left out and handled by the default scheduler.
func groupKubepacsPods(pods []*corev1.Pod, podData map[types.UID]*PodData, templates []*NodeClaimTemplate) []*kubepacsGroup {
	byTemplate := map[*NodeClaimTemplate]*kubepacsGroup{}
	for _, p := range pods {
		nct := kubepacsTemplateForPod(p, podData[p.UID], templates)
		if nct == nil {
			continue
		}
		g, ok := byTemplate[nct]
		if !ok {
			g = &kubepacsGroup{template: nct}
			byTemplate[nct] = g
		}
		g.pods = append(g.pods, p)
	}
	var groups []*kubepacsGroup
	for _, nct := range templates {
		if g, ok := byTemplate[nct]; ok {
			groups = append(groups, g)
		}
	}
	return groups
}

// spotAllowedInstances lists the available spot (instance type, zone) offerings of a single NodePool template.
func spotAllowedInstances(nct *NodeClaimTemplate) []allowedInstance {
	var allowed []allowedInstance
	for _, it := range nct.InstanceTypeOptions {
		for _, offering := range it.Offerings {
			if offering.Available && offering.CapacityType() == v1.CapacityTypeSpot {
				allowed = append(allowed, allowedInstance{InstanceType: it.Name, AvailabilityZone: offering.Zone()})
			}
		}
	}
	return allowed
}

func kubepacsEnabled() bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv("KUBEPACS_ENABLED"))) {
	case "false", "0", "no", "off", "disabled":
		return false
	default:
		return true
	}
}

func kubepacsStrategyAnnotation() string {
	return getenvDefault("KUBEPACS_STRATEGY_ANNOTATION", defaultKubepacsStrategyAnnotation)
}

func kubepacsStrategyValue() string {
	return getenvDefault("KUBEPACS_STRATEGY_VALUE", defaultKubepacsStrategyValue)
}

func kubepacsScenarioInstanceLabel() string {
	return getenvDefault("KUBEPACS_SCENARIO_INSTANCE_LABEL", defaultKubepacsScenarioInstanceLabel)
}

func kubepacsSolverPath() string {
	return getenvDefault("KUBEPACS_SOLVER_PATH", defaultKubepacsSolverPath)
}

func getenvDefault(key, defaultValue string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return defaultValue
}

func kubepacsRegion() string {
	region := os.Getenv("AWS_REGION")
	if region == "" {
		region = os.Getenv("AWS_DEFAULT_REGION")
	}
	if region == "" {
		region = "us-east-1" // fallback default
	}
	return region
}

func (s *Scheduler) solvePython(ctx context.Context, pods []*corev1.Pod) (Results, error) {
	if len(pods) == 0 {
		return Results{}, nil
	}

	// 0. Keep only pods that belong to a KubePACS NodePool.
	// Pods that don't match any KubePACS NodePool are handled by the original Karpenter logic.
	groups := groupKubepacsPods(pods, s.cachedPodData, s.nodeClaimTemplates)
	if len(groups) == 0 {
		return Results{}, fmt.Errorf("no pods match kubepacs NodePool, fallback to original scheduler")
	}
	kubepacsPodCount := lo.SumBy(groups, func(g *kubepacsGroup) int { return len(g.pods) })
	log.FromContext(ctx).Info("Filtered pods for kubepacs",
		"totalPods", len(pods), "kubepacsPods", kubepacsPodCount, "kubepacsNodePools", len(groups))

	// 1. First, try to schedule pods to existing nodes (including inflight)
	// This matches the original Karpenter behavior and prevents over-provisioning
	remaining := 0
	for _, g := range groups {
		var left []*corev1.Pod
		for _, p := range g.pods {
			// Try existing nodes first (Ready + Not Ready inflight nodes)
			if err := s.addToExistingNode(ctx, p); err != nil {
				// Try inflight NodeClaims created in this scheduling loop
				if err := s.addToInflightNode(ctx, p); err != nil {
					left = append(left, p)
				}
			}
		}
		g.pods = left
		remaining += len(left)
	}

	// If all pods scheduled to existing/inflight nodes, we're done
	if remaining == 0 {
		log.FromContext(ctx).Info("All pods scheduled to existing/inflight nodes, skipping Python solver")
		return s.kubepacsResults(), nil
	}

	// 2. Solve each KubePACS NodePool separately, using only that NodePool's offerings
	for _, g := range groups {
		if len(g.pods) == 0 {
			continue
		}
		newNodeClaims, err := s.solvePythonForNodePool(ctx, g.template, g.pods)
		if err != nil {
			return Results{}, err
		}
		s.newNodeClaims = append(s.newNodeClaims, newNodeClaims...)
	}

	return s.kubepacsResults(), nil
}

func (s *Scheduler) kubepacsResults() Results {
	for _, nc := range s.newNodeClaims {
		nc.FinalizeScheduling(s.draDriversForNodeClaim(nc)...)
	}
	results := Results{
		NewNodeClaims: s.newNodeClaims,
		ExistingNodes: s.existingNodes,
		PodErrors:     nil, // Assume all handled or remaining will be retried
	}
	if s.allocator != nil {
		results.DRAClaimAllocationMetadata = lo.MapKeys(
			s.allocator.ResourceClaimAllocationMetadata(),
			func(_ *dynamicresources.ResourceClaimAllocationMetadata, k dynamicresources.ResourceClaimID) types.NamespacedName {
				return k.Value()
			},
		)
	}
	return results
}

//nolint:gocyclo
func (s *Scheduler) solvePythonForNodePool(ctx context.Context, nct *NodeClaimTemplate, pods []*corev1.Pod) ([]*NodeClaim, error) {
	log.FromContext(ctx).Info("Scheduling remaining pods with Python solver",
		"NodePool", nct.NodePoolName, "remainingPods", len(pods))

	// 1. Calculate Pod Requirements (Average)
	var totalCPU, totalMem float64
	for _, p := range pods {
		req := s.cachedPodData[p.UID].Requests
		totalCPU += float64(req.Cpu().MilliValue()) / 1000.0
		totalMem += float64(req.Memory().Value()) / (1024 * 1024 * 1024) // GiB
	}
	avgCPU := totalCPU / float64(len(pods))
	avgMem := totalMem / float64(len(pods))

	if avgCPU == 0 {
		avgCPU = 0.1
	}
	if avgMem == 0 {
		avgMem = 0.1
	}

	// 2. Prepare Allowed Instances List from this NodePool only
	allowedInstances := spotAllowedInstances(nct)
	allowedJson, err := json.Marshal(allowedInstances)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal allowed instances: %v", err)
	}
	log.FromContext(ctx).Info(fmt.Sprintf("Allowed instances count: %d", len(allowedInstances)), "NodePool", nct.NodePoolName)

	// 3. Get AWS Region
	region := kubepacsRegion()
	log.FromContext(ctx).Info("Using AWS region for Python solver", "region", region)

	// 4. Call Python Script
	cmd := exec.Command("python3", "-u", kubepacsSolverPath(),
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

	log.FromContext(ctx).Info("Calling Python solver", "NodePool", nct.NodePoolName, "args", cmd.Args)
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("python script execution failed: %v, stderr: %s", err, stderr.String())
	}

	// 5. Parse Output
	if stderr.Len() > 0 {
		log.FromContext(ctx).Info("Python solver stderr", "stderr", stderr.String())
	}
	log.FromContext(ctx).Info("Python solver output", "NodePool", nct.NodePoolName, "output", out.String())

	var pythonResults []PythonSolverResult
	if err := json.Unmarshal(out.Bytes(), &pythonResults); err != nil {
		return nil, fmt.Errorf("failed to parse python output: %v, output: %s", err, out.String())
	}

	// 6. Create NodeClaims from this NodePool's template
	var newNodeClaims []*NodeClaim
	podIndex := 0

	for _, res := range pythonResults {
		chosenIT, ok := lo.Find(nct.InstanceTypeOptions, func(it *cloudprovider.InstanceType) bool { return it.Name == res.InstanceType })
		if !ok {
			log.FromContext(ctx).Error(nil, "Instance type from python solver not found in NodePool", "NodePool", nct.NodePoolName, "instanceType", res.InstanceType)
			continue
		}
		for i := 0; i < res.NumInstances; i++ {
			// Create NodeClaim
			nc := NewNodeClaim(
				nct,
				s.topology,
				s.daemonOverheadGroups[nct],
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
			// Guard against pods without requests, which would otherwise divide by zero and crash the controller
			podCPU := max(podRequest.Cpu().MilliValue(), 1)
			podMem := max(podRequest.Memory().Value(), 1)
			capacity := int(min(nodeCapacity.Cpu().MilliValue()/podCPU, nodeCapacity.Memory().Value()/podMem))

			podsForNode := []*corev1.Pod{}
			for j := 0; j < capacity && podIndex < len(pods); j++ {
				podsForNode = append(podsForNode, pods[podIndex])
				podIndex++
			}

			for _, p := range podsForNode {
				r, its, ofs, result, err := nc.CanAdd(ctx, p, s.cachedPodData[p.UID], false, s.allocator)
				if err == nil {
					nc.Add(ctx, p, s.cachedPodData[p.UID], r, its, ofs, result, s.allocator)
				} else {
					log.FromContext(ctx).Error(err, "Failed to add pod to python-selected node")
				}
			}

			if len(nc.Pods) > 0 {
				newNodeClaims = append(newNodeClaims, nc)
				s.remainingResources[nc.NodePoolName] = subtractMax(s.remainingResources[nc.NodePoolName], nc.InstanceTypeOptions)
			}
		}
	}

	return newNodeClaims, nil
}
