# Packaged Helm Repository

This directory contains the Helm repository index and packaged releases.
For evaluation of the submitted source, use the local chart and instructions
in [Karpenter](../KubePACS_with_Karpenter/README.md). A hosted archive or mutable
image tag may differ from the current checkout.

The optional hosted repository can be inspected with:

```sh
helm repo add kubepacs https://helm.kubepacs.ddps.cloud/charts
helm repo update
helm search repo kubepacs --versions
```

These commands do not deploy a cluster. Record the chosen chart version,
archive checksum, source revision, and controller image digest when using
a packaged release.

## Maintainer Packaging

From the repository root, after validating the local chart:

```sh
helm lint KubePACS_with_Karpenter/karpenter-provider-aws/charts/karpenter
helm package KubePACS_with_Karpenter/karpenter-provider-aws/charts/karpenter --destination charts
helm repo index charts --url https://helm.kubepacs.ddps.cloud/charts
```

Packaging updates repository artifacts; it is not required for figure
reproduction. Publication is maintained by
[the Helm workflow](../.github/workflows/publish-kubepacs-helm.yaml).
A successful package/index operation does not verify live provisioning.
