-- sql/grant_vip.sql
-- Параметры:
-- :issuer_id — Telegram ID администратора, который выдаёт
-- :uid       — Telegram ID пользователя, кому выдаём
-- :years     — на сколько лет (по умолчанию 50)

-- гарантируем необходимые таблицы
CREATE TABLE IF NOT EXISTS admins (
  user_id INTEGER PRIMARY KEY,
  note    TEXT
);

CREATE TABLE IF NOT EXISTS admin_grants_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  issuer_id     INTEGER NOT NULL,
  target_id     INTEGER NOT NULL,
  granted_until TEXT    NOT NULL,
  created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Выдаём/продлеваем подписку (только если issuer — админ)
INSERT INTO users (id, subscribe, date_end)
SELECT
  :uid,
  'subscribe',
  datetime('now', '+' || COALESCE(:years, 50) || ' years')
WHERE EXISTS (SELECT 1 FROM admins WHERE user_id = :issuer_id)
ON CONFLICT(id) DO UPDATE SET
  subscribe = 'subscribe',
  date_end  = datetime('now', '+' || COALESCE(:years, 50) || ' years');

-- Логирование (только если действительно админ)
INSERT INTO admin_grants_log(issuer_id, target_id, granted_until)
SELECT
  :issuer_id,
  :uid,
  datetime('now', '+' || COALESCE(:years, 50) || ' years')
WHERE EXISTS (SELECT 1 FROM admins WHERE user_id = :issuer_id);

-- Человекочитаемый результат
SELECT
  CASE
    WHEN EXISTS (SELECT 1 FROM admins WHERE user_id = :issuer_id)
      THEN 'OK: VIP granted to ' || :uid || ' until ' ||
           datetime('now', '+' || COALESCE(:years, 50) || ' years')
    ELSE 'DENIED: issuer is not admin'
  END AS result;
