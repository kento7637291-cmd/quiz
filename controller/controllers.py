import re
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, make_response
from functools import wraps
from usecase import usecases
from repository import repositories
from extensions import db, socketio
from model.models import QuizQuestion, QuizSubmission, TeamBet, BingoSquare, Team

quiz_bp = Blueprint("quiz", __name__)


def verify_window_id():
    """ウィンドウID が一致しているかチェック。複数ウィンドウでのセッション混在を防止"""
    stored_window_id = session.get("window_id")
    if not stored_window_id:
        return True  # ログイン前は検査しない

    request_window_id = request.form.get("window_id") or request.args.get("window_id")
    if request_window_id and request_window_id != stored_window_id:
        # 異なるウィンドウからのアクセス→セッションをクリア
        session.clear()
        return False
    return True


def team_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not verify_window_id():
            flash("セッションの検証に失敗しました。再度ログインしてください。", "warning")
            return redirect(url_for("quiz.login"))

        if "team_id" not in session and not session.get("is_admin"):
            flash("チームを選択するか、管理者としてログインしてください。", "warning")
            return redirect(url_for("quiz.login"))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not verify_window_id():
            flash("セッションの検証に失敗しました。再度ログインしてください。", "warning")
            return redirect(url_for("quiz.login"))

        if not session.get("is_admin"):
            flash("管理者権限が必要です。", "danger")
            return redirect(url_for("quiz.login"))
        return f(*args, **kwargs)

    return decorated_function


# 全テンプレートに状態フラグを自動注入
@quiz_bp.context_processor
def inject_game_status():
    q1 = QuizQuestion.query.filter_by(question_num=1).first()
    is_q1_activated = q1.status in ["active", "revealed"] if q1 else False

    q5 = QuizQuestion.query.filter_by(question_num=5).first()
    is_q5_revealed = q5.status == "revealed" if q5 else False

    from model.models import BingoTheme
    bingo_theme = BingoTheme.query.filter_by(position=1).first()
    is_bingo_activated = bingo_theme.is_active if bingo_theme else False

    return dict(is_q1_activated=is_q1_activated, is_q5_revealed=is_q5_revealed, is_bingo_activated=is_bingo_activated)


# Route: Index Redirect
@quiz_bp.route("/", methods=["GET"])
def index():
    if session.get("is_admin"):
        return redirect(url_for("quiz.admin"))
    if "team_id" in session:
        return redirect(url_for("quiz.bingo"))
    return redirect(url_for("quiz.login"))


@quiz_bp.route("/health")
def health():
    return {"status": "ok"}, 200


# Route: Login / Team Selection
@quiz_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role")
        if role == "admin":
            admin_password = request.form.get("admin_password")
            if admin_password != "admin":
                flash("管理者パスワードが正しくありません。", "danger")
                return redirect(url_for("quiz.login"))

            session.clear()
            session.permanent = True
            session["is_admin"] = True
            session["name"] = "管理者"
            session["window_id"] = str(uuid.uuid4())
            session.modified = True
            flash("管理者としてログインしました。", "success")
            resp = make_response(redirect(url_for("quiz.admin")))
            resp.set_cookie("session", "", max_age=0)  # 古いセッションクッキーをクリア
            return resp
        else:
            team_id = request.form.get("team_id", type=int)
            team_name_suffix = request.form.get("team_name_suffix", "").strip()
            team = repositories.get_team_by_id(team_id)
            if team:
                # ユーザーがテキストボックスに入力した文字列がある場合
                if team_name_suffix:
                    # 「チーム X」を付けず、入力された文字列そのものをそのままチーム名にする
                    team.team_name = team_name_suffix
                    db.session.commit()

                session.clear()
                session.permanent = True
                session["team_id"] = team.team_id
                session["team_name"] = team.team_name
                session["window_id"] = str(uuid.uuid4())
                session.modified = True
                flash(f"{team.team_name}として参加しました！", "success")
                resp = make_response(redirect(url_for("quiz.bingo")))
                resp.set_cookie("session", "", max_age=0)  # 古いセッションクッキーをクリア
                return resp

    teams = repositories.get_all_teams()
    return render_template("login.html", teams=teams)


# Admin Action: Bulk Approve Bingo Squares
@quiz_bp.route("/admin/bingo/approve_all", methods=["POST"])
@admin_required
def admin_approve_bingo_all():
    pending = repositories.get_pending_bingo_squares()
    count = 0
    for s in pending:
        success, _ = usecases.approve_bingo_square(s.square_id, "approved")
        if success:
            count += 1

    if count > 0:
        socketio.emit("bingo_update", {}, namespace="/")
        flash(f"{count} 件の回答を一括承認しました。", "success")
    else:
        flash("承認待ちの回答はありません。", "info")
    return redirect(url_for("quiz.admin"))


@quiz_bp.route("/admin/bingo/approve_team/<int:team_id>", methods=["POST"])
@admin_required
def admin_approve_bingo_team(team_id):
    pending = repositories.get_bingo_squares_by_team(team_id)
    count = 0
    for s in pending:
        if s.status == "pending":
            success, _ = usecases.approve_bingo_square(s.square_id, "approved")
            if success:
                count += 1

    if count > 0:
        socketio.emit("bingo_update", {}, namespace="/")
        flash(f"チームの回答 {count} 件を一括承認しました。", "success")
    else:
        flash("このチームの承認待ち回答はありません。", "info")
    return redirect(url_for("quiz.admin"))


# Route: Logout
@quiz_bp.route("/logout")
def logout():
    session.clear()
    flash("ログアウトしました。", "info")
    return redirect(url_for("quiz.login"))


# Route: Bingo (Common Points Grid)
@quiz_bp.route("/bingo", methods=["GET", "POST"])
@team_required
def bingo():
    team_id = session.get("team_id")
    if request.method == "POST":
        if not team_id:
            flash("管理者アカウントでは投稿できません。", "warning")
            return redirect(url_for("quiz.bingo"))

        position = request.form.get("position", type=int)
        content = request.form.get("content")
        success, message = usecases.submit_bingo_answer(team_id, position, content)
        if success:
            socketio.emit(
                "bingo_submitted",
                {"team_id": team_id, "position": position},
                namespace="/",
            )
            flash(message, "success")
        else:
            flash(message, "danger")
        return redirect(url_for("quiz.bingo"))

    themes = repositories.get_all_bingo_themes()
    squares = []
    if team_id:
        squares = repositories.get_bingo_squares_by_team(team_id)

    square_map = {s.position: s for s in squares}
    return render_template("bingo.html", themes=themes, square_map=square_map)


# Route: Live 4-Choice Quiz Answering
@quiz_bp.route("/quiz", methods=["GET", "POST"])
@team_required
def quiz_view():
    team_id = session.get("team_id")

    if request.method == "POST":
        if not team_id:
            flash("管理者アカウントでは回答を送信できません。", "warning")
            return redirect(url_for("quiz.quiz_view"))

        quiz_id = request.form.get("quiz_id", type=int)
        choice = request.form.get("choice")

        success, message = usecases.submit_quiz_answer(quiz_id, team_id, choice)
        if success:
            socketio.emit(
                "quiz_submitted",
                {"team_id": team_id, "quiz_id": quiz_id},
                namespace="/",
            )
            flash(message, "success")
        else:
            flash(message, "danger")
        return redirect(url_for("quiz.quiz_view"))

    active_q = repositories.get_active_question()
    submitted = None

    if active_q and team_id:
        submitted = repositories.get_submission_by_team_and_quiz(
            active_q.quiz_id, team_id
        )

    last_revealed = repositories.get_last_revealed_question()
    last_sub = None
    if last_revealed and team_id:
        last_sub = repositories.get_submission_by_team_and_quiz(
            last_revealed.quiz_id, team_id
        )

    return render_template(
        "quiz.html",
        question=active_q,
        submitted=submitted,
        last_revealed=last_revealed,
        last_sub=last_sub,
    )


# Route: Betting Sub-event
@quiz_bp.route("/bet", methods=["GET", "POST"])
@team_required
def bet_view():
    team_id = session.get("team_id")

    if request.method == "POST":
        if not team_id:
            flash("管理者アカウントではベットできません。", "warning")
            return redirect(url_for("quiz.bet_view"))

        event_id = request.form.get("event_id", type=int)
        bet_points = request.form.get("bet_points", type=int)
        prediction = request.form.get("prediction")
        multiplier = request.form.get("multiplier", type=float, default=2.0)

        success, message = usecases.place_bet(
            event_id, team_id, bet_points, prediction, multiplier
        )
        if success:
            socketio.emit(
                "bet_submitted",
                {"team_id": team_id, "event_id": event_id},
                namespace="/",
            )
            flash(message, "success")
        else:
            flash(message, "danger")
        return redirect(url_for("quiz.bet_view"))

    active_event = repositories.get_active_bet_event()
    submitted_bet = None
    options = []

    if active_event:
        options = repositories.get_options_for_event(active_event.event_id)
        if team_id:
            submitted_bet = repositories.get_bet_by_event_and_team(
                active_event.event_id, team_id
            )

    return render_template(
        "bet.html",
        event=active_event,
        submitted_bet=submitted_bet,
        options=options,
    )


# Route: Leaderboard / Rankings
@quiz_bp.route("/ranking")
def ranking():
    teams = repositories.get_all_teams()
    return render_template("ranking.html", teams=teams)


# Route: Administrator Dashboard
@quiz_bp.route("/admin", methods=["GET"])
@admin_required
def admin():
    questions = repositories.get_all_questions()
    events = repositories.get_all_events()
    teams = repositories.get_all_teams()
    pending_squares = repositories.get_pending_bingo_squares()
    themes = repositories.get_all_bingo_themes()

    active_event = repositories.get_active_bet_event()
    bets = []
    if active_event:
        bets = repositories.get_bets_for_event(active_event.event_id)

    options_map = {}
    for e in events:
        options_map[e.event_id] = repositories.get_options_for_event(e.event_id)

    team_map = {t.team_id: t.team_name for t in teams}
    operation_logs = repositories.get_recent_operation_logs(20)

    return render_template(
        "admin.html",
        questions=questions,
        events=events,
        teams=teams,
        pending_squares=pending_squares,
        themes=themes,
        active_event=active_event,
        bets=bets,
        options_map=options_map,
        team_map=team_map,
        operation_logs=operation_logs,
    )


# Admin Action: Approve/Reject Bingo Square
@quiz_bp.route("/admin/bingo/<int:square_id>/approve", methods=["POST"])
@admin_required
def admin_approve_bingo(square_id: int):
    status = request.form.get("status")
    success, message = usecases.approve_bingo_square(square_id, status)
    if success:
        socketio.emit(
            "bingo_update", {"square_id": square_id, "status": status}, namespace="/"
        )

        # ビンゴ達成判定
        square = repositories.get_bingo_square_by_id(square_id)
        if square and status == "approved":
            team = repositories.get_team_by_id(square.team_id)
            current_squares = repositories.get_bingo_squares_by_team(square.team_id)
            approved_positions = {s.position for s in current_squares if s.status == "approved"} | {5}

            from usecase.usecases import calculate_bingo_lines
            lines = calculate_bingo_lines(approved_positions)

            # ビンゴ達成（3ライン以上）
            if lines >= 1:
                socketio.emit(
                    "bingo_complete",
                    {"team_id": square.team_id, "team_name": team.team_name, "lines": lines},
                    namespace="/"
                )

        repositories.add_operation_log("ビンゴマス承認", f"{team.team_name} #{ square.position if square else '?'}")
        flash(message, "success")
    else:
        flash(message, "danger")
    return redirect(url_for("quiz.admin"))


# Admin Action: Start/Activate Quiz
@quiz_bp.route("/admin/quiz/<int:quiz_id>/activate", methods=["POST"])
@admin_required
def admin_activate_quiz(quiz_id: int):
    active = repositories.get_active_question()
    if active:
        repositories.update_question_status(active.quiz_id, "hidden")

    repositories.update_question_status(quiz_id, "active")
    socketio.emit(
        "quiz_update", {"status": "active", "quiz_id": quiz_id}, namespace="/"
    )
    repositories.add_operation_log("クイズ受付開始", f"第{quiz_id}問")
    flash(f"第 {quiz_id} 問の回答受付を開始しました！", "success")
    return redirect(url_for("quiz.admin"))


# Admin Action: Reveal Correct Answer of Quiz
@quiz_bp.route("/admin/quiz/<int:quiz_id>/reveal", methods=["POST"])
@admin_required
def admin_reveal_quiz(quiz_id: int):
    award_points = request.form.get("award_points", default=100, type=int)
    success, message = usecases.reveal_quiz_answer(quiz_id, award_points)
    if success:
        socketio.emit(
            "quiz_update", {"status": "revealed", "quiz_id": quiz_id}, namespace="/"
        )
        repositories.add_operation_log("クイズ正解発表", f"第{quiz_id}問、{award_points}pt付与")
        flash(message, "success")
    else:
        flash(message, "danger")
    return redirect(url_for("quiz.admin"))


# Admin Action: Set/Activate Bet Event Status
@quiz_bp.route("/admin/event/<int:event_id>/status", methods=["POST"])
@admin_required
def admin_set_event_status(event_id: int):
    status = request.form.get("status")
    if status == "betting":
        active = repositories.get_active_bet_event()
        if active:
            repositories.update_event_status(active.event_id, "waiting")

    repositories.update_event_status(event_id, status)
    socketio.emit(
        "event_update", {"status": status, "event_id": event_id}, namespace="/"
    )
    flash(f"イベントステータスを {status} に変更しました。", "success")
    return redirect(url_for("quiz.admin"))


# Admin Action: Settle Payout for Bet Event
@quiz_bp.route("/admin/event/<int:event_id>/settle", methods=["POST"])
@admin_required
def admin_settle_event(event_id: int):
    event = repositories.get_event_by_id(event_id)
    if not event:
        flash("イベントが見つかりません。", "danger")
        return redirect(url_for("quiz.admin"))

    if "格付け①" in event.event_name:
        try:
            bets = repositories.get_bets_for_event(event_id)

            correct_map = {
                "赤色": request.form.get("flavor_red", "巨峰").strip(),
                "青色": request.form.get("flavor_blue", "イチゴ").strip(),
                "緑色": request.form.get("flavor_green", "イチゴ").strip(),
                "黄色": request.form.get("flavor_yellow", "グレープ").strip(),
            }

            for bet in bets:
                pred_text = bet.prediction or ""
                correct_count = 0

                parts = [p.strip() for p in pred_text.split(",") if ":" in p]
                for part in parts:
                    color, flavor = part.split(":", 1)
                    if color in correct_map and flavor == correct_map[color]:
                        correct_count += 1

                if correct_count == 0:
                    current_mult = 0.0
                    bet.status = "lost"
                elif correct_count == 1:
                    current_mult = 0.8
                    bet.status = "won"
                elif correct_count == 2:
                    current_mult = 1.2
                    bet.status = "won"
                else:
                    current_mult = 1.5
                    bet.status = "won"

                if current_mult > 0:
                    team = repositories.get_team_by_id(bet.team_id)
                    payout = int(bet.bet_points * current_mult)
                    team.points += payout

            event.status = "settled"
            db.session.commit()
            socketio.emit(
                "event_update",
                {"status": "settled", "event_id": event_id},
                namespace="/",
            )
            flash(
                f"【格付け①】の清算が完了しました！管理者が入力した正解レシピに基づき、全チームの合致数を判定して自動配点しました。",
                "success",
            )
        except Exception as e:
            db.session.rollback()
            flash(f"清算エラー: {str(e)}", "danger")

    else:
        winning_prediction = request.form.get("winning_prediction")
        success, message = usecases.settle_bet_event(event_id, winning_prediction)
        if success:
            socketio.emit(
                "event_update",
                {"status": "settled", "event_id": event_id},
                namespace="/",
            )
            flash(message, "success")
        else:
            flash(message, "danger")

    return redirect(url_for("quiz.admin"))


# Admin Action: Reset Game Data / Points
@quiz_bp.route("/admin/reset", methods=["POST"])
@admin_required
def admin_reset():
    try:
        QuizSubmission.query.delete()
        TeamBet.query.delete()
        BingoSquare.query.delete()

        Team.query.filter(Team.team_id > 15).delete()
        db.session.flush()

        with db.session.no_autoflush:
            for team in Team.query.all():
                team.points = 500
                team.team_name = f"チーム {team.team_id}"

        for q in repositories.get_all_questions():
            q.status = "hidden"

        for e in repositories.get_all_events():
            e.status = "waiting"

        from model.models import BingoTheme
        for theme in BingoTheme.query.all():
            theme.is_active = False

        db.session.commit()
        socketio.emit("reset_all", {}, namespace="/")
        flash(
            "すべての企画データをリセットし、16チーム目以降の不要データを削除した上で、各チーム（1〜15）の持ち点とチーム名を初期化しました。",
            "success",
        )
    except Exception as e:
        db.session.rollback()
        flash(f"リセットエラー: {str(e)}", "danger")
    return redirect(url_for("quiz.admin"))


@quiz_bp.route("/admin/team/points", methods=["POST"])
@admin_required
def admin_update_points():
    team_id = request.form.get("team_id", type=int)
    points = request.form.get("points", type=int)
    repositories.update_team_points(team_id, points)
    socketio.emit(
        "points_update", {"team_id": team_id, "points": points}, namespace="/"
    )
    flash(f"チームの持ち点を {points}pt に更新しました。", "success")
    return redirect(url_for("quiz.admin"))


@quiz_bp.route("/admin/quiz/<int:quiz_id>/update", methods=["POST"])
@admin_required
def admin_update_quiz(quiz_id):
    q = repositories.get_question_by_id(quiz_id)
    if q:
        q.question_text = request.form.get("question_text")
        q.choice_a = request.form.get("choice_a")
        q.choice_b = request.form.get("choice_b")
        q.choice_c = request.form.get("choice_c")
        q.choice_d = request.form.get("choice_d")
        q.correct_choice = request.form.get("correct_choice")
        db.session.commit()
        flash(f"第 {q.question_num} 問を更新しました。", "success")
    return redirect(url_for("quiz.admin"))


@quiz_bp.route("/admin/bingo/theme", methods=["POST"])
@admin_required
def admin_update_bingo_theme():
    position = request.form.get("position", type=int)
    theme_text = request.form.get("theme_text")
    repositories.update_bingo_theme(position, theme_text)
    flash(f"ビンゴ第 {position} マスのお題を更新しました。", "success")
    return redirect(url_for("quiz.admin"))


@quiz_bp.route("/admin/event/<int:event_id>/update", methods=["POST"])
@admin_required
def admin_update_event(event_id):
    event = repositories.get_event_by_id(event_id)
    if event:
        event.event_name = request.form.get("event_name")
        event.multiplier = request.form.get("multiplier", type=float)
        db.session.commit()
        flash(f"イベント「{event.event_name}」を更新しました。", "success")
    return redirect(url_for("quiz.admin"))


# Admin Action: Add Team
@quiz_bp.route("/admin/team/add", methods=["POST"])
@admin_required
def admin_add_team():
    teams = repositories.get_all_teams()
    new_team_id = max([t.team_id for t in teams]) + 1 if teams else 1
    new_team = repositories.add_team(f"チーム {new_team_id}")
    socketio.emit(
        "team_added",
        {"team_id": new_team.team_id, "team_name": new_team.team_name},
        namespace="/",
    )
    flash(f"チーム {new_team_id} を追加しました。", "success")
    return redirect(url_for("quiz.admin"))


# Admin Action: Remove Team
@quiz_bp.route("/admin/team/remove", methods=["POST"])
@admin_required
def admin_remove_team():
    teams = repositories.get_all_teams()
    if len(teams) <= 1:
        flash("最後のチームは削除できません。", "danger")
        return redirect(url_for("quiz.admin"))

    success = repositories.remove_last_team()
    if success:
        socketio.emit("team_removed", {}, namespace="/")
        flash("最後のチームを削除しました。", "success")
    else:
        flash("初期チーム（1〜15）は削除できません。追加したチームのみ削除可能です。", "warning")
    return redirect(url_for("quiz.admin"))


# Admin Action: Start Bingo Game
@quiz_bp.route("/admin/bingo/start", methods=["POST"])
@admin_required
def admin_start_bingo():
    from model.models import BingoTheme

    themes = BingoTheme.query.all()
    for theme in themes:
        theme.is_active = True

    db.session.commit()
    socketio.emit("bingo_start", {}, namespace="/")
    flash("Mind SHIFT BINGOをスタートさせました！", "success")
    return redirect(url_for("quiz.admin"))


# Admin Action: Stop Bingo Game
@quiz_bp.route("/admin/bingo/stop", methods=["POST"])
@admin_required
def admin_stop_bingo():
    from model.models import BingoTheme

    themes = BingoTheme.query.all()
    for theme in themes:
        theme.is_active = False

    db.session.commit()
    socketio.emit("bingo_stop", {}, namespace="/")
    repositories.add_operation_log("Mind SHIFT BINGO停止")
    flash("Mind SHIFT BINGOを停止させました。", "success")
    return redirect(url_for("quiz.admin"))


# Admin Action: Broadcast Message to All Teams
@quiz_bp.route("/admin/broadcast", methods=["POST"])
@admin_required
def admin_broadcast():
    message = request.form.get("message", "").strip()
    if not message:
        flash("メッセージを入力してください。", "danger")
        return redirect(url_for("quiz.admin"))

    socketio.emit("broadcast", {"message": message}, namespace="/")
    repositories.add_operation_log("全チーム告知", f"メッセージ: {message[:50]}")
    flash(f"全チームに告知を送信しました: {message}", "success")
    return redirect(url_for("quiz.admin"))


# Admin Action: Rollback Quiz Status
@quiz_bp.route("/admin/quiz/<int:quiz_id>/rollback", methods=["POST"])
@admin_required
def admin_rollback_quiz(quiz_id: int):
    q = repositories.get_question_by_id(quiz_id)
    if not q:
        flash("問題が見つかりません。", "danger")
        return redirect(url_for("quiz.admin"))

    old_status = q.status
    if q.status == "revealed":
        q.status = "hidden"
    elif q.status == "active":
        q.status = "hidden"
    else:
        flash("戻せる状態ではありません。", "warning")
        return redirect(url_for("quiz.admin"))

    db.session.commit()
    repositories.add_operation_log(f"クイズロールバック", f"第{q.question_num}問: {old_status} → {q.status}")
    socketio.emit("quiz_update", {"status": "hidden", "quiz_id": quiz_id}, namespace="/")
    flash(f"第{q.question_num}問を {old_status} から {q.status} に戻しました。", "success")
    return redirect(url_for("quiz.admin"))


# Admin Action: Rollback Event Status
@quiz_bp.route("/admin/event/<int:event_id>/rollback", methods=["POST"])
@admin_required
def admin_rollback_event(event_id: int):
    event = repositories.get_event_by_id(event_id)
    if not event:
        flash("イベントが見つかりません。", "danger")
        return redirect(url_for("quiz.admin"))

    old_status = event.status
    if event.status == "settled":
        event.status = "closed"
    elif event.status == "closed":
        event.status = "betting"
    else:
        flash("戻せる状態ではありません。", "warning")
        return redirect(url_for("quiz.admin"))

    db.session.commit()
    repositories.add_operation_log("ベットイベントロールバック", f"{event.event_name}: {old_status} → {event.status}")
    socketio.emit("event_update", {"status": event.status, "event_id": event_id}, namespace="/")
    flash(f"{event.event_name} を {old_status} から {event.status} に戻しました。", "success")
    return redirect(url_for("quiz.admin"))


# Admin Action: Start Bet Countdown
@quiz_bp.route("/admin/event/<int:event_id>/countdown/<int:seconds>", methods=["POST"])
@admin_required
def admin_start_countdown(event_id: int, seconds: int):
    event = repositories.get_event_by_id(event_id)
    if not event:
        flash("イベントが見つかりません。", "danger")
        return redirect(url_for("quiz.admin"))

    socketio.emit("bet_countdown", {"seconds": seconds}, namespace="/")
    repositories.add_operation_log("ベットカウントダウン開始", f"{event.event_name}: {seconds}秒")
    flash(f"{event.event_name} のカウントダウンを開始しました。", "success")
    return redirect(url_for("quiz.admin"))
