# Optimizer And Profiling Utilities

These utilities are separate from the [figure workflow](../../README.md).
The plotting scripts do not execute them.

`alpha_ILP_library_v4.py` provides optimizer functions. Its merged input CSVs
contain instance type, AZ ID, vCPU, memory, availability metrics, prices, and
CoreMark. Six preserved `merged_coremark_spotdata_260221_*.csv` files are
included for inspecting/reusing the historical optimizer inputs. They are not
the Figure 1 price inputs and do not contain all newer instance families.

`getGoldenNodepool(file_path, ...)` reads a merged CSV but still queries AWS
for account-specific AZ names. A cached CSV therefore does not make this
utility an offline workflow. Region must match the supplied CSV. Additional
dependencies beyond the plotting environment include PuLP and requests;
`profile_runner.py` also needs psutil. CBC must be available through PuLP.

`profile_runner.py` downloads live price/metadata inputs and performs repeated
optimizer runs across regions, writing timestamped merged inputs and profiling
reports into its working directory. It is not a replay command for the stored
profiling measurements. Do not run it to regenerate the figures, and do not
treat new timings as exact reproductions of historical timings.

For a documented optimizer response check, use the
[API workflow](../../../api/README.md). A fully pinned, validated historical
profiling rerun procedure remains outside the current figure reproduction path.
