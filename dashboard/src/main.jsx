import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const request = async (url, options = {}) => {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Request failed");
  return payload;
};

const modeDetails = {
  ask: { icon: "✦", title: "Ask", description: "Explain code or answer a question." },
  plan: { icon: "◫", title: "Plan", description: "Explore the approach before editing." },
  write: { icon: "↗", title: "Write", description: "Stage a proposed code change." },
  execute: { icon: "⌘", title: "Execute", description: "Use connected tools after confirmation." },
};

const buildTree = (paths) => {
  const root = { folders: {}, files: [] };
  paths.forEach((path) => {
    const parts = path.split("/");
    let node = root;
    parts.slice(0, -1).forEach((part) => {
      node.folders[part] ||= { folders: {}, files: [] };
      node = node.folders[part];
    });
    node.files.push({ name: parts.at(-1), path });
  });
  return root;
};

const fileGlyph = (name) => {
  if (/\.(py|js|jsx|ts|tsx|json|yaml|yml|toml|css|html|md)$/i.test(name)) return "⌘";
  return "·";
};

function Folder({ name, node, onOpen, selectedFile, depth = 0 }) {
  const [open, setOpen] = useState(depth < 1);
  return <div className="tree-node">
    <button className="folder" onClick={() => setOpen(!open)} aria-expanded={open}>
      <span className="chevron">{open ? "⌄" : "›"}</span><span className="folder-icon">▰</span>{name}
    </button>
    {open && <div className="tree-children">
      {Object.entries(node.folders).sort(([a], [b]) => a.localeCompare(b)).map(([folder, child]) => (
        <Folder key={folder} name={folder} node={child} onOpen={onOpen} selectedFile={selectedFile} depth={depth + 1} />
      ))}
      {node.files.sort((a, b) => a.name.localeCompare(b.name)).map((file) => (
        <button className={`file ${selectedFile === file.path ? "selected" : ""}`} key={file.path} onClick={() => onOpen(file.path)} title={file.path}>
          <span>{fileGlyph(file.name)}</span>{file.name}
        </button>
      ))}
    </div>}
  </div>;
}

function FileTree({ files, onOpen, selectedFile }) {
  const tree = useMemo(() => buildTree(files), [files]);
  return <div className="file-tree">
    {Object.entries(tree.folders).sort(([a], [b]) => a.localeCompare(b)).map(([folder, node]) => (
      <Folder key={folder} name={folder} node={node} onOpen={onOpen} selectedFile={selectedFile} />
    ))}
    {tree.files.map((file) => <button className={`file ${selectedFile === file.path ? "selected" : ""}`} key={file.path} onClick={() => onOpen(file.path)}><span>{fileGlyph(file.name)}</span>{file.name}</button>)}
  </div>;
}

function App() {
  const [status, setStatus] = useState(null);
  const [files, setFiles] = useState([]);
  const [fileQuery, setFileQuery] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState("");
  const [mode, setMode] = useState("ask");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [diff, setDiff] = useState("");
  const [sessions, setSessions] = useState([]);
  const [testOutput, setTestOutput] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState(null);
  const [provider, setProvider] = useState("gemini");
  const [model, setModel] = useState("gemini-2.5-flash");
  const [fallbackChain, setFallbackChain] = useState([]);
  const [apiKeys, setApiKeys] = useState("");
  const [providerModels, setProviderModels] = useState({});
  const [modelsLoading, setModelsLoading] = useState(false);
  const [inspectorTab, setInspectorTab] = useState("changes");
  const [toolsOpen, setToolsOpen] = useState(false);
  const [toolCatalog, setToolCatalog] = useState(null);
  const [mcpName, setMcpName] = useState("");
  const [mcpCommand, setMcpCommand] = useState("npx");
  const [mcpArgs, setMcpArgs] = useState("");
  const [mcpEnv, setMcpEnv] = useState("");
  const composerRef = useRef(null);

  const refresh = async () => {
    const [nextStatus, nextFiles, nextDiff, nextSessions, nextSettings, nextTools] = await Promise.all([
      request("/api/status"),
      request(`/api/files?query=${encodeURIComponent(fileQuery)}`),
      request("/api/diff"),
      request("/api/sessions"),
      request("/api/settings"),
      request("/api/tools"),
    ]);
    setStatus(nextStatus);
    setFiles(nextFiles.files);
    setDiff(nextDiff.diff);
    setSessions(nextSessions.sessions);
    setSettings(nextSettings);
    setToolCatalog(nextTools);
  };

  const refreshProviderModels = async (targetProvider) => {
    setModelsLoading(true);
    try {
      const payload = await request(`/api/providers/${encodeURIComponent(targetProvider)}/models`);
      setProviderModels((current) => ({ ...current, [targetProvider]: payload }));
      return payload;
    } catch (error) {
      setProviderModels((current) => ({ ...current, [targetProvider]: { models: [], source: "catalog", message: error.message } }));
      return null;
    } finally { setModelsLoading(false); }
  };

  useEffect(() => { refresh().catch((error) => setNotice(error.message)); }, []);
  useEffect(() => {
    const timer = setTimeout(() => {
      request(`/api/files?query=${encodeURIComponent(fileQuery)}`)
        .then((payload) => setFiles(payload.files))
        .catch((error) => setNotice(error.message));
    }, 180);
    return () => clearTimeout(timer);
  }, [fileQuery]);
  useEffect(() => {
    if (!settingsOpen || !settings) return;
    setProvider(settings.current.provider);
    setModel(settings.current.model);
    setFallbackChain(settings.current.fallbacks || []);
    setApiKeys("");
    refreshProviderModels(settings.current.provider);
  }, [settingsOpen, settings]);
  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === "Escape") { setSettingsOpen(false); setToolsOpen(false); setSelectedFile(null); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const openFile = async (path) => {
    try {
      const payload = await request(`/api/file?path=${encodeURIComponent(path)}`);
      setSelectedFile(payload.path);
      setFileContent(payload.content);
    } catch (error) { setNotice(error.message); }
  };

  const choosePrompt = (nextMode, prompt) => {
    setMode(nextMode);
    setMessage(prompt);
    requestAnimationFrame(() => composerRef.current?.focus());
  };

  const send = async () => {
    if (!message.trim() || busy) return;
    if (mode === "execute" && !window.confirm("Execute mode can call enabled MCP servers and run local commands. Continue only if you trust the connected tools.")) return;
    const question = message.trim();
    setMessages((items) => [...items, { role: "user", content: question }]);
    setMessage("");
    setBusy(true);
    setNotice(mode === "write" ? "Staging your proposed change…" : "Working on it…");
    try {
      const payload = await request("/api/chat", {
        method: "POST", body: JSON.stringify({ message: question, mode, session_id: status?.session_id }),
      });
      setMessages((items) => [...items, { role: "assistant", content: payload.answer }]);
      setNotice(payload.staged ? "Changes are staged. Review them in Changes before applying." : "Done.");
      if (payload.staged) setInspectorTab("changes");
      await refresh();
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  };

  const action = async (endpoint) => {
    setBusy(true);
    setNotice("Working…");
    try {
      const payload = await request(endpoint, { method: "POST" });
      setNotice(payload.result || payload.answer || "Done.");
      if (endpoint === "/api/test") { setTestOutput(payload.result || ""); setInspectorTab("checks"); }
      if (endpoint === "/api/review") {
        setMessages((items) => [...items, { role: "review", content: payload.answer }]);
        setInspectorTab("changes");
      }
      await refresh();
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  };

  const selectSession = async (sessionId) => {
    try { await request(`/api/sessions/${sessionId}/select`, { method: "POST" }); await refresh(); setNotice("Session loaded."); }
    catch (error) { setNotice(error.message); }
  };

  const openTools = async () => {
    setToolsOpen(true);
    try { setToolCatalog(await request("/api/tools")); }
    catch (error) { setNotice(error.message); }
  };

  const updatePreset = async (name, enabled) => {
    setBusy(true);
    try {
      const payload = await request(`/api/tools/mcp/${encodeURIComponent(name)}`, { method: "PUT", body: JSON.stringify({ enabled }) });
      setToolCatalog((catalog) => ({ ...catalog, mcp_servers: payload.mcp_servers }));
      setNotice(`${name} MCP ${enabled ? "connected" : "disconnected"}. It will be used on the next execute request.`);
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  };

  const saveCustomMcp = async (event) => {
    event.preventDefault();
    const env = Object.fromEntries(mcpEnv.split("\n").map((line) => line.split(/=(.*)/s)).filter(([key]) => key?.trim()).map(([key, value]) => [key.trim(), value ?? ""]));
    setBusy(true);
    try {
      const payload = await request("/api/tools/mcp", { method: "POST", body: JSON.stringify({ name: mcpName, command: mcpCommand, args: mcpArgs.split("\n").filter(Boolean), env }) });
      setToolCatalog((catalog) => ({ ...catalog, mcp_servers: payload.mcp_servers }));
      setMcpName(""); setMcpCommand("npx"); setMcpArgs(""); setMcpEnv("");
      setNotice("Custom MCP connection saved locally. It will be used on the next execute request.");
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  };

  const removeMcp = async (name) => {
    if (!window.confirm(`Disconnect ${name}? Its local MCP configuration will be removed.`)) return;
    setBusy(true);
    try {
      const payload = await request(`/api/tools/mcp/${encodeURIComponent(name)}`, { method: "DELETE" });
      setToolCatalog((catalog) => ({ ...catalog, mcp_servers: payload.mcp_servers }));
      setNotice(`${name} disconnected.`);
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  };

  const sessionTitle = useMemo(() => status?.session?.title || "New session", [status]);
  const providerInfo = settings?.providers.find((item) => item.id === provider);
  const currentProvider = settings?.providers.find((item) => item.id === settings?.current?.provider);
  const currentModel = settings?.current?.model || "Choose a model";
  const connectedMcpCount = toolCatalog?.mcp_servers?.filter((server) => server.enabled).length || 0;
  const selectedProviderModels = providerModels[provider];
  const modelChoices = useMemo(() => Array.from(new Set([
    ...(selectedProviderModels?.models || []),
    ...(providerInfo?.models || []),
    model,
  ].filter(Boolean))).sort(), [selectedProviderModels, providerInfo, model]);
  const selectProvider = (value) => {
    setProvider(value);
    const next = settings.providers.find((item) => item.id === value);
    setModel(next?.models?.[0] || "");
    refreshProviderModels(value);
  };
  const fallbackChoices = (targetProvider) => Array.from(new Set([
    ...(providerModels[targetProvider]?.models || []),
    ...(settings?.providers.find((item) => item.id === targetProvider)?.models || []),
  ])).sort();
  const addFallback = () => {
    const nextProvider = settings?.providers.find((item) => item.id !== provider)?.id || provider;
    const nextModel = fallbackChoices(nextProvider)[0] || "";
    setFallbackChain((chain) => [...chain, { provider: nextProvider, model: nextModel }]);
    refreshProviderModels(nextProvider);
  };
  const updateFallback = (index, field, value) => {
    setFallbackChain((chain) => chain.map((fallback, currentIndex) => {
      if (currentIndex !== index) return fallback;
      if (field === "provider") {
        const nextModel = fallbackChoices(value)[0] || "";
        refreshProviderModels(value);
        return { provider: value, model: nextModel };
      }
      return { ...fallback, [field]: value };
    }));
  };
  const saveSettings = async () => {
    setBusy(true);
    try {
      const payload = await request("/api/settings", {
        method: "POST",
        body: JSON.stringify({ provider, model, fallbacks: fallbackChain, api_keys: apiKeys.trim() ? apiKeys.split("\n") : null }),
      });
      setSettings(payload);
      setApiKeys("");
      await refreshProviderModels(provider);
      setNotice("Model settings saved. Available models were refreshed using your local provider key.");
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  };

  return <main>
    <header className="app-header">
      <div className="brand"><span className="brand-mark">✦</span><div><span className="eyebrow">LOCAL-FIRST CODING AGENT</span><h1>CodeStart</h1></div></div>
      <div className="header-actions">
        <span className="model-chip" title="The selected model for new requests"><span className="live-dot"></span>{currentProvider?.label || "Model"} <b>{currentModel}</b></span>
        <span className={`workspace-chip ${status?.staged ? "has-changes" : ""}`}><span>{status?.staged ? "●" : "✓"}</span>{status?.staged ? "Changes ready" : "Workspace clean"}</span>
        <button className="tools-button" onClick={openTools}>⌘ Tools{connectedMcpCount ? <b>{connectedMcpCount}</b> : ""}</button>
        <button className="settings-button" onClick={() => setSettingsOpen(true)}>⚙ <span>Model settings</span></button>
      </div>
    </header>

    <section className="workspace">
      <aside className="files pane">
        <div className="pane-title file-heading"><div><span className="eyebrow">PROJECT</span><h2>Files <span>{status?.indexed_files ?? 0}</span></h2></div></div>
        <label className="search"><span>⌕</span><input value={fileQuery} onChange={(e) => setFileQuery(e.target.value)} placeholder="Find a file" aria-label="Find a file" /></label>
        <FileTree files={files} onOpen={openFile} selectedFile={selectedFile} />
        <div className="files-footer">{fileQuery ? `${files.length} matches` : "Select a file to preview"}</div>
      </aside>

      <section className="chat pane">
        <div className="pane-title chat-heading"><div><span className="eyebrow">ACTIVE SESSION</span><h2>{sessionTitle}</h2></div><button className="ghost" onClick={() => action("/api/index")} disabled={busy}>↻ Reindex</button></div>
        <div className="messages">
          {messages.length === 0 && <div className="welcome">
            <div className="welcome-icon">✦</div><h3>What are we building?</h3><p>Start with a question, make a plan, or ask the agent to stage a safe change for your review.</p>
            <div className="prompt-grid">
              <button onClick={() => choosePrompt("ask", "Explain the structure of this project and where I should start.")}><b>✦ Ask about the codebase</b><span>Get an answer without editing files.</span></button>
              <button onClick={() => choosePrompt("plan", "Plan the next improvement for this project. Explain the files you would change and why.")}><b>◫ Plan an improvement</b><span>See the approach before any edits.</span></button>
              <button onClick={() => choosePrompt("write", "Improve the user experience of this project. Stage the changes for me to review.")}><b>↗ Stage a change</b><span>Review a diff before applying it.</span></button>
            </div>
          </div>}
          {messages.map((item, index) => <article key={index} className={`message ${item.role}`}><span>{item.role === "user" ? "You" : item.role === "review" ? "Review" : "Assistant"}</span><pre>{item.content}</pre></article>)}
          {busy && <div className="typing"><i></i><i></i><i></i><span>Agent is working</span></div>}
        </div>
        <div className="composer">
          <div className="mode-switch" role="tablist" aria-label="Request mode">
            {Object.entries(modeDetails).map(([option, detail]) => <button key={option} className={mode === option ? "active" : ""} onClick={() => setMode(option)} role="tab" aria-selected={mode === option}><b>{detail.icon} {detail.title}</b><span>{detail.description}</span></button>)}
          </div>
          <div className="input-row"><textarea ref={composerRef} value={message} onChange={(e) => setMessage(e.target.value)} onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") send(); }} placeholder={mode === "write" ? "Describe the change you want to stage…" : mode === "plan" ? "What should we plan?" : "Ask anything about your project…"} /><button className="primary send-button" disabled={busy || !message.trim()} onClick={send}>Send <kbd>⌘↵</kbd></button></div>
          <p className="composer-note">{mode === "write" ? "Writes are staged first — nothing applies until you approve the diff." : mode === "execute" ? "Execute mode asks for confirmation and can call enabled MCP servers." : "Use ⌘↵ to send"}</p>
        </div>
      </section>

      <aside className="inspector pane">
        <div className="inspector-head"><div><span className="eyebrow">WORKSPACE ACTIVITY</span><h2>{inspectorTab === "changes" ? "Changes" : inspectorTab === "checks" ? "Checks" : "Sessions"}</h2></div><span className="inspector-status">{status?.staged ? "1 staged set" : "Up to date"}</span></div>
        <div className="inspector-tabs" role="tablist"><button className={inspectorTab === "changes" ? "active" : ""} onClick={() => setInspectorTab("changes")}>Changes{status?.staged && <i>•</i>}</button><button className={inspectorTab === "checks" ? "active" : ""} onClick={() => setInspectorTab("checks")}>Checks</button><button className={inspectorTab === "sessions" ? "active" : ""} onClick={() => setInspectorTab("sessions")}>Sessions</button></div>
        <div className="inspector-body">
          {inspectorTab === "changes" && <section className="tab-content">
            {status?.staged ? <pre className="diff-output">{diff}</pre> : <div className="empty-state"><span>↗</span><h3>No staged changes</h3><p>Use Write when you are ready to propose an edit. You will always see the diff first.</p></div>}
            <div className="actions"><button className="primary" disabled={!status?.staged || busy} onClick={() => action("/api/apply")}>Apply changes</button><button disabled={!status?.staged || busy} onClick={() => action("/api/undo")}>Discard</button><button className="ghost" disabled={!status?.staged || busy} onClick={() => action("/api/review")}>Review</button></div>
          </section>}
          {inspectorTab === "checks" && <section className="tab-content checks-content"><div className="check-callout"><span>✓</span><div><b>Validate your changes</b><p>Run the project test suite after applying a change.</p></div></div><button className="run-tests" disabled={busy} onClick={() => action("/api/test")}>▶ Run tests</button><pre className="test-output">{testOutput || "No checks have run in this session."}</pre></section>}
          {inspectorTab === "sessions" && <section className="tab-content sessions-content"><div className="sessions-top"><p>Switch context without losing your work.</p><button className="ghost" onClick={() => refresh()}>↻ Refresh</button></div>{sessions.slice(0, 8).map((session) => <button className={`session ${status?.session_id === session.id ? "current" : ""}`} key={session.id} onClick={() => selectSession(session.id)}><span>{session.pinned ? "📌" : "◌"}</span><div><b>{session.title}</b><small>{session.id.slice(0, 8)} · {session.pinned ? "Pinned" : "Recent"}</small></div>{status?.session_id === session.id && <em>Current</em>}</button>)}</section>}
        </div>
      </aside>
    </section>

    {selectedFile && <section className="preview pane"><div className="pane-title"><div><span className="eyebrow">FILE PREVIEW</span><h2>{selectedFile}</h2></div><button className="ghost" onClick={() => setSelectedFile(null)}>Close <kbd>Esc</kbd></button></div><pre>{fileContent}</pre></section>}

    {toolsOpen && <div className="modal-backdrop" role="presentation"><section className="tools-modal pane" role="dialog" aria-modal="true" aria-labelledby="tools-title"><div className="pane-title"><div><span className="eyebrow">INTEGRATIONS</span><h2 id="tools-title">Tools and MCP</h2></div><button className="ghost" onClick={() => setToolsOpen(false)}>Close <kbd>Esc</kbd></button></div><div className="tools-body">
      <p className="settings-intro">Core tools are built in. Connect trusted MCP servers to extend the agent for explicit execute requests.</p>
      <section><span className="eyebrow">BUILT IN</span><div className="core-tools">{toolCatalog?.core?.map((tool) => <div key={tool.name}><b>{tool.name}</b><span>{tool.description}</span></div>)}</div></section>
      <section><div className="section-heading"><div><span className="eyebrow">MCP CONNECTIONS</span><h3>Available servers</h3></div><span>{connectedMcpCount} connected</span></div><div className="mcp-list">{toolCatalog?.mcp_servers?.map((server) => <article className={`mcp-card ${server.enabled ? "connected" : ""}`} key={server.name}><div className="mcp-card-title"><div><b>{server.label}</b><span>{server.origin === "preset" ? "Preset" : "Custom"}</span></div><i>{server.enabled ? "Connected" : "Not connected"}</i></div><p>{server.description}</p><small>{server.requires}</small>{server.env_keys?.length > 0 && <small>Environment: {server.env_keys.join(", ")}</small>}<div className="mcp-actions">{server.origin === "preset" ? <button className={server.enabled ? "ghost" : "primary"} disabled={busy} onClick={() => updatePreset(server.name, !server.enabled)}>{server.enabled ? "Disconnect" : "Connect"}</button> : <button className="ghost" disabled={busy} onClick={() => removeMcp(server.name)}>Disconnect</button>}</div></article>)}</div></section>
      <form className="custom-mcp" onSubmit={saveCustomMcp}><div><span className="eyebrow">ADD CUSTOM STDIO MCP</span><h3>Connect another tool</h3><p>Only add commands from sources you trust. The server runs on your computer whenever Execute uses MCP.</p></div><div className="custom-grid"><label>Server name<input required value={mcpName} onChange={(event) => setMcpName(event.target.value)} placeholder="e.g. linear" pattern="[A-Za-z0-9][A-Za-z0-9_.-]{0,63}" /></label><label>Command<input required value={mcpCommand} onChange={(event) => setMcpCommand(event.target.value)} placeholder="npx" /></label></div><label>Arguments <small>One argument per line</small><textarea value={mcpArgs} onChange={(event) => setMcpArgs(event.target.value)} placeholder={"-y\n@modelcontextprotocol/server-example"} /></label><label>Environment <small>One KEY=value per line. Values are kept local and never shown again.</small><textarea value={mcpEnv} onChange={(event) => setMcpEnv(event.target.value)} placeholder="SERVICE_TOKEN=..." /></label><button className="primary" disabled={busy}>Save MCP connection</button></form>
    </div></section></div>}

    {settingsOpen && <div className="modal-backdrop" role="presentation"><section className="settings-modal pane" role="dialog" aria-modal="true" aria-labelledby="settings-title"><div className="pane-title"><div><span className="eyebrow">LOCAL SETTINGS</span><h2 id="settings-title">Model and fallback chain</h2></div><button className="ghost" onClick={() => setSettingsOpen(false)}>Close <kbd>Esc</kbd></button></div><div className="settings-body">
      <p className="settings-intro">Choose the provider that handles new requests. If it is unavailable, the optional fallback is tried automatically.</p>
      <div className="settings-grid"><label>Primary provider<select value={provider} onChange={(e) => selectProvider(e.target.value)}>{settings?.providers.map((item) => <option key={item.id} value={item.id}>{item.label}{item.configured ? ` · ${item.key_count} key${item.key_count === 1 ? "" : "s"}` : ""}</option>)}</select></label><div className="model-picker"><label>Primary model<input list="primary-models" value={model} onChange={(e) => setModel(e.target.value)} placeholder="Choose or enter a model" /><datalist id="primary-models">{modelChoices.map((item) => <option key={item} value={item} />)}</datalist></label><button type="button" className="ghost refresh-models" disabled={modelsLoading} onClick={() => refreshProviderModels(provider)}>{modelsLoading ? "Loading…" : "↻ Refresh models"}</button></div></div>
      <p className={`model-source ${selectedProviderModels?.source || "catalog"}`}>{selectedProviderModels?.message || "Suggested models are shown until you refresh from the provider."}</p>
      {providerInfo?.requires_api_key && <label>Add API key(s) <textarea value={apiKeys} onChange={(e) => setApiKeys(e.target.value)} placeholder={providerInfo.configured ? "Paste additional keys — one per line" : "Paste one or more keys — one per line"} /><small>{providerInfo.key_count ? `${providerInfo.key_count} key${providerInfo.key_count === 1 ? " is" : "s are"} already configured. New keys are added to the local recovery pool.` : "Keys are stored only in this project’s local .env file."} They are never displayed in the dashboard.</small></label>}
      <div className="fallback"><div className="fallback-heading"><div><span className="eyebrow">RECOVERY ORDER</span><h3>Fallback models</h3><p>Extra keys for the primary model are tried first. Then these models are tried in order when a provider error or limit is reached.</p></div><button type="button" className="ghost" onClick={addFallback}>+ Add fallback</button></div><div className="fallback-list">{fallbackChain.length === 0 && <p className="no-fallbacks">No model fallback is configured yet.</p>}{fallbackChain.map((fallback, index) => <div className="fallback-row" key={`${fallback.provider}-${index}`}><span>{index + 1}</span><label>Provider<select value={fallback.provider} onChange={(e) => updateFallback(index, "provider", e.target.value)}>{settings?.providers.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label><label>Model<input list={`fallback-models-${index}`} value={fallback.model} onChange={(e) => updateFallback(index, "model", e.target.value)} /><datalist id={`fallback-models-${index}`}>{fallbackChoices(fallback.provider).map((item) => <option key={item} value={item} />)}</datalist></label><button type="button" className="ghost remove-fallback" onClick={() => setFallbackChain((chain) => chain.filter((_, currentIndex) => currentIndex !== index))}>Remove</button></div>)}</div></div>
      <div className="settings-actions"><button className="ghost" onClick={() => setSettingsOpen(false)}>Cancel</button><button className="primary" disabled={busy || !model} onClick={saveSettings}>Save model settings</button></div>
    </div></section></div>}
    <footer className={notice ? "has-notice" : ""}><span>{notice || "Ready to help with this workspace."}</span>{busy && <span className="footer-busy">Working</span>}</footer>
  </main>;
}

createRoot(document.getElementById("root")).render(<App />);
