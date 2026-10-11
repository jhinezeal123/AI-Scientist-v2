# T3 Code provider setup UI in Workbench

Upstream: https://github.com/pingdotgg/t3code
Pinned commit: f0a47b3172c4a73e1932b23d37c3345481c5a67e (retrieved 2026-10-11).
License: MIT, Copyright (c) 2026 T3 Tools Inc. See LICENSE.

## Imported source

The actual upstream ProviderInstanceCard, ProviderSettingsForm,
ProviderModelsSection, CustomModelEditor and its validation logic,
ProviderAccentColorPicker, SettingsGroup, settingsLayout, providerStatus,
ProviderInstanceIcon, OpenAI/Claude artwork, modelOrdering, useCommitOnBlur,
AnimatedHeight, observeResize, color helpers and UI primitives are used here.
Primitives include Button, DraftInput, Input, Select, Switch, Textarea, Tooltip,
Popover, ColorPicker, Badge, Dialog, ScrollArea and Wizard.
The ACP Registry search step, ProviderSetupSection,
ProviderAuthenticationSection, RedactedSensitiveText, InputGroup and Alert are
also imported from this pinned revision. Browser, credentials and interactive
terminal setup retain T3's interaction contracts. The terminal renderer uses
Workbench's xterm/ConPTY integration instead of T3's Ghostty renderer.

`PresetSettings` reuses ProviderSettingsPanel's 17rem provider list, selected
editor, scroll areas and responsive layout. `T3AddProviderDialog` reuses the
upstream provider radio choices and Provider → Identity → Config wizard with
these imported controls. Workbench's additional agent/model pair editor uses
those same settings rows and primitives.

`source-manifest.json` records checksums of the pinned upstream files before
adaptation, including sources from which sections were extracted. It does not
claim byte equality of the integration files. Theme and contrast declarations
come from upstream index.css; `t3.input.css` and the CSS build script isolate the
reset, utilities and portals from Workbench's existing styles.

## Integration adaptations

- Imports point to local files. Small `bridge` contracts map the existing
  Workbench provider schema to the upstream UI; they contain no Slack, remote
  or project workflow policy.
- Workbench's authenticated API and SQLite store replace T3's Effect atoms,
  environment scope, authorization and secrets services. Fields commit on
  blur/Enter or selection, as in the upstream form. Sensitive environment
  values are hidden after saving, stored in the existing local control DB.
- Codex and Claude Code remain native drivers. Any number of named instances
  can be added. Other installed agents connect through ACP or CLI JSON.
  ACP Registry uses the same official catalog as T3 and exposes every catalog
  agent. Managed binary/npm/Python releases are installed explicitly from the
  UI, with update, cancellation and removal controls. Separate T3 remote
  environments and unrelated chat/editor features are outside this integration.
- Workbench adds a direct ACP Registry button above the configured providers.
  Registry selection collapses the provider choices so search and the catalog
  appear immediately, with a visible result count. Change provider reopens the
  original choices; the remaining Identity → Config steps use the same wizard.
- The T3 runtime icon animation is replaced with matching static lock icons.
  Unsupported provider artwork uses initials. The shared utility merger is
  adapted to class-variance-authority and tailwind-merge.
- Codex reads paginated `model/list` from its configured app-server profile;
  ACP reads session configuration metadata; Claude uses the pinned T3 model
  manifest filtered by installed CLI version. There is no inference turn.
  The bundled Claude manifest does not include T3's remote manifest updater.
- Preset model choice is a dropdown from the selected provider's catalog.
  Explicit custom models are managed in the upstream Models section. T3's
  favorites, visibility and ordering affect this dropdown and are saved in
  Workbench's provider configuration. Existing saved models remain visible if
  temporarily unavailable.
- Antigravity uses the official ACP runtime, per-instance Google sign-in and
  account-specific session models. An IDE/agy installation does not provide
  ACP sign-in. Google credentials stay in a private backend profile and survive
  refresh/restart; the browser sees flow state and masked settings only.
- Registry installation/authentication backend contracts are adapted to Python,
  not copied TypeScript server code. Provenance is recorded in
  `agent management/agent_management/vendor/t3code/provider-setup-source.json`.
  Setup has its own catalog, installer, cancellable operation state, profile
  store and API. Only the runtime coordinator is shared with project execution.

## Updating and verification

Compare against the official pinned source, retain the MIT notice and document
all adaptations. Run `npm run build`, `npm run test:features`, the backend preset
configuration/model catalog tests and feature boundary tests. Browser QA covers
adding a provider, reading models, saving a custom model/preset, refresh,
visibility, preferences and narrow viewports. Keep Workbench execution and
approval policy in the existing adapters and project workflow services.
