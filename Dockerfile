# One image for every Python service; docker-compose picks the command (ticket S02.1).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.31 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps apps
COPY packages packages
RUN uv sync --frozen --no-dev --all-packages

ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home --uid 1000 riven
USER riven

EXPOSE 8000
CMD ["uvicorn", "riven_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
