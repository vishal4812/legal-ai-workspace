import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";

const chromium = process.env.CHROMIUM_PATH || "/snap/bin/chromium";
const frontend = process.env.PHASE7_BROWSER_BASE_URL || "http://127.0.0.1:5173";

function command(args, options = {}) {
  return spawnSync(args[0], args.slice(1), {
    cwd: new URL("..", import.meta.url),
    encoding: "utf8",
    ...options,
  });
}

async function freePort() {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

class CDP {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
  }

  async open() {
    await new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result);
        return;
      }
      for (const listener of this.listeners.get(message.method) || []) listener(message.params);
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) || [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  close() {
    this.socket.close();
  }
}

async function waitFor(fn, message, timeout = 60_000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (await fn()) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${message}`);
}

async function main() {
  const setup = command([
    "docker", "compose", "exec", "-T", "backend",
    "python", "-m", "scripts.phase7_browser_fixture", "setup",
  ]);
  if (setup.status !== 0) throw new Error(setup.stderr || setup.stdout);
  const line = setup.stdout.split("\n").find((value) => value.startsWith("PHASE7_FIXTURE_JSON="));
  if (!line) throw new Error(`Fixture setup did not return JSON: ${setup.stdout}`);
  const fixture = JSON.parse(line.slice("PHASE7_FIXTURE_JSON=".length));
  const failureCollection = `phase7_browser_failure_${fixture.retry_document_id.replaceAll("-", "")}`;
  const profile = mkdtempSync(join(tmpdir(), "legal-master-phase7-browser-"));
  const port = await freePort();
  const browser = spawn(chromium, [
    "--headless=new",
    "--no-sandbox",
    "--disable-gpu",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    "about:blank",
  ], { stdio: "ignore" });
  let cdp;
  try {
    let target;
    await waitFor(async () => {
      try {
        const response = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(frontend + "/login")}`, { method: "PUT" });
        if (!response.ok) return false;
        target = await response.json();
        return true;
      } catch {
        return false;
      }
    }, "Chromium DevTools endpoint", 30_000);
    cdp = new CDP(target.webSocketDebuggerUrl);
    await cdp.open();
    await Promise.all([cdp.send("Page.enable"), cdp.send("Runtime.enable"), cdp.send("Network.enable"), cdp.send("Log.enable")]);
    const consoleErrors = [];
    cdp.on("Runtime.exceptionThrown", (event) => consoleErrors.push(event.exceptionDetails.text));
    cdp.on("Log.entryAdded", (event) => {
      if (event.entry.level === "error") consoleErrors.push(event.entry.text);
    });

    async function evaluate(expression) {
      const result = await cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
      return result.result.value;
    }
    const bodyHas = (text) => evaluate(`document.body?.innerText.includes(${JSON.stringify(text)}) === true`);
    const setInput = (selector, value) => evaluate(`(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return false;
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      setter.call(element, ${JSON.stringify(value)});
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    })()`);
    const clickText = (text) => evaluate(`(() => {
      const element = [...document.querySelectorAll("button,a")].find((item) => item.textContent.trim() === ${JSON.stringify(text)});
      if (!element) return false;
      element.click();
      return true;
    })()`);
    const clickDocumentAction = (filename, text) => evaluate(`(() => {
      const article = [...document.querySelectorAll("article")].find((item) => item.innerText.includes(${JSON.stringify(filename)}));
      const element = article && [...article.querySelectorAll("button")].find((item) => item.textContent.trim() === ${JSON.stringify(text)});
      if (!element) return false;
      element.click();
      return true;
    })()`);
    async function recreateBackend(collectionName) {
      const args = collectionName
        ? ["env", `QDRANT_COLLECTION_NAME=${collectionName}`, "docker", "compose", "up", "-d", "--force-recreate", "backend"]
        : ["docker", "compose", "up", "-d", "--force-recreate", "backend"];
      const result = command(args);
      if (result.status !== 0) throw new Error(result.stderr || result.stdout);
      await waitFor(async () => {
        try {
          return (await fetch("http://127.0.0.1:8000/health")).ok;
        } catch {
          return false;
        }
      }, "recreated backend health", 60_000);
    }
    function qdrantCollection(action, dimension = 4) {
      const code = action === "create"
        ? `from qdrant_client import QdrantClient, models; c=QdrantClient(url='http://qdrant:6333'); c.create_collection(collection_name=${JSON.stringify(failureCollection)}, vectors_config=models.VectorParams(size=${dimension}, distance=models.Distance.COSINE)); c.close()`
        : `from qdrant_client import QdrantClient; c=QdrantClient(url='http://qdrant:6333'); c.delete_collection(collection_name=${JSON.stringify(failureCollection)}); c.close()`;
      const result = command(["docker", "compose", "exec", "-T", "backend", "python", "-c", code]);
      if (result.status !== 0) throw new Error(result.stderr || result.stdout);
    }
    async function login(email) {
      await cdp.send("Page.navigate", { url: `${frontend}/login` });
      await waitFor(() => evaluate("Boolean(document.querySelector('input[type=email]'))"), "login form");
      await setInput("input[type=email]", email);
      await setInput("input[type=password]", fixture.password);
      if (!(await clickText("Sign in"))) throw new Error("Sign in button missing");
      await waitFor(() => evaluate("location.pathname !== '/login'"), "successful login");
    }
    const vaultUrl = `${frontend}/workspaces/${fixture.workspace_id}/cases/${fixture.case_id}/documents`;

    await login(fixture.owner_email);
    console.log("Chromium: owner authenticated");
    await cdp.send("Page.navigate", { url: vaultUrl });
    await waitFor(() => bodyHas(fixture.document_name), "document vault");
    await waitFor(() => bodyHas("Index for search"), "owner indexing control");
    if (!(await clickDocumentAction(fixture.document_name, "Index for search"))) throw new Error("Index control missing");
    await waitFor(() => bodyHas("Indexing"), "processing state", 30_000);
    await waitFor(() => bodyHas("Search index: Indexed"), "completed index", 300_000);
    console.log("Chromium: indexing completed");
    if (!(await bodyHas("512 dimensions"))) throw new Error("Embedding dimension missing");
    consoleErrors.length = 0;

    await setInput("input[maxlength='2000']", "termination written notice");
    await clickText("Search");
    await waitFor(() => bodyHas("Semantic Search Results"), "semantic results");
    console.log("Chromium: owner search completed");
    if (!(await bodyHas("termination"))) throw new Error("Expected ranked source text missing");
    if (await bodyHas("AI Legal Advice")) throw new Error("Search was mislabeled as legal advice");

    let downloadStatus;
    cdp.on("Network.responseReceived", (event) => {
      if (event.response.url.endsWith(`/documents/${fixture.document_id}/download`)) downloadStatus = event.response.status;
    });
    await clickDocumentAction(fixture.document_name, "Download");
    await waitFor(() => Promise.resolve(downloadStatus === 200), "authenticated original download", 30_000);
    console.log("Chromium: original download verified");

    await recreateBackend(failureCollection);
    qdrantCollection("create", 4);
    if (!(await clickDocumentAction(fixture.retry_document_name, "Index for search"))) {
      throw new Error("Failure test index control missing");
    }
    await waitFor(() => bodyHas("The vector collection dimension does not match the embedding model"), "safe failed index state");
    await waitFor(() => bodyHas("Retry indexing"), "retry indexing control");
    console.log("Chromium: safe failure state visible");
    qdrantCollection("delete");
    if (!(await clickDocumentAction(fixture.retry_document_name, "Retry indexing"))) {
      throw new Error("Retry control missing");
    }
    await waitFor(() => evaluate(`(() => {
      const article = [...document.querySelectorAll("article")].find((item) => item.innerText.includes(${JSON.stringify(fixture.retry_document_name)}));
      return article?.innerText.includes("Search index: Indexed") === true;
    })()`), "successful browser retry", 300_000);
    console.log("Chromium: failed index retry completed");
    qdrantCollection("delete");
    await recreateBackend(null);
    consoleErrors.length = 0;

    await clickText("Sign out");
    await waitFor(() => evaluate("location.pathname === '/login'"), "logout");
    await login(fixture.viewer_email);
    console.log("Chromium: viewer authenticated");
    await cdp.send("Page.navigate", { url: vaultUrl });
    console.log("Chromium: viewer vault navigation sent");
    await waitFor(() => bodyHas("Search index: Indexed"), "viewer index status");
    console.log("Chromium: viewer index status visible");
    consoleErrors.length = 0;
    const viewerHasControl = await evaluate(`[...document.querySelectorAll("button")].some((item) => ["Index for search", "Retry indexing"].includes(item.textContent.trim()))`);
    if (viewerHasControl) throw new Error("Viewer received an indexing mutation control");
    await setInput("input[maxlength='2000']", "termination clause");
    await clickText("Search");
    await waitFor(() => bodyHas("Semantic Search Results"), "viewer semantic results");
    console.log("Chromium: viewer search completed");
    if (consoleErrors.length) throw new Error(`Browser console errors: ${consoleErrors.join(" | ")}`);
    console.log("Phase 7 Chromium E2E passed");
  } finally {
    if (cdp) cdp.close();
    browser.kill("SIGTERM");
    rmSync(profile, { recursive: true, force: true });
    const cleanup = command(
      ["docker", "compose", "exec", "-T", "-e", `PHASE7_FIXTURE_JSON=${JSON.stringify(fixture)}`, "backend", "python", "-m", "scripts.phase7_browser_fixture", "cleanup"],
    );
    if (cleanup.status !== 0) console.error(cleanup.stderr || cleanup.stdout);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
