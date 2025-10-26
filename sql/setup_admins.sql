-- Создаём таблицу администраторов (телеграм-ID)
CREATE TABLE IF NOT EXISTS admins (
  user_id INTEGER PRIMARY KEY,
  note    TEXT
);

-- Лог всех выдач VIP (кто кому и до какой даты)
CREATE TABLE IF NOT EXISTS admin_grants_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  issuer_id     INTEGER NOT NULL,
  target_id     INTEGER NOT NULL,
  granted_until TEXT    NOT NULL,
  created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
