# syntax=docker/dockerfile:1.7
# Reproducible, offline-at-runtime Duckling sidecar.  The source is fetched at
# one reviewed commit during build; it is deliberately not vendored in Memorii.
FROM debian:bookworm@sha256:813017f3d62be4b5891a7acca6a01bdcd4b8513daa81b1ab99d3a50385b26931 AS build

ARG DUCKLING_COMMIT=59a13ff87b1aa8be6b93d387244f8636b26185c5
ARG STACK_VERSION=3.9.3
ARG STACK_SHA256=bc45cf6e1d00910348dcceb510a469056f6d9c63997230f901c22cf997598b05

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git ghc build-essential libgmp-dev libpcre3-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
RUN curl --fail --location --silent --show-error --output /tmp/stack.tar.gz "https://github.com/commercialhaskell/stack/releases/download/v${STACK_VERSION}/stack-${STACK_VERSION}-linux-x86_64.tar.gz" \
    && echo "${STACK_SHA256}  /tmp/stack.tar.gz" | sha256sum --check --status \
    && tar -xzf /tmp/stack.tar.gz -C /tmp \
    && install -m 0755 /tmp/stack-${STACK_VERSION}-linux-x86_64/stack /usr/local/bin/stack \
    && rm -rf /tmp/stack.tar.gz /tmp/stack-${STACK_VERSION}-linux-x86_64
RUN git clone --no-checkout https://github.com/facebook/duckling.git /src/duckling \
    && git -C /src/duckling checkout --detach "${DUCKLING_COMMIT}" \
    && test "$(git -C /src/duckling rev-parse HEAD)" = "${DUCKLING_COMMIT}"
WORKDIR /src/duckling
RUN stack --no-terminal --system-ghc build duckling-example-exe \
    && install -D -m 0755 "$(stack --local-bin-path)/duckling-example-exe" /out/duckling-example-exe

FROM debian:bookworm-slim@sha256:abd67ffcfa541b485a3dff59865ab629aa048a6c613e639d36e7456b0b229241
LABEL org.opencontainers.image.source="https://github.com/facebook/duckling" \
      org.opencontainers.image.revision="59a13ff87b1aa8be6b93d387244f8636b26185c5" \
      org.opencontainers.image.licenses="MIT" \
      memorii.duckling.ruleset="duckling-59a13ff87b1aa8be6b93d387244f8636b26185c5"
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgmp10 libpcre3 zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --no-create-home --uid 65532 duckling
COPY --from=build /out/duckling-example-exe /usr/local/bin/duckling-example-exe
USER 65532:65532
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/duckling-example-exe", "--port", "8000"]
