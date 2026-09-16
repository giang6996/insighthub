# Day 2 MCP Debug Session

## Scenario
A temporary Docker container was intentionally created with a controlled failure condition.

The container starts, prints a startup message, prints an error indicating that required configuration is missing, and exits with status code 1.

The purpose of this scenario is to verify that Codex can use the Docker MCP server to inspect a real failed container and identify the root cause without modifying Docker state.

## Constraints
Codex was instructed to use only Docker MCP.
No container modification, exec, restart, or removal was permitted.

## MCP Tools Used
- container inspection/list tool
- container logs tool

## Observed Evidence
Docker MCP reported:

Container: day2-debug-fail
State: Exited
Exit Code: 1

The container logs contained:

starting app
ERROR: required config missing

## Root Cause
The simulated application exits because required configuration is missing.

The Docker runtime itself is functioning normally; the failure is caused by the application command executed inside the container.

## Resolution
Provide the required configuration before container startup.

## Result
Codex successfully used Docker MCP to identify the failed container, inspect its logs, and determine the root cause without modifying Docker state.