-- sql/grant_vip.sql
-- Параметры:
--   :uid       - Telegram ID пользователя
--   :username  - username (можно оставить NULL)
--   :years     - на сколько лет вперёд

PRAGMA foreign_keys = ON;

WITH new_end AS (
  SELECT datetime('now', printf('+%d years', :years)) AS dt
)
INSERT INTO users (id, username, subscribe, date_end, state_bot)
VALUES (
  :uid,
  :username,
  'subscribe',
  (SELECT dt FROM new_end),
  COALESCE((SELECT state_bot FROM users WHERE id = :uid), 'stop')
)
ON CONFLICT(id) DO UPDATE SET
  subscribe = 'subscribe',
  date_end  = (SELECT dt FROM new_end),
  username  = COALESCE(:username, users.username);
