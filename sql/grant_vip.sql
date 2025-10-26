-- Параметры:
-- :issuer_id — Telegram ID того, кто выдаёт (должен быть в admins)
-- :uid       — Telegram ID пользователя, кому выдаём
-- :years     — на сколько лет продлить (по умолчанию 50)

-- гарантируем, что логовая таблица есть
CREATE TABLE IF NOT EXISTS admin_grants_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  issuer_id     INTEGER NOT NULL,
  target_id     INTEGER NOT NULL,
  granted_until TEXT    NOT NULL,
  created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

WITH new_end AS (
  SELECT datetime('now', '+' || COALESCE(:years, 50) || ' years') AS val
)

-- UPSERT в users только если issuer — админ
INSERT INTO users (id, subscribe, date_end)
SELECT :uid, 'subscribe', (SELECT val FROM new_end)
WHERE EXISTS (SELECT 1 FROM admins WHERE user_id = :issuer_id)
ON CONFLICT(id) DO UPDATE SET
  subscribe = 'subscribe',
  date_end  = excluded.date_end;

-- Запишем в лог только если выдача действительно произошла
INSERT INTO admin_grants_log(issuer_id, target_id, granted_until)
SELECT :issuer_id, :uid, (SELECT val FROM new_end)
WHERE EXISTS (SELECT 1 FROM admins WHERE user_id = :issuer_id);

-- Человекочитаемый результат
SELECT
  CASE
    WHEN EXISTS(SELECT 1 FROM admins WHERE user_id = :issuer_id)
      THEN 'OK: VIP granted to ' || :uid || ' until ' || (SELECT val FROM new_end)
    ELSE 'DENIED: issuer is not admin'
  END AS result;
