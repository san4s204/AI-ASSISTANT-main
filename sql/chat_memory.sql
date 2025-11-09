-- sql/chat_memory.sql
CREATE TABLE IF NOT EXISTS chat_memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id   INTEGER NOT NULL,  -- владелец "дочернего" бота (tg id)
    chat_id    INTEGER NOT NULL,  -- чат, в котором идёт диалог с этим ботом
    role       TEXT    NOT NULL,  -- 'user' или 'assistant'
    content    TEXT    NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
