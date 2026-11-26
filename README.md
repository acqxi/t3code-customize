# t3code-customize

[English](README.md) | [繁體中文](README.zh-TW.md)

Your 5 hour and weekly usage, context and tokens per second, right under the T3 Code composer.

Unofficial. Not affiliated with T3 Tools. For T3 Code (Nightly, Beta or Release) on Linux (AppImage), macOS and Windows, including Windows Desktop with a WSL runtime.

## What you get

- **Usage meters** for your 5 hour and weekly limits, from the limits T3 already gets from your providers.
- **Context** used in the thread. Hover it for the window size, the auto-compaction threshold and a Compact now button.
- **Tokens per second** for the last response, with turn time and token details on hover.
- **Cache rate** for the last turn.
- **Performance metrics**: time to first token and to first answer, live, average and peak tokens/s, token and cache usage, tool time and turn time, plus the provider, model, effort and speed of each turn. The composer shows the current and previous turn, and each reply keeps its own line. Estimated values show `≈` and unavailable ones `—`; which metrics exist depends on the provider. Codex, Claude Code and ACP agents such as Antigravity are timed from their streams. See [docs/performance-metrics.md](docs/performance-metrics.md).
- **Subscription switch** when you have more than one signed-in subscription that offers your model. If the current one is on pace to run out before its 5 hour or weekly window resets, a chip like **Opus 5.5 on Personal →** switches the thread to the same model on the one with the most room. It also points out a subscription whose weekly allowance resets within a day mostly unused. Hover it for the reasoning.

The official app's native dependencies and public T3 Connect configuration are
reused. Windows signature changes and platform restrictions are described below.

## Install

Install T3 Code (Nightly, Beta or Release) first. You need Git, Python **3.10+**, an
internet connection and at least approximately **6 GB** of free space. The tool
uses the exact Node version upstream pins in `engines.node`; if your Node differs,
it downloads a private, checksum-verified copy for the host.
The first build takes approximately 5 to 15 minutes, depending on the machine.

### Windows (PowerShell)

Install Git for Windows and Python, with `git` and `python.exe` on PATH. Clone
this repository, then run Python directly; Git Bash and administrator access are not
required:

```powershell
git clone https://github.com/acqxi/t3code-customize.git
cd t3code-customize
python .\t3code-customize build
```

For a nonstandard installation location, pass the **installed executable**,
not the NSIS installer:

```powershell
python .\t3code-customize build --app 'C:\Apps\T3 Code\T3 Code (Nightly).exe'
```

Alternatively, run the checked-out `install.ps1`; it clones this repository into the
tool's private data directory and builds it. Use `-App` for an explicit executable
and `-Branch` when testing a feature branch. It does not change execution policy.

### Windows Desktop with a WSL runtime (no Windows Python/Git/Node needed)

If your Windows T3 Code runs its backend in WSL, run the tool **inside WSL**, with
Windows interop (`powershell.exe`) available. The JavaScript and the Linux runtime
are built in WSL; copies, hashes, the executable's integrity resource and the
Start menu shortcut go through Windows PowerShell:

```sh
git clone https://github.com/acqxi/t3code-customize.git
cd t3code-customize
python3 ./t3code-customize build --target windows
```

It finds the Windows install under your Windows `%LOCALAPPDATA%\Programs`
(pass `--app '/mnt/c/.../T3 Code (Beta).exe'` otherwise). WSL needs `git`,
`python3` and internet, on x64. The build copies your app to `%LOCALAPPDATA%\t3code-customize\builds`,
rebuilds `resources/wsl-runtime.tar.gz` and its `.sha256` from the same patches,
and adds **T3 Code (Customized)** to the Start menu. Your installed app and its
WSL runtime are not modified. On first launch the customized app installs its
runtime into its own `~/.t3/wsl-runtime/sha256-…` folder next to stock's.

Both apps share the same T3 profile (account, settings, projects, threads), so
quit stock fully before opening the customized one. `t3code-customize check`
reports, read-only, the runtime running in the current distro, your project and
thread counts, and the latest finished turn per provider; run it before and
after switching to compare.

### Linux and macOS

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/acqxi/t3code-customize/main/install.sh)"
```

Or clone this repository and run `python3 ./t3code-customize build`. AppImages in
`~/Applications`, `~/Downloads` and the other standard tool search directories
are discovered automatically. For other paths, pass
`--app /path/to/T3-Code.AppImage`. The old `--appimage` option still works.

### Enable the stats

After the build succeeds, **quit T3 Code fully**. Open **T3 Code (Customized)**
from the Windows Start menu, the Linux app launcher or Spotlight on macOS.
Enable **Settings > General > Stats for nerds**.

The customized app opens the normal T3 Code main screen; it does not show a
separate setup wizard. Open Settings manually and search for **Stats for nerds**
if you cannot find the switch. It is off by default. Once enabled, the stats
appear below the chat composer and under each reply; which values are available
depends on the provider and the conversation. The same settings section has a
switch for each metric and for each place it appears.

The command wrapper lives in `~/.local/bin` on Linux, or
`%LOCALAPPDATA%\t3code-customize\bin` on Windows. If it is not on PATH, add that
directory or use `python t3code-customize <command>` from the checkout
(`python3` on Linux).

On macOS, open **T3 Code (Customized)** from Spotlight, Launchpad or `~/Applications`. See the [macOS guide](docs/macos.md) for setup, day-to-day use and why it loads the patches into your app instead of rebuilding it. It looks for `T3 Code (Nightly).app` in `/Applications` and `~/Applications`; point it elsewhere once with `--app "/path/to/T3 Code (Nightly).app"`.

## After every T3 Code update

```sh
t3code-customize
```

Update the **official app** first, then run the tool. It pulls the latest patches,
rebuilds for your installed version and tells you when to reopen. Until you run
it, the launcher falls back to stock T3 Code. Windows customized copies
have automatic updates disabled; update stock from its original launcher.

## When a nightly breaks the patches

Upstream moves fast, and sometimes a nightly changes the code the patches touch. When that happens:

- If you have Claude Code or Codex installed, it offers to port the patches for you right there.
- Otherwise, wait for this repo to catch up, then run `t3code-customize` again.
- Or point any coding agent at this repo and ask it to follow [AGENTS.md](AGENTS.md).

Your current T3 Code keeps working the whole time.

## How it works

T3 Code is open source (MIT). This repo holds six feature patches and one script. The
script:

1. reads your installed application: its exact upstream commit and the public config T3 Connect needs,
2. applies the patches to that commit and runs their tests,
3. rebuilds the web, server and desktop JavaScript,
4. on Linux and Windows, lays it over a copy of your app, checking unchanged archive entries byte for byte,
5. on Windows, updates Electron's embedded archive integrity metadata in that copy,
6. built from WSL for Windows, also rebuilds the WSL runtime archive, keeping its native entries.

Windows builds with a `server.asar` sidecar have both archives patched. Linux uses the merged
`app.asar`. Native libraries and unpacked payloads are copied from the installed app, without
compiling replacement binaries.

On macOS nothing is copied or re-signed, so your app keeps its signature, keychain access, passkeys and updates. The launcher opens your own `T3 Code (Nightly).app` with a startup hook, loads the rebuilt bundles into it before any app code runs, and closes the hook again. Opening T3 Code any other way gives you stock.

Everything runs on your machine. Your installed app and your T3 data are never modified by the
build. The customized app uses the same T3 profile as stock; quit stock before switching.

## Commands

```
t3code-customize             update the patches and build for your installed T3 Code
t3code-customize status      show what the next launch opens
t3code-customize check       read-only: running runtime, your data counts, latest stats per provider
t3code-customize off | on    switch between stock and the customized build
t3code-customize uninstall   remove it, its launcher, builds and caches
```

## Good to know

- **Bugs:** before reporting anything to T3 Code, run `t3code-customize off`, reopen and check it happens on stock too. Report customization problems here.
- **macOS:** the customization applies when T3 Code starts from the launcher. If T3 Code is already running, the launcher just brings it forward. It relies on T3 Code allowing a startup hook (`--inspect-brk`); if a release turns that off, the build stops and says so.
- **Windows signatures:** updating embedded archive hashes changes the copied
  executable, so it no longer has the official Authenticode signature. This is
  a local customized copy, not a signed distributable installer.
- **Windows WSL environments:** built from WSL (`--target windows`), both the
  native Windows server and the embedded WSL runtime are patched. Built from
  Windows Python, only the native server is patched and the WSL runtime stays
  stock (a Linux single executable cannot be built there).
- **Architectures:** the private Node downloader supports x64 and arm64.
  Build on the same architecture as the installed app, and on the same platform,
  except Windows Desktop, which can also be built from WSL.
- **Files on Linux and macOS:** data/builds in `~/.local/share/t3code-customize`,
  source/logs in `~/.cache/t3code-customize`.
- **Files on Windows:** data/builds in `%LOCALAPPDATA%\t3code-customize`,
  source/logs in its `cache` subdirectory. Built from WSL, builds and launcher
  state are there too, while source, logs and config stay in WSL
  (`~/.cache/t3code-customize`, `~/.config/t3code-customize`) and the command is
  `~/.local/bin/t3code-customize`.

## Development checks

```sh
python -m unittest discover -s tests -v
python t3code-customize verify
```

Use `python3` on Linux. The first command tests layouts, split/merged
archives, update fallback, locks, command shims and integrity metadata with
fixtures. Windows also exercises the real PE resource API. The second command
applies all patches to their base and runs every test and typecheck in
`checks.json`; it downloads upstream sources and dependencies.

CI runs the platform tests on Linux, macOS and Windows, plus upstream patch
verification on Linux and macOS. Fixture tests are separate from real desktop startup
and provider integration checks.

## License

MIT, same as T3 Code.
