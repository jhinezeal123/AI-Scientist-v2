# T3 model catalog

`model-manifest.json` is the bundled upstream model manifest from
https://github.com/pingdotgg/t3code at
f0a47b3172c4a73e1932b23d37c3345481c5a67e, MIT © 2026 T3 Tools Inc.
See LICENSE and the frontend vendor source manifest for provenance/checksum.
Workbench reads the Claude catalog and filters models by installed CLI version.
Updating this pinned snapshot is explicit; T3 remote manifest updates are not enabled.

`acp-registry.json` is an offline snapshot of the official ACP Registry used
by T3. `acp-registry-source.json` records its URL, date and checksum. The live
registry is checked when requested; unavailable networking uses the cached or
bundled catalog. Provider install/auth contracts are adapted to Python, with
upstream source checksums in `provider-setup-source.json`. They include T3's
binary → npm → uv resolution and Antigravity private profile/browser contract.
