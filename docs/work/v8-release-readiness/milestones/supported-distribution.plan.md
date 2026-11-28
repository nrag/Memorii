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

Pi 0.99.2 and OpenClaw 2026.9.7 completed signed capture, duplicate receipt,
restart recall, revocation and unrelated-session denial. Audits from their
installed dependency closures reported two High packages for Pi and four for
OpenClaw. Pi embeds Undici and minimatch in the distributed executable. A
dependency override left their original bundled copies present. The pinned
versions remain in place. Approval to change and recertify those versions is
pending. A newer pin needs its own complete closure scan and host journey.
