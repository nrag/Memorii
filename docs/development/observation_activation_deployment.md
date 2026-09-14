# Observation Activation Deployment Bootstrap

`tools/observation_activation_bootstrap.py` is the trusted launcher-side
pre-import verifier for the Observation Activation target.  It is standard
library only and must be pinned independently by release/deployment tooling.
It intentionally does not import `memorii`, invoke an installer, parse JSON,
read environment configuration, or execute an installed entry-point.

The launcher constructs the protected frozen `DeploymentConfiguration` from
its release-prepared deployment record, starts CPython 3.11+ with a newly
created private `-X pycache_prefix`, and calls:

```python
facts = verify_deployment(
    configuration,
    private_pycache_prefix=launcher_created_private_prefix,
)
```

Only after this succeeds may the launcher import Memorii.  It then converts
the same protected configuration and returned `DeploymentVerificationFacts`
to core's typed `DeploymentConfiguration` and
`DeploymentVerificationReceipt`; it must not rebuild either from request data,
environment variables, a manifest, or an installed package.

The verifier requires exact interpreter implementation/version/platform,
unloaded Memorii modules, the configured `sys.pycache_prefix`, no Memorii
bytecode in the installation or private prefix, canonical non-overlapping
nofollow site and scripts anchors, and an installed closure matching the
configuration.  It validates every distribution's normalized metadata and
RECORD bytes, all RECORD-owned files' hashes and sizes, RECORD traversal only
to the two anchors, and all site entries.  Scripts may contain host-owned
launcher/interpreter files; every configured script must nevertheless be
RECORD-owned and pinned.  It rejects symlinks, special files, editable or zip
shadow selection, package bytecode, unrecorded site files, duplicate ownership,
and unsupported policy literals.

The configuration records only a release-prepared wheel digest; verification
does not claim to reconstruct or reinstall that wheel.  Release preparation
must verify wheel bytes before its offline `pip --no-deps --no-compile
--no-index --target` installation, build the complete row closure afterwards,
and launch a separate fresh verifier process.  Preparation/signing are owned
by the release tool and are deliberately outside this bootstrap module.

Before the first Memorii or selected-dependency import, the trusted host calls
`install_selected_distribution_origin_guard(configuration)` and retains the
returned guard through composition.  The guard is a normal meta-path finder:
it validates each selected `ModuleSpec` before its loader executes, including
transitive imports, native extensions, and namespace packages.  A namespace is
accepted only when every search location lies below its declared distribution
root.  The host may call `guard.remove()` only after it no longer needs this
deployment boundary enforced.  This is a deployment check in the trusted-host
TCB, not a defense against a process that has already modified Python's import
or filesystem observations.
