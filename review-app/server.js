import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import url from "node:url";

const root = process.cwd();
const staticDir = fs.existsSync(path.join(root, "dist")) ? path.join(root, "dist") : path.join(root, "public");
const resultsPath = process.env.REVIEW_RESULTS || "D:\\adult-media-flagger\\media_flags.jsonl";
const reviewStatePath = process.env.REVIEW_STATE || "D:\\adult-media-flagger\\review-state.json";
const port = Number(process.env.PORT || 8787);

const items = loadItems(resultsPath);
const byId = new Map(items.map((item) => [String(item.id), item]));
let reviewState = loadReviewState(reviewStatePath);

const server = http.createServer(async (req, res) => {
  try {
    const parsed = new URL(req.url || "/", `http://${req.headers.host}`);
    if (parsed.pathname === "/api/stats") return json(res, stats());
    if (parsed.pathname === "/api/items") return json(res, queryItems(parsed));
    if (parsed.pathname === "/api/review" && req.method === "POST") return saveReview(req, res);
    if (parsed.pathname.startsWith("/api/review/") && req.method === "DELETE") return deleteReview(parsed, res);
    if (parsed.pathname.startsWith("/media/")) return serveMedia(parsed, res);
    return serveStatic(parsed, res);
  } catch (error) {
    res.writeHead(500, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: String(error?.stack || error) }));
  }
});

server.listen(port, () => {
  console.log(`Review app: http://localhost:${port}`);
  console.log(`Results: ${resultsPath}`);
  console.log(`Review state: ${reviewStatePath}`);
});

function loadItems(filePath) {
  const text = fs.readFileSync(filePath, "utf8");
  return text
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .map((item) => ({
      ...item,
      filename: path.basename(item.path),
      mediaUrl: `/media/${item.id}`,
      scoreText: typeof item.score === "number" ? item.score.toFixed(3) : "n/a"
    }));
}

function loadReviewState(filePath) {
  if (!fs.existsSync(filePath)) return {};
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function writeReviewState() {
  fs.mkdirSync(path.dirname(reviewStatePath), { recursive: true });
  fs.writeFileSync(reviewStatePath, JSON.stringify(reviewState, null, 2));
}

function stats() {
  const decisions = countBy(items, "decision");
  const reviews = countBy(Object.values(reviewState), "userDecision");
  return {
    total: items.length,
    decisions,
    reviews,
    reviewed: Object.keys(reviewState).length,
    remainingReview: items.filter((item) => ["review", "adult_likely", "error"].includes(item.decision) && !reviewState[item.id]).length
  };
}

function queryItems(parsed) {
  const decisions = (parsed.searchParams.get("decisions") || "review,adult_likely,error").split(",");
  const show = parsed.searchParams.get("show") || "unreviewed";
  const limit = Number(parsed.searchParams.get("limit") || 250);
  let filtered = items.filter((item) => decisions.includes(item.decision));
  if (show === "unreviewed") filtered = filtered.filter((item) => !reviewState[item.id]);
  if (show === "reviewed") filtered = filtered.filter((item) => reviewState[item.id]);
  filtered.sort((a, b) => decisionRank(a.decision) - decisionRank(b.decision) || (b.score || 0) - (a.score || 0));
  return filtered.slice(0, limit).map((item) => ({ ...item, review: reviewState[item.id] || null }));
}

async function saveReview(req, res) {
  const body = await readBody(req);
  const parsed = JSON.parse(body || "{}");
  if (!parsed.id || !byId.has(String(parsed.id))) {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "Unknown item id" }));
    return;
  }
  reviewState[String(parsed.id)] = {
    userDecision: parsed.userDecision,
    note: parsed.note || "",
    reviewedAt: new Date().toISOString()
  };
  writeReviewState();
  json(res, { ok: true, review: reviewState[String(parsed.id)], stats: stats() });
}

function deleteReview(parsed, res) {
  const id = decodeURIComponent(parsed.pathname.replace("/api/review/", ""));
  if (!byId.has(String(id))) {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "Unknown item id" }));
    return;
  }
  delete reviewState[String(id)];
  writeReviewState();
  json(res, { ok: true, stats: stats() });
}

function serveMedia(parsed, res) {
  const id = decodeURIComponent(parsed.pathname.replace("/media/", ""));
  const item = byId.get(id);
  if (!item) {
    res.writeHead(404);
    res.end("Not found");
    return;
  }
  const filePath = path.resolve(item.path);
  if (!fs.existsSync(filePath)) {
    res.writeHead(404);
    res.end("Missing media file");
    return;
  }
  res.writeHead(200, {
    "Content-Type": contentType(filePath),
    "Cache-Control": "public, max-age=3600"
  });
  fs.createReadStream(filePath).pipe(res);
}

function serveStatic(parsed, res) {
  const pathname = parsed.pathname === "/" ? "/index.html" : parsed.pathname;
  const filePath = path.join(staticDir, path.normalize(pathname).replace(/^(\.\.[/\\])+/, ""));
  if (!filePath.startsWith(staticDir) || !fs.existsSync(filePath)) {
    res.writeHead(404);
    res.end("Not found");
    return;
  }
  res.writeHead(200, { "Content-Type": contentType(filePath) });
  fs.createReadStream(filePath).pipe(res);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
    });
    req.on("end", () => resolve(body));
    req.on("error", reject);
  });
}

function json(res, data) {
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify(data));
}

function countBy(rows, key) {
  return rows.reduce((acc, row) => {
    const value = row?.[key] || "none";
    acc[value] = (acc[value] || 0) + 1;
    return acc;
  }, {});
}

function decisionRank(decision) {
  return { adult_likely: 0, review: 1, error: 2, safe: 3 }[decision] ?? 9;
}

function contentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm"
  }[ext] || "application/octet-stream";
}
