package scheduling_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	v1 "sigs.k8s.io/karpenter/pkg/apis/v1"
	"sigs.k8s.io/karpenter/pkg/cloudprovider"
	"sigs.k8s.io/karpenter/pkg/cloudprovider/fake"
	pscheduling "sigs.k8s.io/karpenter/pkg/scheduling"
	"sigs.k8s.io/karpenter/pkg/test"
	. "sigs.k8s.io/karpenter/pkg/test/expectations"
)

// stubSolver stands in for kubepacs_cli.py: it records every call and allocates all pods to the first allowed
// (instance type, zone) offering. KUBEPACS_STUB_MODE=fail exits non-zero and =bogus returns an offering that is not a
// candidate, to exercise the fallback paths.
const stubSolver = `#!/usr/bin/env python3
import json, os, sys
allowed = json.load(sys.stdin)
with open(os.environ["KUBEPACS_STUB_LOG"], "a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "allowed": allowed}) + "\n")
mode = os.environ.get("KUBEPACS_STUB_MODE", "first")
if mode == "fail":
    sys.exit(1)
count = int(sys.argv[sys.argv.index("--pod-count") + 1])
if mode == "bogus":
    print(json.dumps([{"instance_type": "not-a-candidate", "availability_zone": "nowhere", "num_instances": count}]))
    sys.exit(0)
first = allowed[0]
print(json.dumps([{"instance_type": first["instance_type"], "availability_zone": first["availability_zone"], "num_instances": count}]))
`

type stubCall struct {
	Args    []string `json:"args"`
	Allowed []struct {
		InstanceType     string `json:"instance_type"`
		AvailabilityZone string `json:"availability_zone"`
	} `json:"allowed"`
}

func (c stubCall) allows(instanceType, zone string) bool {
	for _, a := range c.Allowed {
		if a.InstanceType == instanceType && a.AvailabilityZone == zone {
			return true
		}
	}
	return false
}

func readStubCalls(path string) []stubCall {
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return nil
	}
	Expect(err).ToNot(HaveOccurred())
	var calls []stubCall
	for _, line := range strings.Split(strings.TrimSpace(string(data)), "\n") {
		if line == "" {
			continue
		}
		var c stubCall
		Expect(json.Unmarshal([]byte(line), &c)).To(Succeed())
		calls = append(calls, c)
	}
	return calls
}

func kubepacsNodePool(name string, taint *corev1.Taint) *v1.NodePool {
	np := test.NodePool(v1.NodePool{
		ObjectMeta: metav1.ObjectMeta{Name: name},
		Spec: v1.NodePoolSpec{
			Template: v1.NodeClaimTemplate{
				ObjectMeta: v1.ObjectMeta{Annotations: map[string]string{"kubepacs.io/strategy": "kubepacs"}},
				Spec: v1.NodeClaimTemplateSpec{
					Requirements: []v1.NodeSelectorRequirementWithMinValues{{
						Key:      v1.CapacityTypeLabelKey,
						Operator: corev1.NodeSelectorOpIn,
						Values:   []string{v1.CapacityTypeSpot, v1.CapacityTypeOnDemand},
					}},
				},
			},
		},
	})
	if taint != nil {
		np.Spec.Template.Spec.Taints = []corev1.Taint{*taint}
	}
	return np
}

func kubepacsPod(taint *corev1.Taint) *corev1.Pod {
	opts := test.PodOptions{ResourceRequirements: corev1.ResourceRequirements{
		Requests: corev1.ResourceList{corev1.ResourceCPU: resource.MustParse("1"), corev1.ResourceMemory: resource.MustParse("512Mi")},
	}}
	if taint != nil {
		opts.Tolerations = []corev1.Toleration{{Key: taint.Key, Operator: corev1.TolerationOpEqual, Value: taint.Value, Effect: taint.Effect}}
	}
	return test.UnschedulablePod(opts)
}

var _ = Describe("KubePACS", func() {
	var stubLog string

	BeforeEach(func() {
		dir := GinkgoT().TempDir()
		solver := filepath.Join(dir, "kubepacs_stub.py")
		Expect(os.WriteFile(solver, []byte(stubSolver), 0o755)).To(Succeed())
		stubLog = filepath.Join(dir, "calls.jsonl")
		GinkgoT().Setenv("KUBEPACS_SOLVER_PATH", solver)
		GinkgoT().Setenv("KUBEPACS_STUB_LOG", stubLog)
		GinkgoT().Setenv("KUBEPACS_ENABLED", "true")
		GinkgoT().Setenv("KUBEPACS_STUB_MODE", "first")
	})
	AfterEach(func() {
		cloudProvider.InstanceTypesForNodePool = map[string][]*cloudprovider.InstanceType{}
	})

	It("should provision the solver's spot offering for a single KubePACS NodePool", func() {
		np := kubepacsNodePool("kubepacs", nil)
		ExpectApplied(ctx, env.Client, np)
		pod := kubepacsPod(nil)
		ExpectProvisioned(ctx, env.Client, cluster, cloudProvider, prov, pod)

		calls := readStubCalls(stubLog)
		Expect(calls).To(HaveLen(1))
		Expect(calls[0].Allowed).ToNot(BeEmpty())
		node := ExpectScheduled(ctx, env.Client, pod)
		Expect(node.Labels).To(HaveKeyWithValue(v1.NodePoolLabelKey, "kubepacs"))
		Expect(node.Labels).To(HaveKeyWithValue(corev1.LabelInstanceTypeStable, calls[0].Allowed[0].InstanceType))
		Expect(node.Labels).To(HaveKeyWithValue(corev1.LabelTopologyZone, calls[0].Allowed[0].AvailabilityZone))
		Expect(node.Labels).To(HaveKeyWithValue(v1.CapacityTypeLabelKey, v1.CapacityTypeSpot))
	})

	It("should solve each KubePACS NodePool separately with its own offerings", func() {
		webTaint := &corev1.Taint{Key: "workload", Value: "web", Effect: corev1.TaintEffectNoSchedule}
		wsTaint := &corev1.Taint{Key: "workload", Value: "workspaces", Effect: corev1.TaintEffectNoSchedule}
		web := kubepacsNodePool("web-spot", webTaint)
		ws := kubepacsNodePool("workspaces-spot", wsTaint)
		cloudProvider.InstanceTypesForNodePool = map[string][]*cloudprovider.InstanceType{
			"web-spot":        {fake.NewInstanceType("web-instance-type")},
			"workspaces-spot": {fake.NewInstanceType("workspaces-instance-type")},
		}
		ExpectApplied(ctx, env.Client, web, ws)
		webPod := kubepacsPod(webTaint)
		wsPod := kubepacsPod(wsTaint)
		ExpectProvisioned(ctx, env.Client, cluster, cloudProvider, prov, webPod, wsPod)

		calls := readStubCalls(stubLog)
		Expect(calls).To(HaveLen(2))
		for _, c := range calls {
			types := map[string]bool{}
			for _, a := range c.Allowed {
				types[a.InstanceType] = true
			}
			// Each call only sees one NodePool's offerings
			Expect(types).To(HaveLen(1))
		}
		webNode := ExpectScheduled(ctx, env.Client, webPod)
		Expect(webNode.Labels).To(HaveKeyWithValue(v1.NodePoolLabelKey, "web-spot"))
		Expect(webNode.Labels).To(HaveKeyWithValue(corev1.LabelInstanceTypeStable, "web-instance-type"))
		wsNode := ExpectScheduled(ctx, env.Client, wsPod)
		Expect(wsNode.Labels).To(HaveKeyWithValue(v1.NodePoolLabelKey, "workspaces-spot"))
		Expect(wsNode.Labels).To(HaveKeyWithValue(corev1.LabelInstanceTypeStable, "workspaces-instance-type"))
	})

	It("should not call the solver when no NodePool opts in", func() {
		ExpectApplied(ctx, env.Client, test.NodePool())
		pod := kubepacsPod(nil)
		ExpectProvisioned(ctx, env.Client, cluster, cloudProvider, prov, pod)

		Expect(readStubCalls(stubLog)).To(BeEmpty())
		ExpectScheduled(ctx, env.Client, pod)
	})

	It("should leave pods of a regular NodePool to the default scheduler", func() {
		wsTaint := &corev1.Taint{Key: "workload", Value: "workspaces", Effect: corev1.TaintEffectNoSchedule}
		ExpectApplied(ctx, env.Client, kubepacsNodePool("workspaces-spot", wsTaint), test.NodePool(v1.NodePool{ObjectMeta: metav1.ObjectMeta{Name: "regular"}}))
		pod := kubepacsPod(nil) // does not tolerate the KubePACS NodePool taint
		ExpectProvisioned(ctx, env.Client, cluster, cloudProvider, prov, pod)

		Expect(readStubCalls(stubLog)).To(BeEmpty())
		node := ExpectScheduled(ctx, env.Client, pod)
		Expect(node.Labels).To(HaveKeyWithValue(v1.NodePoolLabelKey, "regular"))
	})

	It("should fall back to the default scheduler when the solver fails", func() {
		GinkgoT().Setenv("KUBEPACS_STUB_MODE", "fail")
		ExpectApplied(ctx, env.Client, kubepacsNodePool("kubepacs", nil))
		pod := kubepacsPod(nil)
		ExpectProvisioned(ctx, env.Client, cluster, cloudProvider, prov, pod)

		Expect(readStubCalls(stubLog)).To(HaveLen(1))
		node := ExpectScheduled(ctx, env.Client, pod)
		Expect(node.Labels).To(HaveKeyWithValue(v1.NodePoolLabelKey, "kubepacs"))
	})

	It("should not call the solver when KUBEPACS_ENABLED is false", func() {
		GinkgoT().Setenv("KUBEPACS_ENABLED", "false")
		ExpectApplied(ctx, env.Client, kubepacsNodePool("kubepacs", nil))
		pod := kubepacsPod(nil)
		ExpectProvisioned(ctx, env.Client, cluster, cloudProvider, prov, pod)

		Expect(readStubCalls(stubLog)).To(BeEmpty())
		ExpectScheduled(ctx, env.Client, pod)
	})

	It("should spread replicas across zones by solving them in separate rounds", func() {
		ExpectApplied(ctx, env.Client, kubepacsNodePool("kubepacs", nil))
		labels := map[string]string{"app": "web"}
		spread := []corev1.TopologySpreadConstraint{{
			MaxSkew:           1,
			TopologyKey:       corev1.LabelTopologyZone,
			WhenUnsatisfiable: corev1.DoNotSchedule,
			LabelSelector:     &metav1.LabelSelector{MatchLabels: labels},
		}}
		pods := []*corev1.Pod{}
		for range 2 {
			p := kubepacsPod(nil)
			p.Labels = labels
			p.Spec.TopologySpreadConstraints = spread
			pods = append(pods, p)
		}
		ExpectProvisioned(ctx, env.Client, cluster, cloudProvider, prov, pods...)

		first := ExpectScheduled(ctx, env.Client, pods[0])
		second := ExpectScheduled(ctx, env.Client, pods[1])
		Expect(first.Labels[corev1.LabelTopologyZone]).ToNot(Equal(second.Labels[corev1.LabelTopologyZone]))
		Expect(first.Labels).To(HaveKeyWithValue(v1.CapacityTypeLabelKey, v1.CapacityTypeSpot))
		Expect(second.Labels).To(HaveKeyWithValue(v1.CapacityTypeLabelKey, v1.CapacityTypeSpot))
		calls := readStubCalls(stubLog)
		Expect(calls).To(HaveLen(2))
		// The scheduler orders pods itself, so take the zone the first round actually chose (the stub picks the first
		// candidate). The second round only offers other zones.
		firstRoundZone := calls[0].Allowed[0].AvailabilityZone
		Expect([]string{first.Labels[corev1.LabelTopologyZone], second.Labels[corev1.LabelTopologyZone]}).To(ContainElement(firstRoundZone))
		for _, a := range calls[1].Allowed {
			Expect(a.AvailabilityZone).ToNot(Equal(firstRoundZone))
		}
	})

	It("should keep topology spread within zones that have spot offerings", func() {
		// Spot only in test-zone-1; the other zones only offer on-demand
		cloudProvider.InstanceTypesForNodePool = map[string][]*cloudprovider.InstanceType{
			"kubepacs": {fake.NewInstanceType("spot-zone-1-instance-type", fake.WithOfferings(
				cloudprovider.Offering{Available: true, Requirements: pscheduling.NewLabelRequirements(map[string]string{v1.CapacityTypeLabelKey: v1.CapacityTypeSpot, corev1.LabelTopologyZone: "test-zone-1"}), Price: 1},
				cloudprovider.Offering{Available: true, Requirements: pscheduling.NewLabelRequirements(map[string]string{v1.CapacityTypeLabelKey: v1.CapacityTypeOnDemand, corev1.LabelTopologyZone: "test-zone-2"}), Price: 2},
				cloudprovider.Offering{Available: true, Requirements: pscheduling.NewLabelRequirements(map[string]string{v1.CapacityTypeLabelKey: v1.CapacityTypeOnDemand, corev1.LabelTopologyZone: "test-zone-3"}), Price: 2},
			))},
		}
		ExpectApplied(ctx, env.Client, kubepacsNodePool("kubepacs", nil))
		labels := map[string]string{"app": "web"}
		pod := kubepacsPod(nil)
		pod.Labels = labels
		pod.Spec.TopologySpreadConstraints = []corev1.TopologySpreadConstraint{{
			MaxSkew:           1,
			TopologyKey:       corev1.LabelTopologyZone,
			WhenUnsatisfiable: corev1.DoNotSchedule,
			LabelSelector:     &metav1.LabelSelector{MatchLabels: labels},
		}}
		ExpectProvisioned(ctx, env.Client, cluster, cloudProvider, prov, pod)

		Expect(readStubCalls(stubLog)).To(HaveLen(1))
		node := ExpectScheduled(ctx, env.Client, pod)
		Expect(node.Labels).To(HaveKeyWithValue(corev1.LabelTopologyZone, "test-zone-1"))
		Expect(node.Labels).To(HaveKeyWithValue(v1.CapacityTypeLabelKey, v1.CapacityTypeSpot))
	})

	It("should exclude pools running in the same NodePool only", func() {
		webTaint := &corev1.Taint{Key: "workload", Value: "web", Effect: corev1.TaintEffectNoSchedule}
		otherTaint := &corev1.Taint{Key: "workload", Value: "other", Effect: corev1.TaintEffectNoSchedule}
		ExpectApplied(ctx, env.Client, kubepacsNodePool("web-spot", webTaint), kubepacsNodePool("other-spot", otherTaint))
		labels := map[string]string{"app": "web"}
		antiAffinity := []corev1.PodAffinityTerm{{
			TopologyKey:   corev1.LabelHostname,
			LabelSelector: &metav1.LabelSelector{MatchLabels: labels},
		}}

		// First web node: the solver picks the first candidate (pool beta)
		first := kubepacsPod(webTaint)
		first.Labels = labels
		ExpectProvisioned(ctx, env.Client, cluster, cloudProvider, prov, first)
		node := ExpectScheduled(ctx, env.Client, first)
		beta := [2]string{node.Labels[corev1.LabelInstanceTypeStable], node.Labels[corev1.LabelTopologyZone]}

		// Second web pod cannot share the node, so a new node is selected: beta is not a candidate in web-spot
		second := test.UnschedulablePod(test.PodOptions{
			ObjectMeta:          metav1.ObjectMeta{Labels: labels},
			PodAntiRequirements: antiAffinity,
			Tolerations:         []corev1.Toleration{{Key: webTaint.Key, Operator: corev1.TolerationOpEqual, Value: webTaint.Value, Effect: webTaint.Effect}},
			ResourceRequirements: corev1.ResourceRequirements{
				Requests: corev1.ResourceList{corev1.ResourceCPU: resource.MustParse("1"), corev1.ResourceMemory: resource.MustParse("512Mi")},
			},
		})
		ExpectProvisioned(ctx, env.Client, cluster, cloudProvider, prov, second)
		secondNode := ExpectScheduled(ctx, env.Client, second)
		Expect([2]string{secondNode.Labels[corev1.LabelInstanceTypeStable], secondNode.Labels[corev1.LabelTopologyZone]}).ToNot(Equal(beta))

		// Another KubePACS NodePool may still pick beta
		other := kubepacsPod(otherTaint)
		ExpectProvisioned(ctx, env.Client, cluster, cloudProvider, prov, other)

		calls := readStubCalls(stubLog)
		Expect(calls).To(HaveLen(3))
		Expect(calls[0].allows(beta[0], beta[1])).To(BeTrue())
		Expect(calls[1].allows(beta[0], beta[1])).To(BeFalse())
		Expect(calls[2].allows(beta[0], beta[1])).To(BeTrue())
	})

	It("should hand pods the solver could not place to the default scheduler", func() {
		GinkgoT().Setenv("KUBEPACS_STUB_MODE", "bogus")
		ExpectApplied(ctx, env.Client, kubepacsNodePool("kubepacs", nil))
		pod := kubepacsPod(nil)
		ExpectProvisioned(ctx, env.Client, cluster, cloudProvider, prov, pod)

		Expect(readStubCalls(stubLog)).To(HaveLen(1))
		node := ExpectScheduled(ctx, env.Client, pod)
		Expect(node.Labels).To(HaveKeyWithValue(v1.NodePoolLabelKey, "kubepacs"))
	})

	It("should schedule regular NodePool pods in the same round as KubePACS pods", func() {
		wsTaint := &corev1.Taint{Key: "workload", Value: "workspaces", Effect: corev1.TaintEffectNoSchedule}
		ExpectApplied(ctx, env.Client, kubepacsNodePool("workspaces-spot", wsTaint), test.NodePool(v1.NodePool{ObjectMeta: metav1.ObjectMeta{Name: "regular"}}))
		kubepacs := kubepacsPod(wsTaint)
		kubepacs.Spec.NodeSelector = map[string]string{v1.NodePoolLabelKey: "workspaces-spot"}
		regular := kubepacsPod(nil)
		ExpectProvisioned(ctx, env.Client, cluster, cloudProvider, prov, kubepacs, regular)

		Expect(readStubCalls(stubLog)).To(HaveLen(1))
		Expect(ExpectScheduled(ctx, env.Client, kubepacs).Labels).To(HaveKeyWithValue(v1.NodePoolLabelKey, "workspaces-spot"))
		Expect(ExpectScheduled(ctx, env.Client, regular).Labels).To(HaveKeyWithValue(v1.NodePoolLabelKey, "regular"))
	})
})
