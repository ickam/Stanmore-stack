FROM python:3.13-alpine

ARG PYTHONDONTWRITEBYTECODE=1

ENV PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /uvx /bin/

RUN apk update && apk add bluez dumb-init

WORKDIR /stanmore2
COPY pyproject.toml uv.lock ./
RUN uv sync --extra mqtt --frozen

COPY marshallstanmore2 ./marshallstanmore2/
RUN rm -f /bin/uv /bin/uvx
ENTRYPOINT ["dumb-init", "--"]
CMD [".venv/bin/python", "-m", "marshallstanmore2"]
