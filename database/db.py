import os
from datetime import datetime, timedelta
import aiosqlite


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    reminder_time TEXT NOT NULL DEFAULT '09:55',
    portion_pages INTEGER NOT NULL DEFAULT 7,
    is_paused INTEGER NOT NULL DEFAULT 0,
    active_book_id INTEGER,
    streak_days INTEGER NOT NULL DEFAULT 0,
    last_read_date TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL,
    md_path TEXT NOT NULL,
    total_words INTEGER NOT NULL DEFAULT 0,
    total_pages INTEGER NOT NULL DEFAULT 0,
    read_words INTEGER NOT NULL DEFAULT 0,
    is_completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS daily_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    day_number INTEGER NOT NULL,
    plan_date TEXT NOT NULL,
    target_words INTEGER NOT NULL,
    read_words INTEGER NOT NULL DEFAULT 0,
    is_completed INTEGER NOT NULL DEFAULT 0,
    evening_prompted INTEGER NOT NULL DEFAULT 0,
    UNIQUE(book_id, day_number)
);

CREATE TABLE IF NOT EXISTS portions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    day_number INTEGER NOT NULL,
    words_count INTEGER NOT NULL,
    start_char INTEGER NOT NULL DEFAULT 0,
    end_char INTEGER NOT NULL DEFAULT 0,
    content_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
"""


async def _ensure_column(db: aiosqlite.Connection, table: str, column: str, ddl_type: str) -> None:
    cur = await db.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in await cur.fetchall()]
    if column not in cols:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


async def init_db(db_path: str) -> None:
    folder = os.path.dirname(db_path)
    if folder:
        os.makedirs(folder, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.executescript(CREATE_TABLES_SQL)
        await _ensure_column(db, "books", "read_words", "INTEGER NOT NULL DEFAULT 0")
        await _ensure_column(db, "users", "streak_days", "INTEGER NOT NULL DEFAULT 0")
        await _ensure_column(db, "users", "last_read_date", "TEXT")
        await _ensure_column(db, "users", "is_paused", "INTEGER NOT NULL DEFAULT 0")
        await _ensure_column(db, "users", "reminder_time", "TEXT NOT NULL DEFAULT '09:55'")
        await _ensure_column(db, "daily_progress", "evening_prompted", "INTEGER NOT NULL DEFAULT 0")
        await db.commit()


async def ensure_user(
    db_path: str,
    user_id: int,
    username: str | None,
    full_name: str | None,
    default_reminder_time: str = "09:55",
    default_portion_pages: int = 7,
) -> None:
    now_str = datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (
                user_id, username, full_name, reminder_time, portion_pages, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, full_name, default_reminder_time, default_portion_pages, now_str),
        )
        await db.execute(
            """
            UPDATE users
            SET username = COALESCE(?, username),
                full_name = COALESCE(?, full_name)
            WHERE user_id = ?
            """,
            (username, full_name, user_id),
        )
        await db.commit()


async def get_user(db_path: str, user_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_all_active_users(db_path: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE is_paused = 0")
        return [dict(r) for r in await cur.fetchall()]


async def update_user_portion_pages(db_path: str, user_id: int, portion_pages: int) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE users SET portion_pages = ? WHERE user_id = ?",
            (portion_pages, user_id),
        )
        await db.commit()


async def update_user_reminder_time(db_path: str, user_id: int, reminder_time: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE users SET reminder_time = ? WHERE user_id = ?",
            (reminder_time, user_id),
        )
        await db.commit()


async def set_user_paused(db_path: str, user_id: int, paused: bool) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE users SET is_paused = ? WHERE user_id = ?",
            (1 if paused else 0, user_id),
        )
        await db.commit()


async def create_book_with_plan(
    db_path: str,
    user_id: int,
    title: str,
    file_path: str,
    md_path: str,
    total_words: int,
    total_pages: int,
    day_word_counts: list[int],
) -> int:
    now_str = datetime.now().isoformat(timespec="seconds")
    start_date = datetime.now().date()

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            """
            INSERT INTO books (
                user_id, title, file_path, md_path, total_words, total_pages, read_words, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (user_id, title, file_path, md_path, total_words, total_pages, now_str),
        )
        book_id = cur.lastrowid

        for idx, target_words in enumerate(day_word_counts, start=1):
            plan_date = (start_date + timedelta(days=idx - 1)).isoformat()
            await db.execute(
                """
                INSERT INTO daily_progress (
                    user_id, book_id, day_number, plan_date, target_words, read_words, is_completed
                ) VALUES (?, ?, ?, ?, ?, 0, 0)
                """,
                (user_id, book_id, idx, plan_date, max(1, target_words)),
            )

        await db.execute(
            "UPDATE users SET active_book_id = ? WHERE user_id = ?",
            (book_id, user_id),
        )
        await db.commit()
        return book_id


async def get_active_book(db_path: str, user_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT b.*
            FROM users u
            JOIN books b ON u.active_book_id = b.id
            WHERE u.user_id = ?
            """,
            (user_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_user_books(db_path: str, user_id: int) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT * FROM books
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_book_by_id(db_path: str, book_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM books WHERE id = ? AND user_id = ?",
            (book_id, user_id),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_active_book(db_path: str, user_id: int, book_id: int) -> bool:
    book = await get_book_by_id(db_path, book_id, user_id)
    if not book:
        return False
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE users SET active_book_id = ? WHERE user_id = ?",
            (book_id, user_id),
        )
        await db.commit()
    return True


async def get_user_books_stats(db_path: str, user_id: int) -> list[dict]:
    return await get_user_books(db_path, user_id)


async def get_read_char_offset(db_path: str, book_id: int) -> int:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            """
            SELECT COALESCE(MAX(end_char), 0)
            FROM portions
            WHERE book_id = ? AND status = 'read'
            """,
            (book_id,),
        )
        row = await cur.fetchone()
        return int(row[0] or 0)


async def get_pending_portion(db_path: str, user_id: int, book_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT *
            FROM portions
            WHERE user_id = ? AND book_id = ? AND status = 'later'
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id, book_id),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_portion(
    db_path: str,
    user_id: int,
    book_id: int,
    day_number: int,
    words_count: int,
    start_char: int,
    end_char: int,
    content_text: str,
) -> int:
    now_str = datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            """
            INSERT INTO portions (
                user_id, book_id, day_number, words_count, start_char, end_char, content_text, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (user_id, book_id, day_number, words_count, start_char, end_char, content_text, now_str),
        )
        await db.commit()
        return cur.lastrowid


async def get_portion_by_id(db_path: str, portion_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM portions WHERE id = ?", (portion_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_portion_status(db_path: str, portion_id: int, status: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE portions SET status = ? WHERE id = ?",
            (status, portion_id),
        )
        await db.commit()


async def mark_portion_read_and_update_progress(
    db_path: str,
    user_id: int,
    book_id: int,
    portion_id: int,
    words_count: int,
) -> None:
    today_str = datetime.now().date().isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE portions SET status = 'read' WHERE id = ?", (portion_id,))

        await db.execute(
            """
            UPDATE books
            SET read_words = read_words + ?
            WHERE id = ?
            """,
            (words_count, book_id),
        )

        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT * FROM daily_progress
            WHERE book_id = ? AND is_completed = 0
            ORDER BY day_number ASC
            LIMIT 1
            """,
            (book_id,),
        )
        day_row = await cur.fetchone()
        if day_row:
            new_read = day_row["read_words"] + words_count
            is_done = 1 if new_read >= day_row["target_words"] else 0
            await db.execute(
                """
                UPDATE daily_progress
                SET read_words = ?, is_completed = ?
                WHERE id = ?
                """,
                (new_read, is_done, day_row["id"]),
            )

        b_cur = await db.execute(
            "SELECT total_words, read_words FROM books WHERE id = ?",
            (book_id,),
        )
        b_row = await b_cur.fetchone()
        if b_row and b_row["read_words"] >= int(b_row["total_words"] * 0.98):
            await db.execute("UPDATE books SET is_completed = 1 WHERE id = ?", (book_id,))

        u_cur = await db.execute(
            "SELECT streak_days, last_read_date FROM users WHERE user_id = ?",
            (user_id,),
        )
        u_row = await u_cur.fetchone()
        if u_row:
            last_date = u_row["last_read_date"]
            streak = u_row["streak_days"] or 0
            yesterday_str = (datetime.now().date() - timedelta(days=1)).isoformat()
            if last_date == today_str:
                new_streak = max(1, streak)
            elif last_date == yesterday_str:
                new_streak = streak + 1
            else:
                new_streak = 1

            await db.execute(
                "UPDATE users SET streak_days = ?, last_read_date = ? WHERE user_id = ?",
                (new_streak, today_str, user_id),
            )

        await db.commit()


async def get_book_progress_summary(db_path: str, book_id: int) -> dict:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT * FROM daily_progress
            WHERE book_id = ?
            ORDER BY day_number ASC
            """,
            (book_id,),
        )
        days = [dict(r) for r in await cur.fetchall()]
        current_day = next((d for d in days if d["is_completed"] == 0), days[-1] if days else None)
        return {
            "days": days,
            "current_day": current_day,
        }


async def skip_current_day_plan(db_path: str, book_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT * FROM daily_progress
            WHERE book_id = ? AND is_completed = 0
            ORDER BY day_number ASC
            LIMIT 1
            """,
            (book_id,),
        )
        day_row = await cur.fetchone()
        if not day_row:
            return None

        remaining_words = max(0, day_row["target_words"] - day_row["read_words"])
        await db.execute(
            "UPDATE daily_progress SET is_completed = 1 WHERE id = ?",
            (day_row["id"],),
        )

        rem_cur = await db.execute(
            """
            SELECT * FROM daily_progress
            WHERE book_id = ? AND is_completed = 0
            ORDER BY day_number ASC
            """,
            (book_id,),
        )
        rem_days = [dict(r) for r in await rem_cur.fetchall()]
        if rem_days and remaining_words > 0:
            add_per_day = max(1, remaining_words // len(rem_days))
            for rd in rem_days:
                await db.execute(
                    "UPDATE daily_progress SET target_words = target_words + ? WHERE id = ?",
                    (add_per_day, rd["id"]),
                )

        await db.commit()
        return dict(day_row)


async def get_unfinished_day_for_evening_prompt(db_path: str, book_id: int) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT * FROM daily_progress
            WHERE book_id = ? AND is_completed = 0 AND evening_prompted = 0
            ORDER BY day_number ASC
            LIMIT 1
            """,
            (book_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def mark_evening_prompted(db_path: str, day_progress_id: int) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE daily_progress SET evening_prompted = 1 WHERE id = ?",
            (day_progress_id,),
        )
        await db.commit()


async def apply_catchup_decision(db_path: str, book_id: int, double_tomorrow: bool) -> dict | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT * FROM daily_progress
            WHERE book_id = ? AND is_completed = 0
            ORDER BY day_number ASC
            LIMIT 1
            """,
            (book_id,),
        )
        today_day = await cur.fetchone()
        if not today_day:
            return None

        shortfall = max(0, today_day["target_words"] - today_day["read_words"])
        if shortfall == 0:
            await db.execute(
                "UPDATE daily_progress SET is_completed = 1 WHERE id = ?",
                (today_day["id"],),
            )
            await db.commit()
            return {"shortfall": 0, "next_day_target": today_day["target_words"]}

        next_cur = await db.execute(
            """
            SELECT * FROM daily_progress
            WHERE book_id = ? AND day_number > ? AND is_completed = 0
            ORDER BY day_number ASC
            """,
            (book_id, today_day["day_number"]),
        )
        later_days = [dict(r) for r in await next_cur.fetchall()]

        if not later_days:
            new_target = today_day["read_words"] + shortfall
            await db.execute(
                "UPDATE daily_progress SET target_words = ? WHERE id = ?",
                (new_target, today_day["id"]),
            )
            await db.commit()
            return {"shortfall": shortfall, "next_day_target": new_target}

        if double_tomorrow:
            tomorrow = later_days[0]
            new_tomorrow_target = tomorrow["target_words"] + shortfall
            await db.execute(
                "UPDATE daily_progress SET target_words = ? WHERE id = ?",
                (new_tomorrow_target, tomorrow["id"]),
            )
            await db.execute(
                "UPDATE daily_progress SET target_words = read_words, is_completed = 1 WHERE id = ?",
                (today_day["id"],),
            )
            await db.commit()
            return {
                "shortfall": shortfall,
                "next_day_number": tomorrow["day_number"],
                "next_day_target": new_tomorrow_target,
            }
        else:
            extra_per_day = max(1, shortfall // len(later_days))
            for ld in later_days:
                await db.execute(
                    "UPDATE daily_progress SET target_words = target_words + ? WHERE id = ?",
                    (extra_per_day, ld["id"]),
                )
            await db.execute(
                "UPDATE daily_progress SET target_words = read_words, is_completed = 1 WHERE id = ?",
                (today_day["id"],),
            )
            await db.commit()
            return {
                "shortfall": shortfall,
                "days_updated": len(later_days),
                "extra_per_day": extra_per_day,
            }