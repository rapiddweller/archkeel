# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

# The build context holds one tested platform wheel. The image compiles nothing (AD-858).
FROM python:3.11-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39

# The label must be in the image at the first push. It links the package to the repository.
LABEL org.opencontainers.image.source="https://github.com/rapiddweller/archkeel" \
      org.opencontainers.image.description="Archkeel development build of the main branch" \
      org.opencontainers.image.licenses="MIT"

# The core runs Git only from /usr/bin/git. Git refuses a mounted work tree of another owner.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory '*'

ARG WHEEL
COPY ${WHEEL} /wheels/${WHEEL}
RUN pip install --no-cache-dir --disable-pip-version-check /wheels/${WHEEL} && rm -r /wheels

WORKDIR /work
ENTRYPOINT ["archkeel"]
