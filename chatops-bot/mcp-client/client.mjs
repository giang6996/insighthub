import { Client } from "@modelcontextprotocol/client";
import { StdioClientTransport } from "@modelcontextprotocol/client/stdio";

const kubeconfig = process.env.KUBERNETES_MCP_KUBECONFIG;
const serverCommand = process.env.KUBERNETES_MCP_SERVER_COMMAND ||
  "/usr/local/lib/node_modules/kubernetes-mcp-server/node_modules/kubernetes-mcp-server-linux-amd64/bin/kubernetes-mcp-server-linux-amd64";
if (!kubeconfig) throw new Error("KUBERNETES_MCP_KUBECONFIG is required");

const transport = new StdioClientTransport({
  command: serverCommand,
  args: [
    "--read-only",
    "--disable-multi-cluster",
    "--toolsets=core",
    `--kubeconfig=${kubeconfig}`,
    "--log-file=stderr",
  ],
  env: {
    PATH: process.env.PATH || "/usr/local/bin:/usr/bin:/bin",
    KUBECONFIG: kubeconfig,
  },
  stderr: "pipe",
});

const client = new Client({ name: "insighthub-chatops-worker", version: "1.0.0" });
try {
  await client.connect(transport, { timeout: 5000 });
  const tools = await client.listTools();
  const tool = tools.tools.find((candidate) => candidate.name === "pods_list_in_namespace");
  if (!tool) throw new Error("pods_list_in_namespace is unavailable");
  const result = await client.callTool({
    name: tool.name,
    arguments: { namespace: "insighthub" },
  });
  process.stdout.write(JSON.stringify(result));
} finally {
  await transport.close().catch(() => {});
}
