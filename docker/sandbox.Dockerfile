# The image of a module sandbox: gemini and its runtime dependencies, for a non-root user.
# Build it with `make sandbox-image`; see .claude/docs/testing.md#sandbox-image.
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim

COPY pyproject.toml README.md LICENSE /src/
COPY gemini /src/gemini
RUN pip install --no-cache-dir --disable-pip-version-check /src && rm -rf /src

RUN useradd --create-home --uid 1000 sandbox
USER sandbox
WORKDIR /home/sandbox
