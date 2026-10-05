package scheduling

import (
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/sets"

	v1 "sigs.k8s.io/karpenter/pkg/apis/v1"
	"sigs.k8s.io/karpenter/pkg/scheduling"
)

// These tests use plain `testing` so they run without the envtest-backed ginkgo suite:
//
//	go test ./pkg/controllers/provisioning/scheduling/ -run TestKubepacs

func kubepacsTestNodePool(name string, kubepacs bool, taints ...corev1.Taint) *NodeClaimTemplate {
	return kubepacsTestNodePoolWithLabels(name, kubepacs, nil, taints...)
}

func kubepacsTestNodePoolWithLabels(name string, kubepacs bool, labels map[string]string, taints ...corev1.Taint) *NodeClaimTemplate {
	np := &v1.NodePool{
		ObjectMeta: metav1.ObjectMeta{Name: name, UID: types.UID(name)},
		Spec: v1.NodePoolSpec{
			Template: v1.NodeClaimTemplate{
				ObjectMeta: v1.ObjectMeta{Labels: labels},
				Spec: v1.NodeClaimTemplateSpec{
					NodeClassRef: &v1.NodeClassReference{Group: "karpenter.k8s.aws", Kind: "EC2NodeClass", Name: name},
					Taints:       taints,
				},
			},
		},
	}
	if kubepacs {
		np.Spec.Template.ObjectMeta.Annotations = map[string]string{defaultKubepacsStrategyAnnotation: defaultKubepacsStrategyValue}
	}
	return NewNodeClaimTemplate(np)
}

func kubepacsTestPod(name string, nodeSelector map[string]string, tolerations ...corev1.Toleration) (*corev1.Pod, *PodData) {
	p := &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{Name: name, UID: types.UID(name)},
		Spec:       corev1.PodSpec{NodeSelector: nodeSelector, Tolerations: tolerations},
	}
	reqs := scheduling.NewPodRequirements(p)
	return p, &PodData{Requirements: reqs, StrictRequirements: reqs}
}

func TestKubepacsGroupsPodsByNodePool(t *testing.T) {
	webTaint := corev1.Taint{Key: "workload", Value: "web", Effect: corev1.TaintEffectNoSchedule}
	wsTaint := corev1.Taint{Key: "workload", Value: "workspaces", Effect: corev1.TaintEffectNoSchedule}
	web := kubepacsTestNodePool("web-spot", true, webTaint)
	ws := kubepacsTestNodePool("workspaces-spot", true, wsTaint)
	plain := kubepacsTestNodePool("workspaces", false, wsTaint)
	templates := []*NodeClaimTemplate{web, ws, plain}

	webPod, webData := kubepacsTestPod("web-1", nil,
		corev1.Toleration{Key: "workload", Operator: corev1.TolerationOpEqual, Value: "web", Effect: corev1.TaintEffectNoSchedule})
	wsPod, wsData := kubepacsTestPod("ws-1", map[string]string{v1.NodePoolLabelKey: "workspaces-spot"},
		corev1.Toleration{Key: "workload", Operator: corev1.TolerationOpEqual, Value: "workspaces", Effect: corev1.TaintEffectNoSchedule})
	// Pinned to the non-KubePACS NodePool: must be left to the default scheduler
	plainPod, plainData := kubepacsTestPod("ws-ondemand", map[string]string{v1.NodePoolLabelKey: "workspaces"},
		corev1.Toleration{Key: "workload", Operator: corev1.TolerationOpEqual, Value: "workspaces", Effect: corev1.TaintEffectNoSchedule})
	// Tolerates nothing: no NodePool here can host it
	strayPod, strayData := kubepacsTestPod("stray", nil)

	podData := map[types.UID]*PodData{webPod.UID: webData, wsPod.UID: wsData, plainPod.UID: plainData, strayPod.UID: strayData}
	groups, others := groupKubepacsPods([]*corev1.Pod{wsPod, plainPod, webPod, strayPod}, podData, templates)

	// Pods without a KubePACS NodePool are returned for the default scheduler, in order
	if len(others) != 2 || others[0] != plainPod || others[1] != strayPod {
		t.Errorf("expected regular pods [ws-ondemand stray] to be left for the default scheduler, got %d pods", len(others))
	}
	if len(groups) != 2 {
		t.Fatalf("expected 2 KubePACS groups, got %d", len(groups))
	}
	// Groups follow template (weight) order, not pod order
	if groups[0].template != web || len(groups[0].pods) != 1 || groups[0].pods[0] != webPod {
		t.Errorf("web-spot group: got template %s with %d pods", groups[0].template.NodePoolName, len(groups[0].pods))
	}
	if groups[1].template != ws || len(groups[1].pods) != 1 || groups[1].pods[0] != wsPod {
		t.Errorf("workspaces-spot group: got template %s with %d pods", groups[1].template.NodePoolName, len(groups[1].pods))
	}
}

func TestKubepacsTemplateForPodRespectsRequirements(t *testing.T) {
	a := kubepacsTestNodePool("pool-a", true)
	b := kubepacsTestNodePool("pool-b", true)
	templates := []*NodeClaimTemplate{a, b}

	// No constraints: the first (highest-weight) KubePACS NodePool wins
	anyPod, anyData := kubepacsTestPod("any", nil)
	if got := kubepacsTemplateForPod(anyPod, anyData, templates); got != a {
		t.Errorf("unconstrained pod: expected pool-a, got %v", got)
	}
	// nodeSelector on the NodePool label routes the pod to that NodePool only
	bPod, bData := kubepacsTestPod("b", map[string]string{v1.NodePoolLabelKey: "pool-b"})
	if got := kubepacsTemplateForPod(bPod, bData, templates); got != b {
		t.Errorf("pool-b pod: expected pool-b, got %v", got)
	}
	// A NodePool that doesn't exist matches nothing
	nonePod, noneData := kubepacsTestPod("none", map[string]string{v1.NodePoolLabelKey: "pool-c"})
	if got := kubepacsTemplateForPod(nonePod, noneData, templates); got != nil {
		t.Errorf("pool-c pod: expected no template, got %s", got.NodePoolName)
	}
}

func TestKubepacsScenarioLabelStillApplies(t *testing.T) {
	scenario := kubepacsTestNodePoolWithLabels("scenario", true, map[string]string{defaultKubepacsScenarioInstanceLabel: "s1"})
	templates := []*NodeClaimTemplate{scenario}

	other, otherData := kubepacsTestPod("other", map[string]string{defaultKubepacsScenarioInstanceLabel: "s2"})
	if got := kubepacsTemplateForPod(other, otherData, templates); got != nil {
		t.Errorf("pod for another scenario should not match, got %s", got.NodePoolName)
	}
	same, sameData := kubepacsTestPod("same", map[string]string{defaultKubepacsScenarioInstanceLabel: "s1"})
	if got := kubepacsTemplateForPod(same, sameData, templates); got != scenario {
		t.Errorf("pod for the same scenario should match")
	}
}

func TestKubepacsExcludeRunningPools(t *testing.T) {
	alpha := allowedInstance{InstanceType: "m5.large", AvailabilityZone: "zone-a"}
	beta := allowedInstance{InstanceType: "c5.large", AvailabilityZone: "zone-b"}
	gamma := allowedInstance{InstanceType: "c5.large", AvailabilityZone: "zone-a"}
	candidates := []allowedInstance{alpha, beta, gamma}

	// The running pool is removed; the same type in another zone is a different pool and stays
	got := excludeRunningPools(candidates, sets.New(beta.key()))
	if len(got) != 2 || got[0] != alpha || got[1] != gamma {
		t.Errorf("expected [alpha gamma], got %v", got)
	}
	// Nothing running: unchanged
	if got := excludeRunningPools(candidates, sets.New[string]()); len(got) != 3 {
		t.Errorf("expected all candidates when nothing runs, got %v", got)
	}
	// Every candidate running: keep them all rather than leaving the pod pending
	if got := excludeRunningPools(candidates, sets.New(alpha.key(), beta.key(), gamma.key())); len(got) != 3 {
		t.Errorf("expected exclusion to be relaxed when it empties the candidates, got %v", got)
	}
}

func TestKubepacsCandidatesKeyIgnoresOrder(t *testing.T) {
	a := allowedInstance{InstanceType: "m5.large", AvailabilityZone: "zone-a"}
	b := allowedInstance{InstanceType: "c5.large", AvailabilityZone: "zone-b"}
	if candidatesKey([]allowedInstance{a, b}) != candidatesKey([]allowedInstance{b, a}) {
		t.Errorf("candidate keys should not depend on order")
	}
	if candidatesKey([]allowedInstance{a}) == candidatesKey([]allowedInstance{b}) {
		t.Errorf("different candidates should have different keys")
	}
}
