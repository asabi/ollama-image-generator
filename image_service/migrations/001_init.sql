CREATE TABLE images (
    id              TEXT PRIMARY KEY,
    filename        TEXT NOT NULL,
    thumbnail       TEXT NOT NULL,
    user_prompt     TEXT NOT NULL,
    full_prompt     TEXT NOT NULL,
    negative_prompt TEXT,
    style           TEXT NOT NULL,
    width           INTEGER NOT NULL,
    height          INTEGER NOT NULL,
    seed            INTEGER,
    model           TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX idx_images_created_at ON images (created_at DESC);
