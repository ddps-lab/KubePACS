# KubeCAPS: Kubernetes Cluster Using Cost-Efficient, Highly Available, and Performative Spot Instances

## How to deploy

- You need change the contents of variables.tf, .env file.
- Run the command below:

    ```bash
    terraform init
    terraform apply --auto-approve
    ```

## Git subtree

```bash
git fetch lithops-upstream
git subtree pull --prefix=lithops lithops-upstream/master --squash -m "Update lithops"
```
