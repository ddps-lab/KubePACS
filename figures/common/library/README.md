# Optimizer And Profiling Utilities

The [local optimizer evaluation](../../../optimizer/README.md) has its own
environment, scenario runner, and regional inputs in the top-level
`optimizer/` directory.

`alpha_ILP_library_v4.py` provides the shared optimizer implementation.
The standalone evaluator reuses `getGoldenNodepool` without changing its
optimization logic. The merged CSVs here preserve historical inputs used
during the original experiments.

`getGoldenNodepool` reads its merged input and looks for
`<region>_az_mapping.json` in its working directory. The standalone evaluator
uses `optimizer/data/` and requires complete local inputs before execution.

`profile_runner.py` downloads live price and metadata inputs and performs
repeated optimizer runs. It is not needed for the local evaluator or
[figure generation](../../README.md).

The [API documentation](../../../api/README.md) describes the separate
Lambda handler interface.
