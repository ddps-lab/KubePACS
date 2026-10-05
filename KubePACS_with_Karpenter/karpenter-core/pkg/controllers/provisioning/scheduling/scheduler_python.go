package scheduling

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strings"

	"github.com/samber/lo"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/sets"
	"sigs.k8s.io/controller-runtime/pkg/log"

	v1 "sigs.k8s.io/karpenter/pkg/apis/v1"
	"sigs.k8s.io/karpenter/pkg/cloudprovider"
	"sigs.k8s.io/karpenter/pkg/scheduling"
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

func (a allowedInstance) key() string { return a.InstanceType + "/" + a.AvailabilityZone }

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
// are returned separately and handled by the default scheduler.
func groupKubepacsPods(pods []*corev1.Pod, podData map[types.UID]*PodData, templates []*NodeClaimTemplate) (groups []*kubepacsGroup, others []*corev1.Pod) {
	byTemplate := map[*NodeClaimTemplate]*kubepacsGroup{}
	for _, p := range pods {
		nct := kubepacsTemplateForPod(p, podData[p.UID], templates)
		if nct == nil {
			others = append(others, p)
			continue
		}
		g, ok := byTemplate[nct]
		if !ok {
			g = &kubepacsGroup{template: nct}
			byTemplate[nct] = g
		}
		g.pods = append(g.pods, p)
	}
	for _, nct := range templates {
		if g, ok := byTemplate[nct]; ok {
			groups = append(groups, g)
		}
	}
	return groups, others
}

// excludeRunningPools drops candidates whose (instance type, zone) pool is already running in the NodePool, so that
// replacements and new replicas land on different spot pools. When every candidate is excluded the full list is kept,
// since leaving the pod pending is worse than sharing a pool.
func excludeRunningPools(candidates []allowedInstance, running sets.Set[string]) []allowedInstance {
	if running.Len() == 0 {
		return candidates
	}
	filtered := lo.Filter(candidates, func(c allowedInstance, _ int) bool { return !running.Has(c.key()) })
	if len(filtered) == 0 {
		return candidates
	}
	return filtered
}

func candidatesKey(candidates []allowedInstance) string {
	keys := lo.Map(candidates, func(c allowedInstance, _ int) string { return c.key() })
	sort.Strings(keys)
	return strings.Join(keys, ",")
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

// solvePython places pods that belong to KubePACS NodePools onto existing, in-flight, or solver-selected spot
// NodeClaims. It returns the pods it did not place: pods of regular NodePools and KubePACS pods the solver could not
// place. The caller schedules those with the default scheduler in the same round, so nothing waits for another loop.
func (s *Scheduler) solvePython(ctx context.Context, pods []*corev1.Pod) []*corev1.Pod {
	groups, leftover := groupKubepacsPods(pods, s.cachedPodData, s.nodeClaimTemplates)
	if len(groups) == 0 {
		return pods
	}
	log.FromContext(ctx).Info("Filtered pods for kubepacs",
		"totalPods", len(pods), "kubepacsPods", len(pods)-len(leftover), "kubepacsNodePools", len(groups))

	for _, g := range groups {
		// 1. First, try to schedule pods to existing nodes (including inflight)
		// This matches the original Karpenter behavior and prevents over-provisioning
		var pending []*corev1.Pod
		for _, p := range g.pods {
			if err := s.addToExistingNode(ctx, p); err == nil {
				continue
			}
			if err := s.addToInflightNode(ctx, p); err == nil {
				continue
			}
			pending = append(pending, p)
		}
		if len(pending) == 0 {
			continue
		}
		// 2. Solve the rest with this NodePool's offerings only
		leftover = append(leftover, s.solveKubepacsNodePool(ctx, g.template, pending)...)
	}
	return leftover
}

// solveKubepacsNodePool places pods of one KubePACS NodePool and returns the pods it could not place.
//
// Pods are solved in rounds. Each round computes every pod's candidate (instance type, zone) offerings with the regular
// Karpenter compatibility check, which accounts for node selectors, volume topology, and topology spread. Pods that
// share the same candidates are solved together. Placing pods records their topology, so a replica that could not join
// its sibling's zone gets the other zones as candidates in the next round: with a zonal topology spread, replicas end
// up solved once per zone.
func (s *Scheduler) solveKubepacsNodePool(ctx context.Context, nct *NodeClaimTemplate, pods []*corev1.Pod) []*corev1.Pod {
	running := s.runningKubepacsPools(nct.NodePoolName)
	var unplaced []*corev1.Pod
	remaining := pods
	for len(remaining) > 0 {
		// NodeClaims created in earlier rounds may already fit some pods
		remaining = lo.Filter(remaining, func(p *corev1.Pod, _ int) bool { return s.addToInflightNode(ctx, p) != nil })
		if len(remaining) == 0 {
			break
		}

		candidates := map[*corev1.Pod][]allowedInstance{}
		instanceTypes := map[string]*cloudprovider.InstanceType{}
		var solvable []*corev1.Pod
		for _, p := range remaining {
			cands, its, err := s.kubepacsCandidates(ctx, nct, p)
			if err != nil || len(cands) == 0 {
				log.FromContext(ctx).V(1).Info("no kubepacs candidates for pod, falling back to default", "Pod", p.Name, "NodePool", nct.NodePoolName, "error", err)
				unplaced = append(unplaced, p)
				continue
			}
			candidates[p] = excludeRunningPools(cands, running)
			for name, it := range its {
				instanceTypes[name] = it
			}
			solvable = append(solvable, p)
		}
		if len(solvable) == 0 {
			break
		}

		key := candidatesKey(candidates[solvable[0]])
		batch, rest := lo.FilterReject(solvable, func(p *corev1.Pod, _ int) bool { return candidatesKey(candidates[p]) == key })

		results, err := s.callKubepacsSolver(ctx, nct, batch, candidates[batch[0]])
		if err != nil {
			log.FromContext(ctx).Error(err, "python solver failed, falling back to default", "NodePool", nct.NodePoolName)
			return append(unplaced, solvable...)
		}
		placed := s.createKubepacsNodeClaims(ctx, nct, batch, candidates[batch[0]], instanceTypes, results)
		if placed.Len() == 0 {
			// No progress for this batch: hand it to the default scheduler instead of retrying forever
			unplaced = append(unplaced, batch...)
		} else {
			// Pods left out (e.g. by topology spread) get fresh candidates in the next round
			rest = append(rest, lo.Reject(batch, func(p *corev1.Pod, _ int) bool { return placed.Has(p.UID) })...)
		}
		remaining = rest
	}
	return unplaced
}

// runningKubepacsPools returns the (instance type, zone) pools of the NodePool's live nodes.
func (s *Scheduler) runningKubepacsPools(nodePoolName string) sets.Set[string] {
	running := sets.New[string]()
	for _, n := range s.existingNodes {
		if n.MarkedForDeletion() {
			continue
		}
		labels := n.Labels()
		if labels[v1.NodePoolLabelKey] != nodePoolName {
			continue
		}
		it, zone := labels[corev1.LabelInstanceTypeStable], labels[corev1.LabelTopologyZone]
		if it != "" && zone != "" {
			running.Insert(allowedInstance{InstanceType: it, AvailabilityZone: zone}.key())
		}
	}
	return running
}

// kubepacsCandidates returns the available spot offerings of the NodePool that can host the pod, using the same
// compatibility check as a regular NodeClaim (taints, requirements, volume topology, topology spread, resources).
func (s *Scheduler) kubepacsCandidates(ctx context.Context, nct *NodeClaimTemplate, p *corev1.Pod) ([]allowedInstance, map[string]*cloudprovider.InstanceType, error) {
	its := nct.InstanceTypeOptions
	if remaining, ok := s.remainingResources[nct.NodePoolName]; ok {
		its = filterByRemainingResources(its, remaining)
	}
	if len(its) == 0 {
		return nil, nil, fmt.Errorf("all instance types exceed limits for nodepool")
	}
	probe := NewNodeClaim(nct, s.topology, s.daemonOverheadGroups[nct], its, s.reservationManager, s.reservedOfferingMode)
	requirements, fits, _, _, err := probe.CanAdd(ctx, p, s.cachedPodData[p.UID], false, s.allocator)
	if err != nil {
		return nil, nil, err
	}
	var candidates []allowedInstance
	byName := map[string]*cloudprovider.InstanceType{}
	for _, it := range fits {
		for _, offering := range it.Offerings {
			if !offering.Available || offering.CapacityType() != v1.CapacityTypeSpot {
				continue
			}
			if requirements.Compatible(offering.Requirements, scheduling.AllowUndefinedWellKnownLabels) != nil {
				continue
			}
			candidates = append(candidates, allowedInstance{InstanceType: it.Name, AvailabilityZone: offering.Zone()})
			byName[it.Name] = it
		}
	}
	return candidates, byName, nil
}

func (s *Scheduler) callKubepacsSolver(ctx context.Context, nct *NodeClaimTemplate, pods []*corev1.Pod, candidates []allowedInstance) ([]PythonSolverResult, error) {
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

	// 2. Allowed Instances: offerings that can host these pods in this NodePool
	allowedJson, err := json.Marshal(candidates)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal allowed instances: %v", err)
	}
	log.FromContext(ctx).Info(fmt.Sprintf("Allowed instances count: %d", len(candidates)), "NodePool", nct.NodePoolName)

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
	return pythonResults, nil
}

// createKubepacsNodeClaims creates spot NodeClaims from the solver result and fills them with the batch pods. It returns
// the UIDs of the pods that were placed.
func (s *Scheduler) createKubepacsNodeClaims(ctx context.Context, nct *NodeClaimTemplate, pods []*corev1.Pod, candidates []allowedInstance,
	instanceTypes map[string]*cloudprovider.InstanceType, results []PythonSolverResult) sets.Set[types.UID] {
	allowed := sets.New(lo.Map(candidates, func(c allowedInstance, _ int) string { return c.key() })...)
	placed := sets.New[types.UID]()
	podIndex := 0

	for _, res := range results {
		chosenIT, ok := instanceTypes[res.InstanceType]
		if !ok || !allowed.Has(allowedInstance{InstanceType: res.InstanceType, AvailabilityZone: res.AvailabilityZone}.key()) {
			log.FromContext(ctx).Error(nil, "Offering from python solver is not a candidate for these pods", "NodePool", nct.NodePoolName,
				"instanceType", res.InstanceType, "zone", res.AvailabilityZone)
			continue
		}
		for i := 0; i < res.NumInstances && podIndex < len(pods); i++ {
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
			// The python script already checked capacity; CanAdd still guards requirements and topology.
			podRequest := s.cachedPodData[pods[podIndex].UID].Requests // Use first pod as representative
			nodeCapacity := chosenIT.Capacity
			// Guard against pods without requests, which would otherwise divide by zero and crash the controller
			podCPU := max(podRequest.Cpu().MilliValue(), 1)
			podMem := max(podRequest.Memory().Value(), 1)
			capacity := int(min(nodeCapacity.Cpu().MilliValue()/podCPU, nodeCapacity.Memory().Value()/podMem))

			for j := 0; j < capacity && podIndex < len(pods); j++ {
				p := pods[podIndex]
				podIndex++
				r, its, ofs, result, err := nc.CanAdd(ctx, p, s.cachedPodData[p.UID], false, s.allocator)
				if err != nil {
					log.FromContext(ctx).V(1).Info("pod does not fit python-selected node, retrying in the next round", "Pod", p.Name, "error", err)
					continue
				}
				nc.Add(ctx, p, s.cachedPodData[p.UID], r, its, ofs, result, s.allocator)
				placed.Insert(p.UID)
			}

			if len(nc.Pods) > 0 {
				s.newNodeClaims = append(s.newNodeClaims, nc)
				s.remainingResources[nc.NodePoolName] = subtractMax(s.remainingResources[nc.NodePoolName], nc.InstanceTypeOptions)
			}
		}
	}
	return placed
}
