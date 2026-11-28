# Supported release distribution

State active. Requirement REL-03.

Inspect pyproject, Docker recipes, retained Hermes build context, host
certification fixtures and workflow dependency profiles. Have Pi and
OpenClaw install the exact same prebuilt base wheel. Do not publish the
unqualified optional profile. Preserve repository analyzer validation without
advertising an unsafe install. Remove editable Python and asset overrides
from exact-host image proof.

Build an isolated wheel and inspect metadata and supported resolved closures.
Verify import paths, immutable native assets, provider behavior and exact
host versions. Final qualification records actual scans, model custody,
SBOM, provenance and signature.

## Local implementation evidence

The wheel excludes the old optional local profile. PyTorch 2.15 is confined
to the repository test profile. Metadata resolution passed on Linux x86_64
Python 3.11 and macOS ARM64 Python 3.12. Base artifacts installed outside the
checkout on macOS and in Linux ARM64 Docker. BuildKit checked both recipes.
Static tooling passed 21 checks. Both native images then built and passed the
Pi/OpenClaw installed rehearsal using wheel
`969a1c6970c0fd05afa525ef604be1bdacdfc70d1d165d3c6fbeb5a852207474`.
Final closure still requires provider/Hermes, dependency scans across
supported artifacts, model verification, SBOM, provenance and signatures.

The original Pi 0.99.2 and OpenClaw 2026.9.7 journeys passed functionally.
Their installed closure audits reported two High packages for Pi and four
for OpenClaw. The owner approved new pins on 2026-11-27.

Pi 1.7.0 and OpenClaw 2026.11.10, both on Node 24.22.3 and npm 12.2.3,
passed the real Linux arm64 Docker journeys using committed runtime wheel
`4a07d3a6a9bf08a1195878ec4e03cb591dd488c40b8caddb4a82b5d3f27594d9`.
The respective image indexes were
`75bb6493eea4130ae8b6f2ab817a40812df914e2b59159e0ce5dfa16d8c2d40d` and
`46678f45f78e1b0feabd97f91cca166b9c6fe01f424f9573d78668ad9aa28203`.
Pi's installed application audit reported zero findings. OpenClaw's installed
application closure reported zero High or Critical and 16 Moderate entries.
The explicit compatible dependency overrides retain patched Undici and npm
bytes, including npm's bundled Undici. Global npm's separate closure reported
zero High or Critical entries.

The pinned OpenClaw prompt projection initially persisted recalled text.
The dedicated gateway profile selects Memorii as its context engine and
assembles quoted user-role recall for the current model request. It delegates
host compaction and binds recall to an exact eligible native pre-write and
run identity. The real host journey checks that the original transcript
persists, the recall marker is absent from native persistent state, and all
fresh provider requests after revocation and a second gateway restart omit
the marker. The SDK's separate deterministic test rejects a forwarded write
even when it overlaps an earlier admitted identity.

Application audit and functional certification are separate from the OS image
gate. Trivy 0.76.2 reported 493 High/Critical Debian findings and two High
Python setuptools findings on the Bookworm Pi image. The raw JSON digest is
`725ebaa57006e51756c0a28ca0ddb908c93ef8a0481ca5f36bedfff1de2fd380`.
The exact Pi image CycloneDX inventory digest is
`bdd14402a904a022cef3d628a904a618f1e5be9a10b2b751ee5cd203613f3b77`.
The newer slim multi-stage runtime is a separate image qualification attempt.

The promoted Debian 13 slim multi-stage recipes install the same hash-locked
Python runtime closure, remove build tooling, and install the common wheel
with `--no-deps` and `pip check`. Pi's real journey passed with Linux ARM64
manifest `00a8f39adb549e96dd4a244b1bc59b77e7b1498c7b66f4904e4f05ceb91c665d`.
OpenClaw's final journey used manifest
`c127fdd4d936035dde34508b50194e46c18348c44b6db356775b7eff63d36650` and recovered
capture and model recall after 17 unavailable turns without a gateway
restart. It then verified revocation, restart and persisted-history isolation.
Both used the same `4a07d3a6` runtime wheel.

The slim scans each reported zero Critical and zero Node or Python High
findings. They each reported 88 High Debian package findings across 27 unique
advisories and 32 packages. Trivy listed no Debian fixed versions. The
findings include the SQLite runtime. The owner approved shipping the wheel
and pinned native host assets with Docker reserved for validation on
2026-11-27. These images remain unsuitable for an approved v8 release image.
Shipped-asset scans and exact candidate provenance remain release gates.

The candidate builder now emits separate reproducible Pi and OpenClaw
tar archives with complete package locks. The manifest binds host versions,
archive and member digests, source revision and the common base wheel.
Container verification checks the installed wheel and copied host file
digests before exercise and retains the candidate archives on a passing job.
Both host journeys now run the installed foreground operator console.
A test-only loopback relay observes successful signed captures while the
operator process retains authorization, persistence and response ownership.

| Evidence | Pi SHA-256 | OpenClaw SHA-256 |
| --- | --- | --- |
| Trivy vulnerability JSON | `982d39b285a2ba6dec52e1e254cf887800c7bb5aeebcd85e611447e15bdecad9` | `ef145cfa199ef02e491f58403069dbd8abcf210059c846776921be4e06d3e40e` |
| CycloneDX SBOM | `949c0c83b5ac460a67ccb0d021d28d36a8cee806760c1b4e7ffeff9ffdf3c4ec` | `57c39ad8468d2d418a5a2d0996d10054ea8ba7171a6f6a7c2b4b1b7709652234` |
