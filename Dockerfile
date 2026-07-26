# EnvAssure runtime image — install from a pre-built wheel only (fail-closed).
#
# CI stages exactly one wheel at docker/context/pkg.whl before build:
#   mkdir -p docker/context && cp dist/envassure-*.whl docker/context/pkg.whl
#   docker buildx build \
#     --build-arg BASE_IMAGE="$(grep -v '^#' docker/base-image.lock | grep -v '^$' | tail -n1)" \
#     --build-arg VERSION=0.2.0b1 \
#     --build-arg REVISION=<sha> \
#     -t ghcr.io/fraware/envassure:0.2.0b1 .
#
# Publish paths require BASE_IMAGE to contain @sha256: (see release.yml).

ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}

ARG VERSION=0.0.0
ARG REVISION=unknown

LABEL org.opencontainers.image.title="envassure" \
      org.opencontainers.image.description="Environment Assurance Compiler (eac)" \
      org.opencontainers.image.source="https://github.com/fraware/environment-assurance-compiler" \
      org.opencontainers.image.url="https://github.com/fraware/environment-assurance-compiler" \
      org.opencontainers.image.documentation="https://fraware.github.io/environment-assurance-compiler/" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.vendor="EnvAssure"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/envassure \
    PATH="/home/envassure/.local/bin:${PATH}"

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin envassure \
    && mkdir -p /work /tmp/wheel \
    && chown -R envassure:envassure /work /home/envassure /tmp/wheel

WORKDIR /work

# Exactly one architecture-independent wheel (py3-none-any).
COPY --chown=envassure:envassure docker/context/pkg.whl /tmp/wheel/pkg.whl

USER envassure

RUN python -m pip install --user --upgrade pip \
    && python -m pip install --user /tmp/wheel/pkg.whl \
    && rm -f /tmp/wheel/pkg.whl \
    && eac --version \
    && python - <<'PY'
import importlib.util
import sys
forbidden = ("gymnasium", "pettingzoo", "psycopg", "httpx", "openenv", "openenv_core")
for name in forbidden:
    if importlib.util.find_spec(name) is not None:
        print(f"FAIL: optional stack present after base wheel install: {name}", file=sys.stderr)
        raise SystemExit(1)
print("optional stacks absent")
PY

WORKDIR /work
ENTRYPOINT ["eac"]
CMD ["--help"]
