# KubePACS Helm Repository

This directory is a static Helm repository.

```sh
helm repo add kubepacs https://ddps-lab.github.io/KubePACS/charts
helm repo update
helm search repo kubepacs
```

`index.yaml` is generated with:

```sh
helm repo index charts --url https://ddps-lab.github.io/KubePACS/charts
```
