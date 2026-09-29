# Remote MCP server (streamable HTTP at /mcp) for Claude custom connectors.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install .

# Bake the latest prebuilt index (published weekly by the GitHub Action) into the image.
# The server refreshes it on start once it is older than 7 days.
RUN easa-regs-fetch --index

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health',timeout=4)"
CMD ["easa-regs-mcp", "--http"]
