import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "..", "assets", "libra_memory.db")
conn = sqlite3.connect(db_path)
c = conn.cursor()

bad_episodes = [60, 61, 66, 155, 156, 157, 158, 159]
for eid in bad_episodes:
    c.execute("DELETE FROM episodes WHERE id = ?", (eid,))
    try:
        c.execute("DELETE FROM vec_episodes WHERE episode_id = ?", (eid,))
    except Exception:
        pass

bad_facts = [4, 5, 23]
for fid in bad_facts:
    c.execute("DELETE FROM facts WHERE id = ?", (fid,))
    try:
        c.execute("DELETE FROM vec_facts WHERE fact_id = ?", (fid,))
    except Exception:
        pass

c.execute("DELETE FROM user_habits WHERE id = 2 OR action = 'roblox' OR target = 'roblox'")

conn.commit()
print(f"Cleaned episodes: {bad_episodes}")
print(f"Cleaned facts: {bad_facts}")
print("Cleaned user_habits matching roblox.")
conn.close()
