#!/usr/bin/env python3
"""
シンプルな負荷テストスクリプト（外部ライブラリ最小限）
100人の同時ユーザーをシミュレート

実行方法:
  python3 load_test_python.py
"""

import requests
import threading
import time
import random
import sys
from datetime import datetime
from urllib.parse import urljoin
from collections import defaultdict

# テスト設定
HOST = "http://localhost:8080"
NUM_USERS = 100
TEST_DURATION = 60  # 秒
CONCURRENT_REQUESTS = 10  # 同時実行数

# 統計情報
stats = {
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "total_response_time": 0.0,
    "response_times": [],
    "errors": defaultdict(int),
}

stats_lock = threading.Lock()


def log_request(status_code, response_time, endpoint):
    """リクエスト統計を記録"""
    with stats_lock:
        stats["total_requests"] += 1
        stats["total_response_time"] += response_time
        stats["response_times"].append(response_time)

        if 200 <= status_code < 300:
            stats["successful_requests"] += 1
        else:
            stats["failed_requests"] += 1
            stats["errors"][status_code] += 1

        # 進行状況表示
        if stats["total_requests"] % 50 == 0:
            elapsed = datetime.now().strftime("%H:%M:%S")
            print(f"[{elapsed}] リクエスト数: {stats['total_requests']} | "
                  f"成功: {stats['successful_requests']} | "
                  f"失敗: {stats['failed_requests']}")


def user_behavior(user_id, start_time):
    """1ユーザーの行動をシミュレート"""
    session = requests.Session()
    team_id = user_id % 15 + 1
    team_name = f"Team{team_id}"

    # ログイン
    try:
        session.post(f"{HOST}/login", data={"team_name": team_name, "role": "team"})
    except Exception as e:
        print(f"❌ User {user_id}: ログイン失敗 - {e}")
        return

    # テスト期間中、リクエスト送信
    while time.time() - start_time < TEST_DURATION:
        try:
            # ランキング取得
            t0 = time.time()
            r = session.get(f"{HOST}/ranking")
            elapsed = time.time() - t0
            log_request(r.status_code, elapsed, "/ranking")

            # コメント取得
            t0 = time.time()
            r = session.get(f"{HOST}/api/comments?limit=50")
            elapsed = time.time() - t0
            log_request(r.status_code, elapsed, "/api/comments")

            # コメント投稿
            t0 = time.time()
            r = session.post(
                f"{HOST}/api/comment",
                data={"comment_text": f"Test comment from user {user_id}"}
            )
            elapsed = time.time() - t0
            log_request(r.status_code, elapsed, "/api/comment")

            # ランダム待機
            time.sleep(random.uniform(0.5, 2.0))

        except Exception as e:
            print(f"❌ User {user_id}: リクエスト失敗 - {e}")
            with stats_lock:
                stats["failed_requests"] += 1


def print_summary():
    """テスト結果サマリーを表示"""
    print("\n" + "="*60)
    print("📊 負荷テスト結果")
    print("="*60)
    print(f"ターゲット: {HOST}")
    print(f"同時ユーザー: {NUM_USERS}")
    print(f"テスト時間: {TEST_DURATION}秒")
    print("="*60)

    print(f"\n📈 統計:")
    print(f"  総リクエスト数: {stats['total_requests']}")
    print(f"  成功: {stats['successful_requests']}")
    print(f"  失敗: {stats['failed_requests']}")

    if stats["failed_requests"] > 0:
        print(f"\n  エラー内訳:")
        for status_code, count in sorted(stats["errors"].items()):
            print(f"    HTTP {status_code}: {count}件")

    if stats["response_times"]:
        avg_time = stats["total_response_time"] / len(stats["response_times"])
        sorted_times = sorted(stats["response_times"])
        p50 = sorted_times[len(sorted_times) // 2]
        p95 = sorted_times[int(len(sorted_times) * 0.95)]
        p99 = sorted_times[int(len(sorted_times) * 0.99)]

        print(f"\n  応答時間:")
        print(f"    平均: {avg_time*1000:.1f}ms")
        print(f"    中央値: {p50*1000:.1f}ms")
        print(f"    95%ile: {p95*1000:.1f}ms")
        print(f"    99%ile: {p99*1000:.1f}ms")

    print("\n" + "="*60)


def main():
    print("\n" + "="*60)
    print("🚀 負荷テスト開始")
    print("="*60)
    print(f"ターゲット: {HOST}")
    print(f"ユーザー数: {NUM_USERS}")
    print(f"テスト時間: {TEST_DURATION}秒")
    print(f"開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")

    start_time = time.time()

    # ユーザースレッド起動（CONCURRENT_REQUESTS ずつ）
    threads = []
    for i in range(NUM_USERS):
        t = threading.Thread(target=user_behavior, args=(i+1, start_time))
        t.daemon = True
        threads.append(t)

        # 同時実行数制限
        if len(threads) >= CONCURRENT_REQUESTS:
            for thread in threads:
                thread.start()
            threads = []

    # 残りのスレッド起動
    for thread in threads:
        thread.start()

    # テスト完了待機
    while time.time() - start_time < TEST_DURATION:
        time.sleep(1)

    print("\n✅ テスト完了待機中...\n")
    time.sleep(2)

    # 結果表示
    print_summary()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  テスト中断")
        print_summary()
        sys.exit(0)
