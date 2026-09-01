"use client";

import Link from "next/link";
import { useState } from "react";

import { api } from "../../lib/api";

type ToolProposal = { approval_id: string };
type ToolResult = { tool: string; result: unknown };
type MCPServer = { name: string; url: string };
type MCPTool = { name: string; description?: string | null; input_schema?: Record<string, unknown> };
type GitHubFile = { path: string; sha: string; size: number; content: string };

export default function ConnectionsPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [output, setOutput] = useState("");

  const [mcpServers, setMcpServers] = useState<MCPServer[]>([]);
  const [mcpServer, setMcpServer] = useState("");
  const [mcpTools, setMcpTools] = useState<MCPTool[]>([]);
  const [mcpTool, setMcpTool] = useState("");
  const [mcpArgs, setMcpArgs] = useState("{}");

  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  const [branch, setBranch] = useState("main");
  const [path, setPath] = useState("");
  const [remoteSha, setRemoteSha] = useState("");
  const [remoteContent, setRemoteContent] = useState("");
  const [commitMessage, setCommitMessage] = useState("Update from Genesis");
  const [newBranch, setNewBranch] = useState("");
  const [prTitle, setPrTitle] = useState("");
  const [prBase, setPrBase] = useState("main");
  const [prBody, setPrBody] = useState("");

  async function execute(tool: string, args: Record<string, unknown>) {
    const proposal = await api<ToolProposal>("/v1/tools/propose", {
      method: "POST",
      body: JSON.stringify({ tool, arguments: args }),
    });
    return api<ToolResult>("/v1/tools/execute", {
      method: "POST",
      body: JSON.stringify({ approval_id: proposal.approval_id, approved: true }),
    });
  }

  async function run(label: string, action: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await action();
      setOutput(`${label}\n\n${JSON.stringify(result, null, 2)}`);
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setOutput(`${label} failed\n\n${message}`);
      return undefined;
    } finally {
      setBusy(false);
    }
  }

  async function refreshMcpServers() {
    const response = await run("MCP servers", async () => execute("mcp.servers", {}));
    const result = response as ToolResult | undefined;
    const servers = ((result?.result as { servers?: MCPServer[] } | undefined)?.servers ?? []);
    setMcpServers(servers);
    if (!mcpServer && servers.length) setMcpServer(servers[0].name);
  }

  async function refreshMcpTools() {
    if (!mcpServer) return;
    const response = await run(`MCP tools · ${mcpServer}`, async () => execute("mcp.list_tools", { server: mcpServer }));
    const result = response as ToolResult | undefined;
    const tools = ((result?.result as { tools?: MCPTool[] } | undefined)?.tools ?? []);
    setMcpTools(tools);
    if (tools.length) setMcpTool(tools[0].name);
  }

  async function callMcpTool() {
    if (!mcpServer || !mcpTool) return;
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(mcpArgs) as Record<string, unknown>;
    } catch {
      setError("MCP arguments must be valid JSON");
      return;
    }
    if (!window.confirm(`Call MCP tool ${mcpServer} / ${mcpTool} with these exact arguments?`)) return;
    await run(`MCP call · ${mcpTool}`, async () => execute("mcp.call_tool", { server: mcpServer, name: mcpTool, arguments: parsed }));
  }

  async function githubInfo() {
    if (!owner || !repo) return;
    await run("GitHub repository", async () => execute("github.repo_info", { owner, repo }));
  }

  async function readGithubFile() {
    if (!owner || !repo || !path) return;
    const response = await run("GitHub file", async () => execute("github.read_file", { owner, repo, path, ref: branch }));
    const result = response as ToolResult | undefined;
    const file = result?.result as GitHubFile | undefined;
    if (file?.content !== undefined) {
      setRemoteContent(file.content);
      setRemoteSha(file.sha ?? "");
    }
  }

  async function saveGithubFile() {
    if (!owner || !repo || !branch || !path) return;
    const action = remoteSha ? "replace" : "create";
    if (!window.confirm(`${action} ${owner}/${repo}:${branch}/${path} with the editor contents?`)) return;
    await run("GitHub write", async () => execute("github.upsert_file", {
      owner,
      repo,
      path,
      content: remoteContent,
      message: commitMessage,
      branch,
      expected_sha: remoteSha || null,
    }));
    await readGithubFile();
  }

  async function createGithubBranch() {
    if (!owner || !repo || !newBranch) return;
    if (!window.confirm(`Create branch ${newBranch} from ${branch}?`)) return;
    await run("Create GitHub branch", async () => execute("github.create_branch", {
      owner,
      repo,
      new_branch: newBranch,
      from_branch: branch,
    }));
  }

  async function createPullRequest() {
    if (!owner || !repo || !prTitle || !branch || !prBase) return;
    if (!window.confirm(`Open pull request ${branch} → ${prBase}?`)) return;
    await run("Create pull request", async () => execute("github.create_pull_request", {
      owner,
      repo,
      title: prTitle,
      head: branch,
      base: prBase,
      body: prBody,
    }));
  }

  return (
    <main className="shell connectionsShell">
      <header className="topbar">
        <div>
          <div className="eyebrow">GENESIS / CONNECTIONS</div>
          <h1>Connections</h1>
        </div>
        <Link className="textLink" href="/">← workstation</Link>
      </header>

      {error && <div className="error">{error}</div>}

      <div className="connectionsGrid">
        <section className="panel connectionPanel">
          <div className="panelTitle"><div><span>01</span> MCP</div><small>allowlisted · v2 · HTTP</small></div>
          <div className="connectionBody">
            <p className="mutedCopy">Only Streamable HTTP servers explicitly listed in <code>MCP_SERVERS_JSON</code> can be reached.</p>
            <button disabled={busy} onClick={refreshMcpServers}>Refresh configured servers</button>
            <label>
              Server
              <select value={mcpServer} onChange={(event) => { setMcpServer(event.target.value); setMcpTools([]); setMcpTool(""); }}>
                <option value="">select server</option>
                {mcpServers.map((server) => <option key={server.name} value={server.name}>{server.name} · {server.url}</option>)}
              </select>
            </label>
            <button disabled={busy || !mcpServer} onClick={refreshMcpTools}>Discover tools</button>
            <label>
              Tool
              <select value={mcpTool} onChange={(event) => setMcpTool(event.target.value)}>
                <option value="">select tool</option>
                {mcpTools.map((tool) => <option key={tool.name} value={tool.name}>{tool.name}</option>)}
              </select>
            </label>
            {mcpTool && <div className="schemaBox"><b>{mcpTool}</b><pre>{JSON.stringify(mcpTools.find((item) => item.name === mcpTool)?.input_schema ?? {}, null, 2)}</pre></div>}
            <label>
              Arguments JSON
              <textarea rows={8} value={mcpArgs} onChange={(event) => setMcpArgs(event.target.value)} />
            </label>
            <button className="approveButton" disabled={busy || !mcpServer || !mcpTool} onClick={callMcpTool}>Review & call MCP tool</button>
          </div>
        </section>

        <section className="panel connectionPanel">
          <div className="panelTitle"><div><span>02</span> GitHub</div><small>token stays server-side</small></div>
          <div className="connectionBody">
            <div className="twoCol">
              <label>Owner<input value={owner} onChange={(event) => setOwner(event.target.value)} placeholder="owner" /></label>
              <label>Repository<input value={repo} onChange={(event) => setRepo(event.target.value)} placeholder="repository" /></label>
            </div>
            <div className="twoCol">
              <label>Branch<input value={branch} onChange={(event) => { setBranch(event.target.value); setRemoteSha(""); }} /></label>
              <button disabled={busy || !owner || !repo} onClick={githubInfo}>Repository info</button>
            </div>
            <label>File path<input value={path} onChange={(event) => { setPath(event.target.value); setRemoteSha(""); }} placeholder="src/file.ts" /></label>
            <button disabled={busy || !owner || !repo || !path} onClick={readGithubFile}>Read remote file</button>
            <div className="shaLine">remote SHA: {remoteSha || "not loaded / new file"}</div>
            <label>File contents<textarea rows={16} value={remoteContent} onChange={(event) => setRemoteContent(event.target.value)} /></label>
            <label>Commit message<input value={commitMessage} onChange={(event) => setCommitMessage(event.target.value)} /></label>
            <button className="approveButton" disabled={busy || !owner || !repo || !branch || !path} onClick={saveGithubFile}>{remoteSha ? "Review & replace remote file" : "Review & create remote file"}</button>

            <div className="connectionDivider" />
            <div className="twoCol">
              <label>New branch<input value={newBranch} onChange={(event) => setNewBranch(event.target.value)} placeholder="genesis/my-change" /></label>
              <button disabled={busy || !newBranch} onClick={createGithubBranch}>Create from current branch</button>
            </div>

            <div className="connectionDivider" />
            <label>PR title<input value={prTitle} onChange={(event) => setPrTitle(event.target.value)} /></label>
            <div className="twoCol"><label>Head<input value={branch} onChange={(event) => setBranch(event.target.value)} /></label><label>Base<input value={prBase} onChange={(event) => setPrBase(event.target.value)} /></label></div>
            <label>PR body<textarea rows={5} value={prBody} onChange={(event) => setPrBody(event.target.value)} /></label>
            <button disabled={busy || !prTitle || !branch || !prBase} onClick={createPullRequest}>Review & open pull request</button>
          </div>
        </section>

        <section className="panel connectionPanel outputPanel">
          <div className="panelTitle"><div><span>03</span> Result</div><small>{busy ? "working" : "idle"}</small></div>
          <pre className="connectionOutput">{output || "Connection results appear here."}</pre>
        </section>
      </div>
    </main>
  );
}
