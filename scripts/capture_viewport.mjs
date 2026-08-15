import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

const [url, outputPath, widthText, heightText, browserPath, colorScheme = "dark"] =
  process.argv.slice(2);
const width = Number.parseInt(widthText, 10);
const height = Number.parseInt(heightText, 10);

if (!url || !outputPath || !width || !height || !browserPath) {
  throw new Error(
    "Usage: node scripts/capture_viewport.mjs URL OUTPUT WIDTH HEIGHT BROWSER_PATH",
  );
}

const profilePath = await mkdtemp(path.join(tmpdir(), "sdzjoy-visual-"));
const browser = spawn(
  browserPath,
  [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--no-first-run",
    "--remote-debugging-port=0",
    `--user-data-dir=${profilePath}`,
    "about:blank",
  ],
  { stdio: "ignore", windowsHide: true },
);

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function readDebugPort() {
  const activePortPath = path.join(profilePath, "DevToolsActivePort");
  for (let attempt = 0; attempt < 80; attempt += 1) {
    try {
      const [port] = (await readFile(activePortPath, "utf8")).trim().split("\n");
      return port;
    } catch {
      await delay(100);
    }
  }
  throw new Error("Browser debugging endpoint did not become ready");
}

let socket;
try {
  const port = await readDebugPort();
  const target = await fetch(
    `http://127.0.0.1:${port}/json/new?${encodeURIComponent("about:blank")}`,
    { method: "PUT" },
  ).then((response) => response.json());

  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  let nextId = 0;
  const pending = new Map();
  const eventWaiters = new Map();
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
      return;
    }
    const waiters = eventWaiters.get(message.method) ?? [];
    eventWaiters.delete(message.method);
    for (const resolve of waiters) resolve(message.params);
  });

  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      nextId += 1;
      pending.set(nextId, { resolve, reject });
      socket.send(JSON.stringify({ id: nextId, method, params }));
    });
  const waitForEvent = (method) =>
    new Promise((resolve) => {
      eventWaiters.set(method, [...(eventWaiters.get(method) ?? []), resolve]);
    });

  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: true,
  });
  await send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-color-scheme", value: colorScheme }],
  });
  const loaded = waitForEvent("Page.loadEventFired");
  await send("Page.navigate", { url });
  await loaded;
  await delay(500);

  const screenshot = await send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  await writeFile(outputPath, Buffer.from(screenshot.data, "base64"));
} finally {
  socket?.close();
  const browserStopped = new Promise((resolve) => browser.once("exit", resolve));
  browser.kill();
  await Promise.race([browserStopped, delay(2000)]);
  if (profilePath.startsWith(tmpdir())) {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      try {
        await rm(profilePath, { recursive: true, force: true });
        break;
      } catch (error) {
        if (attempt === 19) throw error;
        await delay(100);
      }
    }
  }
}
