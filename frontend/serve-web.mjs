// Serves the built web app and forwards /utender-api to the U-Tender API on the same address.
// The browser then talks to one origin, so the sign-in cookie (SameSite=lax) is sent with every request.
import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.PORT || 6245);
const API_HOST = process.env.API_HOST || "127.0.0.1";
const API_PORT = Number(process.env.API_PORT || 6246);
const ROOT = resolve(fileURLToPath(new URL("./dist", import.meta.url)));
const PREFIX = "/utender-api";

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".txt": "text/plain; charset=utf-8",
};

function forwardToApi(req, res) {
  const path = req.url.slice(PREFIX.length) || "/";
  const upstream = http.request(
    {
      host: API_HOST,
      port: API_PORT,
      path,
      method: req.method,
      headers: { ...req.headers, host: `${API_HOST}:${API_PORT}` },
    },
    (up) => {
      res.writeHead(up.statusCode || 502, up.headers);
      up.pipe(res);
    },
  );
  upstream.on("error", () => {
    if (!res.headersSent) res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    res.end("The U-Tender API is not available.");
  });
  req.pipe(upstream);
}

async function serveFile(req, res) {
  const pathname = decodeURIComponent(new URL(req.url, "http://local").pathname);
  let file = normalize(join(ROOT, pathname));
  if (!file.startsWith(ROOT)) {
    res.writeHead(403);
    res.end();
    return;
  }
  try {
    if ((await stat(file)).isDirectory()) file = join(file, "index.html");
  } catch {
    // Not a file: a page route such as /admin/requirements. The app decides what to show.
    file = join(ROOT, "index.html");
  }
  try {
    const body = await readFile(file);
    res.writeHead(200, { "content-type": TYPES[extname(file)] || "application/octet-stream" });
    res.end(body);
  } catch {
    res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    res.end("Not found");
  }
}

http
  .createServer((req, res) => {
    const url = req.url || "/";
    if (url === PREFIX || url.startsWith(`${PREFIX}/`) || url.startsWith(`${PREFIX}?`)) {
      forwardToApi(req, res);
    } else {
      serveFile(req, res);
    }
  })
  .listen(PORT, "0.0.0.0", () => {
    console.log(`U-Tender web on port ${PORT}, API on ${API_HOST}:${API_PORT}`);
  });
