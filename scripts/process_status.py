from __future__ import annotations

import argparse
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    try:
        media = conn.execute("select count(*) from media_items").fetchone()[0]
        results = conn.execute("select count(*) from adult_results").fetchone()[0]
        decisions = conn.execute(
            "select decision, count(*) from adult_results group by decision order by decision"
        ).fetchall()
        errors = conn.execute("select count(*) from adult_results where decision = 'error'").fetchone()[0]
    finally:
        conn.close()

    print(f"db={args.db}")
    print(f"media_items={media}")
    print(f"adult_results={results}")
    print(f"unprocessed={media - results}")
    print(f"errors={errors}")
    for decision, count in decisions:
        print(f"decision.{decision}={count}")


if __name__ == "__main__":
    main()
