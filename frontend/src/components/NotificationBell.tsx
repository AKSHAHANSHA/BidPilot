import { useEffect, useRef, useState } from "react";
import {
  fetchNotificationCounts,
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationDto,
} from "../lib/marketplace";

/**
 * Polling notification bell for the authenticated app shell.
 *
 * Polls counts every 30s and, when opened, loads the full list. Marking one read is optimistic
 * — the count decrements immediately; the server call runs in the background.
 */
export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<NotificationDto[]>([]);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Poll unread count.
  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const counts = await fetchNotificationCounts();
        if (!cancelled) setUnread(counts.unread);
      } catch {
        /* ignore */
      }
    }
    poll();
    const handle = window.setInterval(poll, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, []);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    function onClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  async function openList() {
    setOpen(true);
    setLoading(true);
    try {
      const rows = await fetchNotifications();
      setItems(rows);
    } finally {
      setLoading(false);
    }
  }

  async function markOne(id: string) {
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n)));
    setUnread((prev) => Math.max(0, prev - 1));
    await markNotificationRead(id);
  }

  async function markAll() {
    setUnread(0);
    setItems((prev) => prev.map((n) => ({ ...n, read_at: n.read_at ?? new Date().toISOString() })));
    await markAllNotificationsRead();
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        aria-label={`Notifications${unread ? ` (${unread} unread)` : ""}`}
        onClick={() => (open ? setOpen(false) : openList())}
        className="relative inline-flex items-center justify-center w-9 h-9 rounded-full border border-rule-soft hover:border-ink bg-surface"
      >
        <span aria-hidden>🔔</span>
        {unread > 0 ? (
          <span className="absolute -top-1 -right-1 min-w-4 h-4 px-1 text-[10px] font-semibold bg-signal text-white rounded-full grid place-items-center">
            {unread > 9 ? "9+" : unread}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="absolute right-0 mt-2 w-80 bg-surface border border-rule-soft rounded-[3px] shadow-lg z-30">
          <div className="flex items-center justify-between px-3 py-2 border-b border-rule-soft">
            <span className="text-xs uppercase tracking-widest text-ink-muted">Notifications</span>
            <button
              onClick={markAll}
              className="text-xs text-signal underline underline-offset-4 hover:no-underline"
            >
              Mark all read
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {loading ? (
              <div className="p-4 text-sm text-ink-muted">Loading…</div>
            ) : items.length === 0 ? (
              <div className="p-4 text-sm text-ink-muted">You have no notifications.</div>
            ) : (
              <ul className="divide-y divide-rule-soft">
                {items.map((n) => (
                  <li key={n.id}>
                    <button
                      onClick={() => !n.read_at && markOne(n.id)}
                      className={`w-full text-left px-3 py-2.5 hover:bg-paper ${
                        n.read_at ? "opacity-70" : ""
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {!n.read_at ? (
                          <span className="inline-block w-1.5 h-1.5 rounded-full bg-signal" />
                        ) : null}
                        <div className="text-sm font-medium">{n.title}</div>
                      </div>
                      {n.body ? (
                        <div className="text-xs text-ink-muted mt-1">{n.body}</div>
                      ) : null}
                      <div className="text-[10px] text-ink-muted mt-1 uppercase tracking-widest">
                        {new Date(n.created_at).toLocaleString()}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
