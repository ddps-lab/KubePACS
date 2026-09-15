# Artifact Appendix

`artifact-appendix.tex` is the submission appendix, using the ACM `acmart`
class and the author information from the paper. `artifact_appendix.pdf`
is the compiled document.

Build from the repository root with a TeX installation containing `acmart`
and `latexmk`:

```sh
mkdir -p /tmp/kubepacs-appendix-build
latexmk -pdf -interaction=nonstopmode -halt-on-error \
  -outdir=/tmp/kubepacs-appendix-build docs/artifact-appendix.tex
cp /tmp/kubepacs-appendix-build/artifact-appendix.pdf docs/artifact_appendix.pdf
```

Build intermediates stay outside the repository. The appendix does not include
local audit records, cloud account details, or Terraform state.

Evaluation covers local optimizer checks and figure and table generation
from supplied results. `major-claims.md` contains the
corresponding submission text.
