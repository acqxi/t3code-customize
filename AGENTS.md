# Porting the patches to a new T3 Code nightly

These instructions are for a coding agent. A person can follow them too.

Each supported T3 Code release has its own patch set in `patches/<version>/`: the
patches, `base.txt` (the upstream commit they were made against) and `checks.json`.
Only the newest set is in the tree; older sets are frozen in tags named
`patches-<version>`, which the tool reads when an install needs them. It picks the set
made for the installed commit, or the closest older one to port from. Upstream moves fast, so a new release often needs a port. Your job is to carry the
patches onto the user's release with every feature still working.

## Start

1. Run `python t3code-customize build` from this repo on Windows, or
   `python3 ./t3code-customize build` on Linux and macOS. It finds the installed
   application (AppImage, macOS app or Windows executable), reads its exact upstream
   commit, and applies the patches in the private source checkout. Use `--app` for a
   nonstandard installed path. The source checkout is `<cache>/t3code`; platform cache
   locations are in [README.md](README.md#good-to-know), and the build prints its log path.
2. If it reports a conflict, a rebase is stopped in that checkout. If it reports a
   failing test or typecheck, the commits are in place and the checks failed.

## Fix

Work only in that private source checkout and this repo.

- Conflicts: resolve each file, `git add` it, then `git -c core.editor=true rebase --continue`.
  Keep upstream's change and port the patch on top of it. When upstream moved or split
  a file, carry the change to the new location and follow the new APIs.
- Failing checks: fix the relevant commit with `git commit --fixup=<sha>`, then
  `git -c sequence.editor=true rebase -i --autosquash <nightly commit>`. Keep one
  commit per patch.
- If a test file moved upstream, update its path in the set's `checks.json`.
- `git log <base>..<nightly commit>` and `git show` explain what changed upstream.
- To install dependencies, use exactly `pnpm install --frozen-lockfile --ignore-scripts`
  in the source checkout, the same as the tool.

Do not drop a patch, delete or weaken a test, or skip a check to get green. If a
feature can't be ported sensibly, stop and explain why.

## Finish

If `t3code-customize` started you, stop once the tests and typechecks in the set's `checks.json`
pass (run them from the source checkout with `node_modules/.bin/vp test run <files>` and
`node_modules/.bin/effect-tsgo tsrs --noEmit` inside each package directory; older bases used `tsc`). It continues the build itself.

Otherwise run the same Python entry with `build --resume`. It reruns the checks on the checkout as you
left it, builds, installs the result and writes the ported commits to a new set,
`patches/<installed version>/`, keeping the set it came from for older installs. Leave
the checkout clean with no rebase in progress. When the new set is committed, tag the
last commit that still has the previous set as `patches-<previous version>` and remove
that folder from the tree, so only the newest set stays.

End with a short report: what changed upstream, what you changed and in which files,
and whether the final build succeeded. Separate fixture tests, native process
checks and real desktop startup evidence.
