#!/bin/sh
# Build only the pinned sidecar.  The caller must record the resulting OCI
# digest in the release binding before production composition can enable it.
set -eu

image_ref=${1:?usage: build-local.sh IMAGE_REF}
docker build --pull=false --file Dockerfile --tag "$image_ref" .
docker image inspect --format '{{index .RepoDigests 0}}' "$image_ref"
