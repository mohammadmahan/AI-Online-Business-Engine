# Vendoring provenance

This directory is a VENDORED copy of the upstream design-skill repository.
Its nested `.git` directory was removed deliberately so the skill content is
tracked as ordinary files in this repository (owner decision, 2026-10-04):
every clone/materialization of this repo then carries the design skill offline,
with no network or `--recurse-submodules` requirement.

- Upstream: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
- Pinned commit: `09170eec67eefd46a7ae85de61b40c194020f997`
  (`main`, 2026-09-27 — “Merge pull request #500 from
  alinultimatltd/fix/light-result-output-coherence”)
- Working tree at vendoring time: clean (`git status` empty).
- Local changes: none beyond this file.

To refresh from upstream, clone the URL above, check out the desired commit,
and copy the working tree over this directory — keeping this file.
