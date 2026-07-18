"""
負荷テスト用スクリプト - Locust を使用
100人の同時ユーザーをシミュレート

実行方法：
  locust -f load_test.py --host=http://localhost:8080 -u 100 -r 10 --run-time 5m

オプション：
  -u 100       : 100人のユーザー
  -r 10        : 毎秒10人ずつ増やす
  --run-time 5m : 5分間実行
"""

from locust import HttpUser, task, between, events
from locust.contrib.fasthttp import FastHttpUser
import json
import random
import time
from datetime import datetime

# テスト用のチーム情報
TEAM_IDS = list(range(1, 16))  # チームID 1-15
TEAM_NAMES = [f"Team{i}" for i in TEAM_IDS]


class QuizUser(FastHttpUser):
    """参加者用ユーザーシミュレーション"""
    wait_time = between(2, 5)  # 2-5秒のランダムウェイト

    def on_start(self):
        """ユーザーセッション開始時に実行"""
        self.team_id = random.choice(TEAM_IDS)
        self.team_name = f"Team{self.team_id}"
        self.session_id = None

        # ログイン
        self.login()

    def login(self):
        """ログイン処理"""
        response = self.client.post(
            "/login",
            data={
                "team_name": self.team_name,
                "role": "team"
            },
            catch_response=True
        )
        if response.status_code == 302:  # リダイレクト
            response.success()
        else:
            response.failure(f"Login failed with status {response.status_code}")

    @task(5)
    def view_ranking(self):
        """ランキングページを表示"""
        self.client.get(
            "/ranking",
            name="/ranking",
            catch_response=True
        )

    @task(3)
    def get_comments(self):
        """コメント履歴を取得"""
        self.client.get(
            "/api/comments?limit=50",
            name="/api/comments",
            catch_response=True
        )

    @task(2)
    def post_comment(self):
        """コメントを投稿"""
        comment_text = random.choice([
            "頑張れ！",
            "楽しい〜",
            "最高！",
            "いいね！",
            "応援してるぞ",
            "あと少し！",
            "頑張ろう",
            "素晴らしい"
        ])

        response = self.client.post(
            "/api/comment",
            data={"comment_text": comment_text},
            name="/api/comment",
            catch_response=True
        )
        if response.status_code == 200:
            response.success()
        else:
            response.failure(f"Comment post failed: {response.status_code}")

    @task(2)
    def view_quiz(self):
        """クイズページを表示"""
        self.client.get(
            "/quiz",
            name="/quiz",
            catch_response=True
        )

    @task(1)
    def view_bingo(self):
        """ビンゴページを表示"""
        self.client.get(
            "/bingo",
            name="/bingo",
            catch_response=True
        )

    @task(1)
    def view_bet(self):
        """ベットページを表示"""
        self.client.get(
            "/bet",
            name="/bet",
            catch_response=True
        )


class AdminUser(FastHttpUser):
    """管理者用ユーザーシミュレーション（1人のみ）"""
    wait_time = between(10, 15)

    def on_start(self):
        """管理者ログイン"""
        self.login()

    def login(self):
        """管理者ログイン"""
        response = self.client.post(
            "/login_admin",
            data={"password": "admin"},
            catch_response=True
        )
        if response.status_code == 302:
            response.success()
        else:
            response.failure(f"Admin login failed: {response.status_code}")

    @task(2)
    def view_admin_panel(self):
        """管理画面を表示"""
        self.client.get(
            "/admin",
            name="/admin",
            catch_response=True
        )

    @task(1)
    def broadcast_message(self):
        """全チーム告知を送信"""
        response = self.client.post(
            "/admin/broadcast",
            data={
                "message": f"Test message at {datetime.now().strftime('%H:%M:%S')}"
            },
            name="/admin/broadcast",
            catch_response=True
        )
        if response.status_code == 302:
            response.success()
        else:
            response.failure(f"Broadcast failed: {response.status_code}")


# テスト統計用
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n" + "="*60)
    print("📊 負荷テスト開始")
    print("="*60)
    print(f"ターゲット: {environment.host}")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n" + "="*60)
    print("📊 負荷テスト終了")
    print("="*60)
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # テスト結果サマリー
    print("\n📈 テスト結果:")
    print(f"  総リクエスト: {environment.stats.total.num_requests}")
    print(f"  成功: {environment.stats.total.num_none_requests}")
    print(f"  失敗: {environment.stats.total.num_failures}")
    print(f"  平均応答時間: {environment.stats.total.avg_response_time:.0f}ms")
    print(f"  95%ile: {environment.stats.total.get_response_time_percentile(0.95):.0f}ms")
    print(f"  99%ile: {environment.stats.total.get_response_time_percentile(0.99):.0f}ms")
    print()
