# Timing qualification evidence

This tree contains frozen reports, metrics, scripts and experiment manifests
for the revisions/dates named by their directories. Failed trial results and
old status summaries are retained as evidence, not current release guidance.
Some local build paths are machine-specific and generated files may require the
original tool/PDK environment.

Use [project status](../project_status.md), [final LVS closure](../timing_lvs_closure_20261029.md)
and [coverage audit](../timing_coverage_audit_20261029.md) for the qualified build.
The dated documents one directory above explain individual experiments.

The latest locally qualified physical successor is the
[November 4 headroom repair](../timing_headroom_20261104.md), with its
[active receipt](20261104-headroom/activation.json) and
[compact evidence index](20261104-headroom/campaign/evidence_sha256.json).
The October 31 receipt remains the historical immediate parent. Verify the
current active implementation with `tools/timing/headroom_release.py`; the
report provides the complete command and qualification scope.
