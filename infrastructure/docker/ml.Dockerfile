# Build context: monorepo root. Installs ml-pipeline editable package.
FROM python:3.12-slim
WORKDIR /app/ml-pipeline
COPY ml-pipeline/pyproject.toml ml-pipeline/README.md ./
COPY ml-pipeline/src ./src
RUN pip install --no-cache-dir -e ".[api]"
# CMD defined when unified ML HTTP gateway exists
