import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { AnimatePresence, motion } from "framer-motion";
import {
  Check,
  CircleAlert,
  Clock3,
  Flame,
  History,
  RotateCcw,
  Shield,
  SkipForward,
  Sparkles,
  StepBack,
  Timer
} from "lucide-react";

const DEFAULT_DECISIONS = ["adult_likely", "review", "error"];

function App() {
  const [stats, setStats] = useState(null);
  const [items, setItems] = useState([]);
  const [index, setIndex] = useState(0);
  const [show, setShow] = useState("unreviewed");
  const [decisions, setDecisions] = useState(DEFAULT_DECISIONS);
  const [note, setNote] = useState("");
  const [history, setHistory] = useState([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [celebrating, setCelebrating] = useState(false);
  const videoRef = useRef(null);

  const item = items[index] || null;

  useEffect(() => {
    refresh();
  }, [show, decisions.join(",")]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.target.tagName === "TEXTAREA") return;
      if (!["ArrowLeft", "ArrowUp", "ArrowRight", " ", "Backspace"].includes(event.key)) return;
      event.preventDefault();
      if (event.key === "ArrowLeft") submit("safe");
      if (event.key === "ArrowUp") submit("needs_review");
      if (event.key === "ArrowRight") submit("adult");
      if (event.key === " ") next();
      if (event.key === "Backspace") undo();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [item, note]);

  useEffect(() => {
    if (stats?.remainingReview === 0 && stats?.total) {
      setCelebrating(true);
      const timeout = window.setTimeout(() => setCelebrating(false), 4800);
      return () => window.clearTimeout(timeout);
    }
  }, [stats?.remainingReview, stats?.total]);

  async function refresh(options = {}) {
    const query = new URLSearchParams({ show, decisions: decisions.join(","), limit: "500" });
    const [statsResponse, itemsResponse] = await Promise.all([fetch("/api/stats"), fetch(`/api/items?${query}`)]);
    setStats(await statsResponse.json());
    setItems(await itemsResponse.json());
    setIndex(options.keepIndex ? (value) => Math.min(value, Math.max(0, items.length - 1)) : 0);
    if (!options.keepNote) setNote("");
  }

  async function submit(userDecision) {
    if (!item) return;
    const votedItem = item;
    await fetch("/api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: item.id, userDecision, note })
    });
    setHistory((current) => [
      {
        id: votedItem.id,
        filename: votedItem.filename,
        decision: votedItem.decision,
        scoreText: votedItem.scoreText,
        userDecision,
        note,
        at: new Date().toLocaleTimeString()
      },
      ...current
    ].slice(0, 50));
    setNote("");
    await refresh();
  }

  async function undo() {
    const last = history[0];
    if (!last) return;
    await fetch(`/api/review/${last.id}`, { method: "DELETE" });
    setHistory((current) => current.slice(1));
    await refresh();
  }

  function back() {
    setIndex((value) => Math.max(0, value - 1));
  }

  function next() {
    setNote("");
    setIndex((value) => Math.min(value + 1, Math.max(0, items.length - 1)));
  }

  function seekVideo(timestamp) {
    if (!videoRef.current) return;
    videoRef.current.currentTime = timestamp;
    videoRef.current.play().catch(() => {});
  }

  function toggleDecision(decision) {
    setDecisions((current) =>
      current.includes(decision) ? current.filter((value) => value !== decision) : [...current, decision]
    );
  }

  const progressText = useMemo(() => `${Math.min(index + 1, items.length)} / ${items.length}`, [index, items.length]);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <Shield size={22} />
          <h1>Review Queue</h1>
        </div>
        <div className="stat-grid">
          <Stat label="Total" value={stats?.total ?? "..."} />
          <Stat label="Voted" value={stats?.reviewed ?? "..."} accent />
          <Stat label="Needs Review" value={stats?.decisions?.review ?? "..."} />
          <Stat label="Adult Likely" value={stats?.decisions?.adult_likely ?? "..."} />
        </div>
        <div className="legend">
          <h2>Keys</h2>
          <LegendKey keyName="Left" label="vote safe" />
          <LegendKey keyName="Up" label="vote later" />
          <LegendKey keyName="Right" label="vote adult" />
          <LegendKey keyName="Space" label="skip only" />
          <LegendKey keyName="Backspace" label="undo vote" />
        </div>
        <button className="history-toggle" onClick={() => setHistoryOpen((value) => !value)}>
          <History size={16} /> Session history <span>{history.length}</span>
        </button>
        <AnimatePresence>
          {historyOpen && (
            <motion.div
              className="history-panel"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
            >
              {history.length ? (
                history.slice(0, 12).map((entry) => <HistoryItem key={`${entry.id}-${entry.at}`} entry={entry} />)
              ) : (
                <div className="history-empty">No votes this session.</div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
        <div className="filters">
          <label>
            Queue
            <select value={show} onChange={(event) => setShow(event.target.value)}>
              <option value="unreviewed">Unreviewed</option>
              <option value="reviewed">Voted</option>
              <option value="all">All</option>
            </select>
          </label>
          <div className="decision-toggles">
            {["adult_likely", "review", "error", "safe"].map((decision) => (
              <button
                key={decision}
                className={decisions.includes(decision) ? "active" : ""}
                onClick={() => toggleDecision(decision)}
              >
                {decision}
              </button>
            ))}
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <h2>{item ? item.filename : "No items in queue"}</h2>
          <div>
            <span className="pill">{progressText}</span>{" "}
            {item && <span className="pill">{item.decision}</span>}
          </div>
        </header>
        <section className="stage">
          <div className="media-pane">
            <AnimatePresence mode="wait">
              {item ? (
              <motion.div
                key={item.id}
                className="media-shell"
                initial={{ opacity: 0, scale: 0.985, x: 18 }}
                animate={{ opacity: 1, scale: 1, x: 0 }}
                exit={{ opacity: 0, scale: 0.985, x: -18 }}
                transition={{ duration: 0.22 }}
              >
                {item.media_type === "video" ? (
                  <video ref={videoRef} src={item.mediaUrl} controls autoPlay muted loop />
                ) : (
                  <img src={item.mediaUrl} alt={item.filename} />
                )}
              </motion.div>
              ) : (
                <motion.div className="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  Queue cleared for this filter.
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          <aside className="details">
            {item && (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.22 }}
              >
                <div className="filename">{item.filename}</div>
                <div className="meta">
                  <Meta label="Score" value={item.scoreText} />
                  <Meta label="Type" value={item.media_type} />
                  <Meta label="Final" value={item.final_decision} />
                  <Meta label="Frames" value={item.sampled_frames} />
                  <Meta label="Bytes" value={item.size_bytes?.toLocaleString()} />
                  <Meta label="Hash" value={item.sha256?.slice(0, 16)} />
                </div>
                {item.media_type === "video" && Array.isArray(item.frame_results) && item.frame_results.length > 0 && (
                  <div className="timeline">
                    <div className="timeline-title">
                      <Timer size={15} /> sampled frames
                    </div>
                    <div className="timeline-chips">
                      {item.frame_results.map((frame) => (
                        <button
                          key={`${item.id}-${frame.timestamp}`}
                          className={`timeline-chip ${frame.decision}`}
                          onClick={() => seekVideo(frame.timestamp)}
                          title={`score ${Number(frame.score || 0).toFixed(3)}`}
                        >
                          <Clock3 size={13} /> {formatTimestamp(frame.timestamp)}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <textarea
                  rows="5"
                  placeholder="Optional note"
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                />
              </motion.div>
            )}
          </aside>
        </section>
        <footer className="actions">
          <button className="utility-action" onClick={back} disabled={index === 0}>
            <StepBack size={18} /> Back
          </button>
          <button className="utility-action" onClick={undo} disabled={!history.length}>
            <RotateCcw size={18} /> Undo <kbd>Backspace</kbd>
          </button>
          <button className="utility-action" onClick={next}>
            <SkipForward size={18} /> Skip <kbd>Space</kbd>
          </button>
          <button className="action safe" onClick={() => submit("safe")}>
            <Check size={18} /> Safe <kbd>Left</kbd>
          </button>
          <button className="action review" onClick={() => submit("needs_review")}>
            <CircleAlert size={18} /> Later <kbd>Up</kbd>
          </button>
          <button className="action adult" onClick={() => submit("adult")}>
            <Flame size={18} /> Adult <kbd>Right</kbd>
          </button>
        </footer>
      </main>
      <AnimatePresence>{celebrating && <Celebration />}</AnimatePresence>
    </div>
  );
}

function Stat({ label, value, accent = false }) {
  return (
    <motion.div className={`stat ${accent ? "accent" : ""}`} layout>
      <span>{label}</span>
      <motion.strong key={value} initial={{ y: 8, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
        {value}
      </motion.strong>
    </motion.div>
  );
}

function Meta({ label, value }) {
  return (
    <div className="meta-row">
      <span>{label}</span>
      <strong>{value ?? "n/a"}</strong>
    </div>
  );
}

function LegendKey({ keyName, label }) {
  return (
    <div className="legend-row">
      <kbd>{keyName}</kbd>
      <span>{label}</span>
    </div>
  );
}

function HistoryItem({ entry }) {
  return (
    <div className="history-item">
      <span className={`history-vote ${entry.userDecision}`}>{entry.userDecision}</span>
      <strong>{entry.filename}</strong>
      <small>{entry.at} · model {entry.decision} · {entry.scoreText}</small>
    </div>
  );
}

function Celebration() {
  return (
    <motion.div className="celebration" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <div className="celebration-card">
        <Sparkles size={34} />
        <h2>Queue cleared</h2>
      </div>
      {Array.from({ length: 30 }).map((_, index) => (
        <motion.span
          key={index}
          className="confetti"
          initial={{ y: -40, x: `${Math.random() * 100}vw`, rotate: 0 }}
          animate={{ y: "105vh", rotate: 360 + Math.random() * 360 }}
          transition={{ duration: 2.4 + Math.random() * 1.6, ease: "easeOut" }}
        />
      ))}
    </motion.div>
  );
}

function formatTimestamp(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(value / 60);
  const remainder = Math.floor(value % 60);
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

createRoot(document.getElementById("root")).render(<App />);
