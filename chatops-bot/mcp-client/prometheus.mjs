import http from "node:http";
import { Client } from "@modelcontextprotocol/client";
import { StdioClientTransport } from "@modelcontextprotocol/client/stdio";

const proxy = http.createServer((request, response) => {
  if (request.method !== "GET" || !request.url?.startsWith("/api/v1/query")) {
    response.writeHead(404).end();
    return;
  }
  const upstream = http.request({ hostname: "prometheus", port: 9090, path: request.url, method: "GET" }, (result) => {
    response.writeHead(result.statusCode || 502, result.headers);
    result.pipe(response);
  });
  upstream.on("error", () => response.writeHead(502).end());
  upstream.end();
});

await new Promise((resolve) => proxy.listen(0, "127.0.0.1", resolve));
const port = proxy.address().port;
const transport = new StdioClientTransport({
  command: process.execPath,
  args: ["/opt/insighthub-mcp/src/server.mjs"],
  env: {
    PATH: process.env.PATH || "/usr/local/bin:/usr/bin:/bin",
    INSIGHTHUB_API_URL: "http://127.0.0.1:8000",
    INSIGHTHUB_PROMETHEUS_URL: `http://127.0.0.1:${port}`,
    INSIGHTHUB_MCP_PROMETHEUS: "1",
    INSIGHTHUB_MCP_TOOLS: "prometheus_summary",
    INSIGHTHUB_MCP_TIMEOUT_MS: "1500",
    INSIGHTHUB_MCP_MAX_BYTES: "65536",
  },
  stderr: "pipe",
});
const client = new Client({ name: "insighthub-chatops-worker", version: "1.0.0" });
try {
  await client.connect(transport, { timeout: 5000 });
  const tools = await client.listTools();
  if (!tools.tools.some((tool) => tool.name === "prometheus_summary")) throw new Error("prometheus_summary unavailable");
  const result = await client.callTool({ name: "prometheus_summary", arguments: { query: "requests_5m" } });
  process.stdout.write(JSON.stringify(result));
} finally {
  await transport.close().catch(() => {});
  proxy.close();
}
