import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.llm import LocalLLM


HOLDOUT_QUERIES_V2 = [
    # --- 14 Casual Chitchat Queries ---
    ("hello there libra what are u doing", "chitchat", "chat"),
    ("how has your day been so far", "chitchat", "chat"),
    ("im having a rough day at work", "chitchat", "chat"),
    ("can you tell me a good bedtime story", "chitchat", "chat"),
    ("do you have a favorite color?", "chitchat", "chat"),
    ("hey buddy thanks so much for everything", "chitchat", "chat"),
    ("whats your opinion on artificial consciousness", "chitchat", "chat"),
    ("im thinking about going for a walk", "chitchat", "chat"),
    ("libra r u sleeping?", "chitchat", "chat"),
    ("give me some motivation to finish my homework", "chitchat", "chat"),
    ("lol that was actually hilarious", "chitchat", "chat"),
    ("tell me a riddle", "chitchat", "chat"),
    ("good evening hope you had a restful day", "chitchat", "chat"),
    ("what should i name my new puppy?", "chitchat", "chat"),

    # --- 13 Real-Time Queries ---
    ("what is the solana price right now", "real-time", "web_search"),
    ("who won the champions league match yesterday", "real-time", "web_search"),
    ("current apple stock price today", "real-time", "web_search"),
    ("whats the weather in new york right now", "real-time", "weather"),
    ("latest news update on the earthquake", "real-time", "web_search"),
    ("liverpool vs real madrid live score", "real-time", "web_search"),
    ("what are the top headlines today", "real-time", "web_search"),
    ("what is the price of btc right now", "real-time", "web_search"),
    ("f1 qualifying results today", "real-time", "web_search"),
    ("current weather in sydney australia", "real-time", "weather"),
    ("who won the game tonight in mlb", "real-time", "web_search"),
    ("breaking news in artificial intelligence today", "real-time", "web_search"),
    ("nfl scores today live", "real-time", "web_search"),

    # --- 13 Mixed Queries ---
    ("hey libra hows everything check the bitcoin price for me", "mixed", "web_search"),
    ("good afternoon my friend how is the weather in paris right now", "mixed", "weather"),
    ("yo whats up can you tell me who won the warriors game tonight", "mixed", "web_search"),
    ("hello there hope ur doing well whats the latest tech news today", "mixed", "web_search"),
    ("hi libra feeling good today can you write a python script for binary search", "mixed", "chat"),
    ("hey buddy long time no see check google stock price today", "mixed", "web_search"),
    ("sup how was your morning check the premier league standings", "mixed", "web_search"),
    ("good morning libra u awake? what are the top headlines this morning", "mixed", "web_search"),
    ("hey can you explain how quantum computing works in simple words", "mixed", "chat"),
    ("whats up libra can you check if it is raining in seattle rn", "mixed", "weather"),
    ("hello my friend what happened today in the stock market", "mixed", "web_search"),
    ("hi libra hope you are well why do cats purr when happy", "mixed", "chat"),
    ("hey dude how are you doing whats the live score for manchester city", "mixed", "web_search"),
]


def run_holdout_v2_benchmark() -> dict:
    """
    Runs the 40 NEW held-out queries against LocalLLM.plan(dry_run=True)
    and reports raw accuracy and every misclassified query without tuning.
    """
    llm = LocalLLM()
    correct = 0
    misses = []
    results = []

    for idx, (query, category, expected) in enumerate(HOLDOUT_QUERIES_V2, 1):
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

    total = len(HOLDOUT_QUERIES_V2)
    accuracy = (correct / total) * 100.0
    print("=" * 72)
    print(f"ROUND 4 HELD-OUT ROUTER V2 BENCHMARK: {correct}/{total} ({accuracy:.1f}%)")
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


def test_router_holdout_v2_benchmark_runs():
    report = run_holdout_v2_benchmark()
    assert report["total"] == 40


if __name__ == "__main__":
    run_holdout_v2_benchmark()
