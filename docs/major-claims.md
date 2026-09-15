### Major Claims of the Paper

KubePACS is a Kubernetes-native spot-instance provisioning system that jointly considers hardware performance, cost, and multi-node availability. The artifact supports examination of the following claims through the supplied experimental results and local analysis scripts.

1. **Joint optimization improves performance per dollar.**
   By incorporating hardware performance, spot prices, and availability constraints into node selection, KubePACS improves cost efficiency over the evaluated provisioning baselines. The artifact provides benchmark inputs, stored evaluation results, and analysis scripts for Figures 1, 5, and 10.

2. **Multi-node availability information improves cluster-scale provisioning decisions.**
   Multi-node Spot Placement Scores provide a more informative basis for selecting capacity than single-node scores. Recorded provisioning outcomes and analysis scripts for Figures 2 and 9 support examination of the relationship between availability indicators and fulfilled requests.

3. **Adaptive optimization balances allocation efficiency and computational overhead.**
   KubePACS combines integer linear programming with Golden Section Search to select the weighting between cost and performance. Figures 6 and 7 characterize parameter sensitivity and execution overhead, while Table 2 compares adaptive optimization with fixed-weight and greedy configurations. The artifact includes stored results and scripts for generating these comparisons, together with the optimizer implementation.

4. **Workload-aware selection accommodates specialized hardware requirements.**
   Performance-score scaling allows node selection to reflect network- and disk-intensive workload preferences. The stored evaluation results and plotting script for Figure 8 show how these preferences affect the selected instance categories.

5. **Performance-aware provisioning improves application-level efficiency.**
   The paper evaluates the effect of instance selection on infrastructure efficiency and application performance. Stored results and generation scripts for Figures 10 and 11 and Table 3 support analysis of infrastructure cost, instance performance, graph-analytics execution time, and compute-service throughput.

To minimize evaluation cost and setup effort, the evaluation workflow generates the figures and tables locally from the supplied experimental results. A local optimizer check uses stored price, availability, hardware, and benchmark inputs to generate instance recommendations for ten scenarios across four AWS regions with different pod requirements. It checks that the resulting allocations provide sufficient pod capacity and respect the stored availability limits, and recomputes capacity and cost from the regional inputs. Kubernetes integration sources are also included.
