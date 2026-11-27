# WSL Host Bridge

Windows T3 Code Desktop can run two backends at once: the native Windows one
(primary) and one inside a WSL distro. The WSL Host Bridge lets agents in the
WSL backend hand work that needs Windows (a browser, Computer Use, GUI apps,
PowerShell) to the Windows backend on the same machine, through T3's own
Linked environments. Projects stay on WSL's ext4 disk; only delegated tasks run
on Windows, under the Windows worker's own permissions, sign-ins and approvals.

It is patches 0009 (helper, link path, Desktop supervisor) and 0010 (the controls on the Environments map and in Connections), built and installed like the others.

## Why a bridge is needed

A WSL backend links to another environment with `PeerLinks.link`
(`apps/server/src/peer/PeerLinks.ts`). The address it links through must
answer as the target environment and, over plain http, must be loopback or a
Tailscale address (`peerOrigin`). Under WSL's default NAT networking:

- WSL's `127.0.0.1` is the WSL VM, not Windows; Windows' loopback is unreachable.
- The Windows host's NAT gateway address is plain http on a LAN-classified
  address, which `peerOrigin` rightly refuses: a link's pairing code and token
  would cross a network. It also only answers when the Windows backend is
  network-accessible (bound to `0.0.0.0`).
- Picking a machine on the Environments map passes `expectedEnvironmentId`,
  and that path (`answeringAs`) refuses loopback on purpose: anything on the
  machine can answer there.

So the bridge gives the WSL backend a loopback address that is guaranteed to
reach this Desktop's own Windows backend, and a link path that accepts that
address only together with the Windows environment ID the Desktop runs.

## Inventory: what existed

| Piece | Where | Used for |
| --- | --- | --- |
| Patch framework | `patches/`, `t3code-customize` | Builds the Windows app and its WSL runtime from the same patches. This feature is two more patches. |
| Backend pool | `apps/desktop/src/backend/DesktopBackendPool.ts` | Primary (Windows) and `wsl:<distro>` instances, their ports, configs, readiness. |
| WSL backend | `apps/desktop/src/wsl/DesktopWslBackend.ts`, `DesktopBackendConfiguration.ts` | Spawns `wsl.exe -d <distro> --cd ~ --exec env … <runtimeDir>/t3 --bootstrap-fd 0`. The runtime is a Node single executable with the full CLI. |
| Hidden CLI helpers | `apps/server/src/bin.ts` (`__process-launcher`, `__service-launcher`) | Pattern for a small helper inside the same `t3` binary. |
| Native links | `PeerLinks`, `peer_environment_links`, server secret store | The link itself, its token, `resolve()` re-checking identity and capabilities before every use, expiry renewal. |
| Pairing codes | `POST /api/auth/pairing-token` with `purpose: "peer-link"` | What the Environments UI mints on the target before linking. |
| GUI linking | `LinkedEnvironmentsSettings.tsx` (`LinkEnvironmentDialog`) | Mint a code on the target, call `peerLinks.link` on the source. |
| Delegation | `delegate_task` → `RemoteDelegation`, `t3_environment_links`, `orchestrator_capabilities` forwarded | Unchanged; works over any link. |

Missing extension points: Desktop had no auxiliary long-lived process inside
WSL, no way to reach Windows loopback from WSL, no push of backend changes, and
did not know its backends' environment IDs. No plugin API exists in T3 Code;
the patches are the extension mechanism.

| Approach | Cost | Verdict |
| --- | --- | --- |
| Independent helper outside T3 (a service or script that relays) | Needs its own lifecycle and a Windows runtime (Windows has no Node here), cannot read the Desktop's backend pool, and still needs a link path that accepts loopback. | Rejected. |
| Minimal upstream patch (this) | About 1,000 lines of code plus tests, in four places: the helper in the `t3` binary, the link path, the Desktop supervisor and its controls on the map and in Connections. It is re-ported with the other patches on each T3 update. | Chosen. |
| A plugin interface in T3 Desktop for backend lifecycle hooks | It would be the cleanest, but it does not exist upstream; adding one is a far larger patch with the same porting cost. | Not available. |

## Architecture

```text
 WSL distro (one VM, shared loopback)          Windows (same user session)
 ┌──────────────────────────────────┐          ┌────────────────────────────────────┐
 │ WSL T3 backend                   │          │ T3 Desktop main process            │
 │  PeerLinks.resolve()             │          │  DesktopHostBridge supervisor      │
 │   GET/POST http://127.0.0.1:B    │          │   ├─ reads pool: Windows port,     │
 │            │                     │          │   │  WSL distro/runtime, readiness │
 │            ▼                     │  stdio   │   ├─ spawns + restarts helper      │
 │ t3 __host-bridge  (helper)  ◀════╪══════════╪═▶ └─ per stream: net.connect       │
 │  listens 127.0.0.1:B only        │ wsl.exe  │        127.0.0.1:<Windows port>    │
 │  frames streams over stdio       │  pipes   │                 │                  │
 └──────────────────────────────────┘          │                 ▼                  │
                                               │ Windows T3 backend (primary)       │
                                               └────────────────────────────────────┘
```

1. **Helper** (`t3 __host-bridge`, in the WSL runtime). Binds the first free
   port of a fixed candidate list on `127.0.0.1` only, reports it, and turns
   every accepted TCP connection into a stream on its stdio. It has no
   destination: it cannot open anything itself. It exits when its stdin ends,
   so it never outlives the Desktop that started it.
2. **Desktop supervisor** (`DesktopHostBridge`). Starts the helper with the same
   `wsl.exe` invocation the WSL backend uses, once both backends are ready, and
   connects each stream to **its own** Windows backend on Windows `127.0.0.1`,
   reading the port at connect time. It restarts the helper with exponential
   backoff, restarts it on resume and when the WSL instance or runtime changes,
   and pauses it when the Windows environment ID differs from the one paired.
3. **Stream framing** (`packages/shared/src/hostBridge`). Open, data, end,
   close and credit frames, with per-stream flow control, so one busy stream
   (a websocket, a large upload) cannot stall the others. TCP bytes pass
   through untouched; HTTP, websockets and streaming responses all work.
4. **Native link**. The Environments UI mints a peer-link pairing code on the
   Windows backend and asks the WSL backend to link to
   `http://127.0.0.1:B` (plus the other candidate ports as alternates) with
   `expectedEnvironmentId` set to the Windows backend's ID and
   `sameHostBridge: true`. That link path accepts only loopback addresses and
   only sends the pairing code after the address answered as that exact ID.
   Everything after linking is stock: token in the secret store, row in
   `peer_environment_links`, `resolve()` re-checking identity on every use.
5. **GUI**. The Environments map draws the bridge as its own kind of link
   from WSL to Windows: a violet line, wider than a native link, labeled
   **Host bridge** with its state on the edge (dashed while pairing, dotted
   and fainter when paused or off, red on an error). It is drawn whenever the
   Desktop offers the bridge, also while it is off, so it can be found and
   turned on there; until it is linked it counts as no link. Selecting the edge, the WSL node or the
   Windows node shows the bridge's controls in the details panel; dragging WSL
   onto Windows opens them instead of the ordinary link flow. Settings →
   Connections has the same controls as a compact row, for the list view and
   search. Both combine the Desktop transport state with the WSL backend's
   native link list.

### Why not the alternatives

| Option | Verdict |
| --- | --- |
| Link to the NAT gateway address | Refused by design (plain http across a network), needs the Windows backend on `0.0.0.0`, and the gateway changes. |
| Relax `peerOrigin` / `answeringAs` for private addresses | Weakens every link's security to fix one case. Rejected. |
| `socat` in WSL to the gateway | Manual, unencrypted NAT leg, Windows must listen on the LAN, gateway and port hard to follow, no lifecycle. Kept only as a manual diagnostic. |
| systemd user unit in WSL | Starts without knowing whether Desktop or the Windows backend runs, cannot reach Windows loopback anyway. Not needed: Desktop already supervises WSL processes. |
| Windows-side helper started from WSL via interop | Would need a Windows runtime (Windows has no Node for it) and a second supervisor. |
| Desktop-supervised stdio relay (chosen) | No network leg, no Windows listener on the LAN, lifecycle tied to Desktop, destination fixed. |

## Trust boundaries

- **WSL loopback leg (helper ↔ WSL backend).** Any process in any distro of
  this WSL VM can connect to `127.0.0.1:B`. That is the same reach a WSL
  process has to the Windows backend's unauthenticated surface through a
  network-accessible Windows backend today. It grants nothing by itself: every
  Windows API except the environment descriptor and the OAuth/pairing endpoints
  needs a bearer token, and the bridge adds none. A process that squats
  `127.0.0.1:B` before the helper could answer as the Windows environment and
  receive the link's token on `resolve()`; such a process already runs as a
  user of the same VM. The helper binds the first free candidate port, and the
  UI shows which one, so a squatter shows up as a moved port.
- **stdio leg (helper ↔ Desktop).** In-memory pipes through `wsl.exe` and the
  Hyper-V socket WSL uses for its own console; it never touches a network
  interface. Not encrypted; it does not need to be.
- **Windows loopback leg (Desktop ↔ Windows backend).** `127.0.0.1` on Windows.
  The Windows backend may stay **local-only**; the bridge does not need network
  access. The Windows backend sees bridged requests as loopback connections;
  T3 uses the client address only for display, not for authorization
  (`auth/utils.ts deriveAuthClientMetadata`).
- **Destination.** Fixed to the Desktop's primary backend. The helper protocol
  has no address field, agents cannot change it, and it is not a proxy.
- **Same machine, not same name.** The Windows endpoint is the Desktop's own
  primary backend and the expected ID comes from that backend's descriptor,
  never from a hostname or OS label, so two environments with the same
  hostname, or another machine with the same label, cannot be mistaken for it.
  A link to another physical machine is never shown as the bridge: the controls
  count only links whose addresses are the bridge's loopback addresses and
  whose environment ID is the Desktop's Windows backend.
- **Under mirrored networking** WSL and Windows share loopback. The bridge
  still works (the candidate port must be free on both), and a Windows process
  connecting to `127.0.0.1:B` reaches only the same Windows backend it could
  reach directly.

## Link lifecycle and authorization

| Situation | What happens |
| --- | --- |
| First enable | User clicks **Enable and pair** with an access level. The app turns the bridge on, waits up to 60 s for the helper to listen, mints a pairing code on Windows and links from WSL. That click is the approval. |
| Already linked (valid) | Nothing is paired again. The map and Connections show the native link. |
| Expired (30 days unused) | **Pairing required**; the user clicks **Pair again**. |
| Credential rejected (revoked on Windows, `capability_denied`) | **Permission denied**; never re-paired automatically. |
| Link removed elsewhere (CLI, Linked environments, agent) | **Pairing required**; never re-paired automatically. |
| User clicks **Revoke** | Native unlink (ends the session on Windows too) and the bridge is disabled. |
| User clicks **Disable** | Helper stopped; link kept, so enabling again needs no pairing. |
| Windows environment ID changes | Helper paused, **Identity mismatch**; the user confirms re-pairing to the new ID. |
| Change access | Re-pairs at the new level (a link's access is fixed when it is made). |

## States

`Disabled`, `Discovering` (backends or IDs not known yet), `Waiting for
Windows backend`, `Waiting for WSL backend`, `Bridge starting`, `Pairing
required`, `Connected`, `Recovering` (helper restarting, or link unreachable
while the helper runs), `Permission denied`, `Identity mismatch`,
`Unsupported` (WSL-only mode, not Windows, or a WSL runtime without the
bridge). Connected means the WSL backend's own link list reports the link
reachable with no error, not just that a TCP port answers.

## Enable progress and failures

Enable shows each step with a progress bar and the elapsed time: turning on
the bridge, starting the helper in WSL, helper listening (with its address),
getting a pairing code from Windows, checking Windows' identity through the
bridge and pairing, linked. Before the button is offered, the controls say
what blocks pairing: the WSL backend off or not connected, this computer's
Windows backend off or not connected in this app (the pairing code is minted
through that connection), Linked environments off on either side, or a WSL
runtime without the bridge. A backend whose settings the app cannot read, such
as a Windows backend turned off in the app, is never reported as having Linked
environments off.

A failure names the step, the reason and a next step, for example "The WSL
backend is not running" or "Something else answered on the bridge port, not
this Windows backend". The app also sends it to the Desktop, which keeps it as
the bridge's **Last error** in diagnostics, also after the bridge is turned
off. The pairing code is never part of it.

The first real-machine run failed silently: the Desktop's traces showed only
state polls and no call to turn the bridge on. The card's Enable went straight
to pairing while the bridge was still off, so the helper never started, and
the failure stayed in the card, leaving Last error empty. Enable now turns the
bridge on first and waits for the helper; every failure reaches Last error.

## Lifecycle

- Desktop start: the supervisor starts with the app and waits for both backends.
- Windows backend restart or port change: streams connect to the current port.
- WSL backend restart, `wsl --shutdown`, distro or runtime change: the helper
  exits with `wsl.exe` and is restarted once the WSL backend is ready again.
- Sleep/resume: restart on resume, backoff reset.
- Crash loops: backoff 1 s doubling to 60 s, reset after 2 minutes up.
- Duplicates: one supervisor per Desktop; the helper binds exclusively; a stale
  helper loses its stdin and exits.
- Shutdown and uninstall: the helper ends with Desktop. Uninstalling the
  customization removes the code; the native link stays in T3 until revoked
  (Revoke on the map or in Connections, `t3 environment unlink`, or Windows' Sharing & access).

## Agents

Once linked, a WSL agent sees the Windows environment in
`t3_environment_links`, reads its providers and models with
`orchestrator_capabilities` on that environment, and runs work there with
`delegate_task` (target `environmentId` = the Windows ID) or
`t3_thread_launch`. A Windows-only project such as `desktop-ops` keeps the
Windows worker away from the WSL repository. Transparent forwarding of Windows
tools into a WSL model session is a separate, later feature.

## Compatibility

- Needs both the Windows server and the WSL runtime from this build: the link
  path and the helper are in the patched server. A stock WSL runtime lacks the
  `hostBridgeLinks` capability and the controls say so instead of failing.
- The link is a stock T3 link. If the customization is removed or T3 updates
  before the patches are ported, the link stays in place but is unreachable
  (no helper); after the next build the helper returns and the link works again
  without pairing.
- Linked environments (Settings → Labs) must be on for both backends.

## Install, update, uninstall

- **Install:** build as usual from WSL, `python3 ./t3code-customize build --target windows`. Both
  patches go into the Windows app and its WSL runtime. Open **T3 Code (Customized)**.
- **Turn on:** Settings → Labs → Linked environments must be on for both the Windows and the WSL
  environment. Then select the **Host bridge** link (or the WSL node) on Settings → Connections →
  Environments map, or use **Local host bridge** in the list view: pick the access level and click
  **Enable and pair**. The app turns the bridge on, mints a pairing code on Windows and links WSL to
  it, showing each step; you never type a code.
- **Update:** after a T3 update, run `t3code-customize` again. Until then the launcher opens
  stock, the helper does not run and the link shows as unreachable; it is not removed, and works
  again without pairing once the customized build is back. Stock rewrites `desktop-settings.json`
  without the bridge's keys, so after using stock, enable the bridge again (no pairing needed).
- **Turn off:** **Disable** stops the helper and keeps the link. **Revoke** unlinks natively (the
  Windows side ends the session too) and turns the bridge off.
- **Uninstall:** `t3code-customize uninstall` removes the customized build, so the helper never
  starts again. The link is an ordinary T3 link: revoke it first on the map or in Connections, or later with
  `t3 environment unlink <windows-environment-id>` in WSL, or from Windows' Settings → Sharing &
  access. Nothing else (Tailscale, other links, T3 Connect) is touched.

## Status and its limits

- **Connected** means the WSL backend's own link list reports the link reachable through the
  bridge with no recorded failure. The list checks the peer's identity, not its token; a token
  revoked on Windows shows as **Permission denied** after the next call through the link fails
  (`capability_denied`, recorded natively as the link's last error), not before.
- The map and Connections refresh the native list every 15 seconds while open; the Desktop state
  every 2 seconds, and every 0.5 seconds while Enable waits for the helper.
- The helper and the link use plain http over loopback and stdio. Nothing crosses a network
  interface; see the trust boundaries above.

## Acceptance tests

`F` = fixture test in `checks.json`; `R` = run for real on a Windows + WSL2 (NAT networking) machine
with the real Windows T3 backend; `U` = needs the user (a Desktop restart, a reboot, pairing
approval).

| Test | How | Status |
| --- | --- | --- |
| Helper listens on loopback only, first free port, refuses any destination argument | F `hostBridgeHelper.test.ts`; R | Passed |
| Framing: intact bytes both ways, half-close, concurrent streams, flow control, caps | F `hostBridgeMux.test.ts` | Passed |
| Windows process → `wsl.exe` stdio is binary-safe and passes EOF | R: 8 MB random round trip | Passed |
| Real path: WSL `127.0.0.1` → helper → `wsl.exe` → Windows relay → Windows backend | R: descriptor answers with the Windows environment ID; app shell and assets 200; OAuth register and resource metadata (`http://127.0.0.1:<port>/mcp`); 20 concurrent requests | Passed |
| Throughput and integrity over the real path | R: 64 MB echo each way intact (~119 MB/s combined); 16 × 2 MB concurrent intact | Passed |
| Bridged responses are byte-identical to direct ones | R: websocket upgrade without auth answers the same `426` both ways | Passed |
| Desktop crash leaves no orphan | R: Windows relay force-killed; helper exited in ~3 s, port freed | Passed |
| Bridge port taken by another process | F; R: helper moved to the next candidate port, or reported `ports_in_use` | Passed |
| Link only at loopback, only to the named environment; impostor never sees the code; existing link not re-paired | F `PeerLinks.test.ts` | Passed |
| Picked-machine loopback refusal unchanged | F `PeerLinks.test.ts` | Passed |
| Supervisor: waits for Windows, then WSL; backs off; restarts after WSL comes back; stops when disabled; pauses on identity change; helper outlives the IPC call | F `DesktopHostBridge.test.ts` | Passed |
| Card states, including same hostname on both sides and links to other machines | F `LocalHostBridge.logic.test.ts` | Passed |
| Enable turns the bridge on before pairing, waits for the helper, links with the exact input; each failure (helper never listening, Linked environments off, impostor, refused) has a reason and reaches Last error, also once off | F `hostBridge.test.ts`, `LocalHostBridge.logic.test.ts`, `DesktopHostBridge.test.ts` | Passed |
| Map: the bridge is its own link kind, a link to another Windows ID shows as an identity mismatch, a pending edge appears while enabling, no "link back" offer and not counted as a two-way link | F `environmentsMap.logic.test.ts` | Passed |
| Shipped helper answers as the Windows environment through a Windows relay, on the real machine, without restarting the Desktop | R | Passed |
| First enable and user approval in the real Desktop | U | Pending |
| CLI (`t3 environment list --json` in WSL), map and agent (`t3_environment_links`) agree | U | Pending |
| WSL agent delegates to a Windows worker, which reports Windows OS, its environment ID and tools | U | Pending |
| Harmless Windows Browser or Computer Use task | U | Pending |
| Restart T3 Desktop: no new pairing | U | Pending |
| `wsl --shutdown`, start T3: recovers | U | Pending |
| Windows reboot and sign-in: recovers | U | Pending |
| NAT gateway changes | By design: never used (stdio, not the network) | n/a |
| Windows backend port changes | F (port read per stream); U | Pending in the real Desktop |
| Windows backend temporarily down | F (waits, recovers); U | Pending in the real Desktop |
| User revokes; plugin never re-pairs | F (nothing pairs without a click); U | Pending in the real Desktop |
| T3 Connect registrations added | By design: none (no Connect calls) | n/a |

