import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.llm import LocalLLM


HOLDOUT_QUERIES = [
    # --- 14 Casual Chitchat Queries (typos, short phrasing, slang -> expected 'chat') ---
    ("yo libra u good?", "chitchat", "chat"),
    ("wassup bro hows it goin", "chitchat", "chat"),
    ("im kinda bored ngl", "chitchat", "chat"),
    ("thx for the help earlier!", "chitchat", "chat"),
    ("u still awake rn?", "chitchat", "chat"),
    ("tell me smth funny pls", "chitchat", "chat"),
    ("morning libra how u doin", "chitchat", "chat"),
    ("feeling super tired tdy", "chitchat", "chat"),
    ("who made u btw", "chitchat", "chat"),
    ("just chillin at home wbu", "chitchat", "chat"),
    ("goodnight libra ttyl", "chitchat", "chat"),
    ("ur pretty smart ngl", "chitchat", "chat"),
    ("hey u there?", "chitchat", "chat"),
    ("idk what to do tonight", "chitchat", "chat"),

    # --- 13 Casual Real-Time Queries (typos, short phrasing -> expected 'web_search' or 'weather') ---
    ("btc price rn?", "real-time", "web_search"),
    ("whos winning the lakers game", "real-time", "web_search"),
    ("tsla stock price tdy", "real-time", "web_search"),
    ("any breaking news abt SpaceX", "real-time", "web_search"),
    ("eth price right now", "real-time", "web_search"),
    ("arsenal vs chelsea live score", "real-time", "web_search"),
    ("latest tech news today", "real-time", "web_search"),
    ("whts the weather in tokyo rn", "real-time", "weather"),
    ("current gold price per oz", "real-time", "web_search"),
    ("nba standings right now", "real-time", "web_search"),
    ("f1 race results today", "real-time", "web_search"),
    ("nvda share price rn", "real-time", "web_search"),
    ("top headlines this morning", "real-time", "web_search"),

    # --- 13 Casual Mixed Queries (greeting/chitchat + real-time or general knowledge) ---
    ("yo libra hows it going check btc price for me", "mixed", "web_search"),
    ("hey bro u awake? whats the latest news on openai", "mixed", "web_search"),
    ("hi how are u doing can u check weather in london", "mixed", "weather"),
    ("sup libra hope ur good who won the ufc fight last night", "mixed", "web_search"),
    ("hey there how u feeling today check nvidia stock price", "mixed", "web_search"),
    ("yo what are u up to tell me todays breaking news", "mixed", "web_search"),
    ("good morning libra how was ur day whats the score of the nba game", "mixed", "web_search"),
    ("hey are u okay can u explain how recursion works in python", "mixed", "chat"),
    ("hi libra im bored tell me why black holes bend light", "mixed", "chat"),
    ("yo hows life can u check premier league table rn", "mixed", "web_search"),
    ("hey buddy how are you what happened today in world news", "mixed", "web_search"),
    ("sup libra u good? what is the difference between tcp and udp", "mixed", "chat"),
    ("hello how u doin check current eth price today", "mixed", "web_search"),
]


def run_holdout_benchmark() -> dict:
    """
    Runs the 40 held-out casual/typo queries against LocalLLM.plan(dry_run=True)
    and reports raw accuracy and every misclassified query without tuning the router.
    """
    llm = LocalLLM()
    correct = 0
    misses = []
    results = []

    for idx, (query, category, expected) in enumerate(HOLDOUT_QUERIES, 1):
        res = llm.plan(query, dry_run=True)
        actual = res.get("action")
        ok = (actual == expected)
        if ok:
            correct += 1
        else:
            misses.append({
                "index": idx,
                "query": query,
                "category": category,
                "expected": expected,
                "actual": actual,
            })
        results.append({
            "index": idx,
            "query": query,
            "category": category,
            "expected": expected,
            "actual": actual,
            "correct": ok,
        })

    total = len(HOLDOUT_QUERIES)
    accuracy = (correct / total) * 100.0
    print("=" * 72)
    print(f"ROUND 2 HELD-OUT ROUTER BENCHMARK: {correct}/{total} ({accuracy:.1f}%)")
    print("=" * 72)
    print(f"Total Queries : {total}")
    print(f"Correct       : {correct}")
    print(f"Misclassified : {len(misses)}")
    if misses:
        print("\nMisclassified Queries:")
        for m in misses:
            print(f"  [{m['index']:02d}] ({m['category']}) '{m['query']}' -> expected='{m['expected']}', actual='{m['actual']}'")
    print("=" * 72)
    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "misses": misses,
        "results": results,
    }


def test_router_holdout_benchmark_runs():
    report = run_holdout_benchmark()
    assert report["total"] == 40


if __name__ == "__main__":
    run_holdout_benchmark()
