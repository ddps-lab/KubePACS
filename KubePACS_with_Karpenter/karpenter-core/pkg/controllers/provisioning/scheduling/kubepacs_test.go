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
	"sigs.k8s.io/karpenter/pkg/test"
	. "sigs.k8s.io/karpenter/pkg/test/expectations"
)

// stubSolver stands in for kubepacs_cli.py: it records every call and allocates all pods to the first allowed
// (instance type, zone) offering. KUBEPACS_STUB_FAIL=1 makes it exit non-zero to exercise the fallback path.
const stubSolver = `#!/usr/bin/env python3
import json, os, sys
allowed = json.load(sys.stdin)
with open(os.environ["KUBEPACS_STUB_LOG"], "a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "allowed": allowed}) + "\n")
if os.environ.get("KUBEPACS_STUB_FAIL") == "1":
    sys.exit(1)
count = int(sys.argv[sys.argv.index("--pod-count") + 1])
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
		GinkgoT().Setenv("KUBEPACS_STUB_FAIL", "0")
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
		GinkgoT().Setenv("KUBEPACS_STUB_FAIL", "1")
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
})
