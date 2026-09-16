## Filesystem MCP validation

Use only the insighthub_filesystem MCP server.
List the top-level entries of the InsightHub project directory.
Do not recurse, do not read file contents, and do not modify anything.

## Docker MCP validation

Use only the Docker MCP server.
List running containers.
Do not execute commands inside containers and do not modify Docker state.

## Kubernetes MCP validation

Use only the Kubernetes MCP server.
List Services in namespace insighthub.
Do not modify any Kubernetes resources.

## Prometheus MCP validation

Use only the Prometheus MCP server.
Run the PromQL query `up` and summarize the returned series.
Do not perform any administrative Prometheus operations.

## Debugging exercise

Use only the Docker MCP server to investigate the container named
day2-debug-fail...