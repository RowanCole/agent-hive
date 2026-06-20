"""SQLite 持久化层 — 会话、消息、任务、文件变更、偏好、Worker 注册表、模块文档。"""
import json
import time
import uuid
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Optional

from core.config import AgentConfig

_mem_lock = Lock()


class MemoryManager:
    """单例持久化管理器 — 所有 Agent 共享同一 SQLite 实例。"""

    _instance: Optional["MemoryManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with _mem_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init(*args, **kwargs)
        return cls._instance

    def _init(self, config: Optional[AgentConfig] = None):
        data_dir = config.data_path if config else Path.cwd() / "agent-hive"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(data_dir / "memory.db"), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, agent_type TEXT NOT NULL DEFAULT 'base',
                title TEXT DEFAULT '', status TEXT DEFAULT 'active',
                created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
                tool_calls TEXT, created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id, created_at);
            CREATE TABLE IF NOT EXISTS task_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                task_plan TEXT NOT NULL, task_results TEXT NOT NULL,
                task_end TEXT NOT NULL, created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS file_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                file_path TEXT NOT NULL, operation TEXT NOT NULL, created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS workers (
                name TEXT PRIMARY KEY, session_id TEXT, parent_id TEXT DEFAULT '',
                depth INTEGER DEFAULT 1, system_prompt TEXT, tools_json TEXT,
                task_summary TEXT DEFAULT '', status TEXT DEFAULT 'idle', created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS module_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, agent_name TEXT NOT NULL,
                agent_type TEXT NOT NULL, session_id TEXT NOT NULL,
                doc_type TEXT NOT NULL DEFAULT 'interface', title TEXT NOT NULL,
                content TEXT NOT NULL, version INTEGER DEFAULT 1,
                created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_md_agent ON module_docs(agent_name, doc_type);
            CREATE INDEX IF NOT EXISTS idx_md_type ON module_docs(agent_type, doc_type);
        """)
        self.conn.commit()

    # ── 会话 ──
    def create_session(self, agent_type: str = "base", title: str = "") -> str:
        sid = str(uuid.uuid4())[:8]
        now = time.time()
        self.conn.execute(
            "INSERT INTO sessions(id, agent_type, title, created_at, updated_at) VALUES(?,?,?,?,?)",
            (sid, agent_type, title, now, now),
        )
        self.conn.commit()
        return sid

    def touch_session(self, session_id: str):
        self.conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (time.time(), session_id))
        self.conn.commit()

    def list_sessions(self, limit=20, agent_type=None):
        if agent_type:
            return self.conn.execute(
                "SELECT * FROM sessions WHERE agent_type=? AND status='active' ORDER BY updated_at DESC LIMIT ?",
                (agent_type, limit),
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM sessions WHERE status='active' ORDER BY updated_at DESC LIMIT ?", (limit,),
        ).fetchall()

    def archive_session(self, session_id: str):
        self.conn.execute("UPDATE sessions SET status='archived' WHERE id=?", (session_id,))
        self.conn.commit()

    # ── 消息 ──
    def save_message(self, session_id: str, role: str, content: str, tool_calls=None):
        self.conn.execute(
            "INSERT INTO messages(session_id, role, content, tool_calls, created_at) VALUES(?,?,?,?,?)",
            (session_id, role, content,
             json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None, time.time()),
        )
        self.conn.commit()

    def load_messages(self, session_id: str, limit=50):
        rows = self.conn.execute(
            "SELECT role, content, tool_calls FROM messages WHERE session_id=? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return list(rows)

    # ── 任务 ──
    def save_task(self, session_id: str, task_plan: list, task_results: list, task_end: list):
        self.conn.execute(
            "INSERT INTO task_records(session_id, task_plan, task_results, task_end, created_at) VALUES(?,?,?,?,?)",
            (session_id, json.dumps(task_plan, ensure_ascii=False),
             json.dumps(task_results, ensure_ascii=False),
             json.dumps(task_end, ensure_ascii=False), time.time()),
        )
        self.conn.commit()

    def get_recent_tasks(self, limit=3):
        rows = self.conn.execute(
            "SELECT task_plan, task_results, task_end FROM task_records ORDER BY id DESC LIMIT ?", (limit,),
        ).fetchall()
        rows = list(rows); rows.reverse()
        return [(json.loads(r["task_plan"]), json.loads(r["task_results"]), json.loads(r["task_end"])) for r in rows]

    # ── 文件变更 ──
    def record_file_change(self, session_id: str, file_path: str, operation: str):
        self.conn.execute(
            "INSERT INTO file_changes(session_id, file_path, operation, created_at) VALUES(?,?,?,?)",
            (session_id, file_path, operation, time.time()),
        )
        self.conn.commit()

    def get_modified_files(self, session_id: str = None):
        if session_id:
            return [r["file_path"] for r in self.conn.execute(
                "SELECT DISTINCT file_path FROM file_changes WHERE session_id=?", (session_id,))]
        return [r["file_path"] for r in self.conn.execute("SELECT DISTINCT file_path FROM file_changes")]

    # ── 偏好 ──
    def set_preference(self, key: str, value: str):
        self.conn.execute("INSERT OR REPLACE INTO preferences(key, value) VALUES(?,?)", (key, value))
        self.conn.commit()

    def get_preference(self, key: str, default=""):
        row = self.conn.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    # ── Worker 注册表 ──
    def register_worker(self, name: str, session_id: str, system_prompt="",
                        tools=None, task_summary="", depth=1, parent_id=""):
        self.conn.execute(
            "INSERT OR REPLACE INTO workers(name, session_id, parent_id, depth, system_prompt, tools_json, task_summary, status, created_at) VALUES(?,?,?,?,?,?,?,'idle',?)",
            (name, session_id, parent_id, depth, system_prompt,
             json.dumps(tools or [], ensure_ascii=False), task_summary, time.time()),
        )
        self.conn.commit()

    def update_worker(self, name: str, **fields):
        sets = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE workers SET {sets} WHERE name=?", list(fields.values()) + [name])
        self.conn.commit()

    def get_worker(self, name: str):
        return self.conn.execute("SELECT * FROM workers WHERE name=?", (name,)).fetchone()

    def get_all_workers(self):
        return self.conn.execute("SELECT * FROM workers ORDER BY created_at").fetchall()

    def delete_worker(self, name: str):
        self.conn.execute("DELETE FROM workers WHERE name=?", (name,))
        self.conn.commit()

    # ── 模块设计文档 ──
    def publish_module_doc(self, agent_name: str, agent_type: str, session_id: str,
                           title: str, content: str, doc_type: str = "interface") -> int:
        now = time.time()
        existing = self.conn.execute(
            "SELECT id, version FROM module_docs WHERE agent_name=? AND doc_type=? AND title=? ORDER BY id DESC LIMIT 1",
            (agent_name, doc_type, title),
        ).fetchone()
        if existing:
            self.conn.execute("UPDATE module_docs SET content=?, version=?, updated_at=? WHERE id=?",
                              (content, existing["version"] + 1, now, existing["id"]))
            return existing["id"]
        self.conn.execute(
            "INSERT INTO module_docs(agent_name, agent_type, session_id, doc_type, title, content, version, created_at, updated_at) VALUES(?,?,?,?,?,?,1,?,?)",
            (agent_name, agent_type, session_id, doc_type, title, content, now, now),
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_module_doc(self, agent_name: str, doc_type: str = "interface") -> list:
        return self.conn.execute(
            "SELECT * FROM module_docs WHERE agent_name=? AND doc_type=? ORDER BY updated_at DESC",
            (agent_name, doc_type),
        ).fetchall()

    def list_module_docs(self, agent_type: str = None, doc_type: str = None) -> list:
        query = "SELECT * FROM module_docs WHERE 1=1"
        params = []
        if agent_type:
            query += " AND agent_type=?"; params.append(agent_type)
        if doc_type:
            query += " AND doc_type=?"; params.append(doc_type)
        return self.conn.execute(query + " ORDER BY updated_at DESC", params).fetchall()

    def search_module_docs(self, keyword: str) -> list:
        return self.conn.execute(
            "SELECT * FROM module_docs WHERE title LIKE ? OR content LIKE ? ORDER BY updated_at DESC",
            (f"%{keyword}%", f"%{keyword}%"),
        ).fetchall()

    def get_all_module_docs_summary(self) -> str:
        rows = self.conn.execute(
            "SELECT agent_name, agent_type, doc_type, title, substr(content, 1, 500) as snippet, version, updated_at FROM module_docs ORDER BY agent_name, doc_type"
        ).fetchall()
        if not rows:
            return ""
        lines = ["[各 Agent 模块设计文档]"]
        for r in rows:
            lines.append(
                f"  [{r['agent_type']}] {r['agent_name']} — {r['doc_type']}: {r['title']} (v{r['version']})\n    {r['snippet']}"
            )
        return "\n".join(lines)

    def load_project_context(self) -> str:
        for p in [Path.cwd() / "agent-hive" / "PROJECT.md", Path.cwd() / "CLAUDE.md"]:
            if p.exists():
                return p.read_text(encoding="utf-8")
        return ""
