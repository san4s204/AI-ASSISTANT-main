-- Параметры, которые нужно передать:
-- :admin_id  — Telegram ID администратора
-- :note      — произвольная подпись (опционально)

CREATE TABLE IF NOT EXISTS admins (
  user_id INTEGER PRIMARY KEY,
  note    TEXT
);

INSERT OR IGNORE INTO admins(user_id, note)
VALUES (:admin_id, COALESCE(:note, NULL));

SELECT 'OK: admin added ' || :admin_id AS result;
