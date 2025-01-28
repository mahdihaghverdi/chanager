FROM python:3.12-slim-bookworm AS python-base

ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.7.1 \
    POETRY_HOME="/optt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \  
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="${POETRY_HOME}/bin:${PATH}"

WORKDIR /code

COPY pyproject.toml poetry.lock /code/

# Install dependencies and the root package
RUN poetry install --no-ansi

COPY . /code

RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /code
USER appuser

RUN . /code/.venv/bin/activate
ENV PATH="/code/.venv/bin:${PATH}"
