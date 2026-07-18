#!/bin/bash

# 簡単な負荷テスト - 100人の同時ユーザーをシミュレート
# 使用方法: bash load_test.sh

HOST="http://localhost:8080"
CONCURRENT_USERS=100
TEST_DURATION=60  # 秒

echo "=================================================="
echo "📊 負荷テスト開始"
echo "=================================================="
echo "ターゲット: $HOST"
echo "同時ユーザー数: $CONCURRENT_USERS"
echo "テスト時間: ${TEST_DURATION}秒"
echo "=================================================="
echo ""

# メモリ使用量の監視
echo "📈 テスト中のメモリ使用量:"
echo "=================================================="

# 開始時刻
START_TIME=$(date +%s)
END_TIME=$((START_TIME + TEST_DURATION))

# バックグラウンドプロセスの PID 配列
PIDS=()

# メインテストループ
while [ $(date +%s) -lt $END_TIME ]; do
    # 並行リクエスト実行
    for i in $(seq 1 $CONCURRENT_USERS); do
        (
            TEAM_ID=$((i % 15 + 1))
            TEAM_NAME="Team$TEAM_ID"

            # ランキング取得
            curl -s -b "session.txt" \
                "$HOST/ranking" > /dev/null 2>&1

            # コメント取得
            curl -s -b "session.txt" \
                "$HOST/api/comments?limit=50" > /dev/null 2>&1

            # コメント投稿
            curl -s -b "session.txt" -X POST \
                -d "comment_text=Test comment $i" \
                "$HOST/api/comment" > /dev/null 2>&1

            # ランキング再取得
            curl -s -b "session.txt" \
                "$HOST/ranking" > /dev/null 2>&1
        ) &
        PIDS+=($!)
    done

    # メモリ使用量表示
    ELAPSED=$(($(date +%s) - START_TIME))
    if command -v ps &> /dev/null; then
        MEM_MB=$(ps aux | grep -E "python|flask|gunicorn" | grep -v grep | awk '{sum+=$6} END {print sum/1024}')
        echo "  [$ELAPSED秒経過] メモリ使用量: ${MEM_MB:.1f} MB"
    fi

    # 全プロセスが完了するまで待機
    for pid in "${PIDS[@]}"; do
        wait $pid 2>/dev/null
    done
    PIDS=()

    sleep 1
done

echo ""
echo "=================================================="
echo "✅ テスト完了"
echo "=================================================="
echo ""

# 最終メモリ使用量
if command -v ps &> /dev/null; then
    echo "📊 最終メモリ使用量:"
    MEM_MB=$(ps aux | grep -E "python|flask|gunicorn" | grep -v grep | awk '{sum+=$6} END {print sum/1024}')
    echo "  総メモリ: ${MEM_MB:.1f} MB (制限: 512 MB)"

    if (( $(echo "$MEM_MB > 512" | bc -l) )); then
        echo "  ⚠️  警告: メモリ制限を超えています！"
    else
        echo "  ✅ メモリ制限内"
    fi
fi
