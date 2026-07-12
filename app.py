import eventlet

eventlet.monkey_patch()

import os
import logging
from flask import Flask
from extensions import db, socketio
from controller.controllers import quiz_bp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    logger.info("Creating app...")

    instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance")
    if not os.path.exists(instance_path):
        os.makedirs(instance_path)

    app = Flask(__name__, instance_path=instance_path)
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"sqlite:///{os.path.join(instance_path, 'quiz_event.db')}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "quiz-bet-event-secret-2026"

    db.init_app(app)
    socketio.init_app(app)
    app.register_blueprint(quiz_bp)

    @app.context_processor
    def inject_team_points():
        from flask import session
        from repository import repositories
        from model.models import QuizQuestion

        team_points = 0
        is_ranking_visible = True

        total_quizzes = QuizQuestion.query.count()
        revealed_quizzes = QuizQuestion.query.filter_by(status="revealed").count()
        is_bet_visible = revealed_quizzes >= 5

        if session.get("is_admin"):
            is_bet_visible = True

        blackout_event_name = "【格付け③】箱の中身はなんだろな？（わっきー戦）"
        events = repositories.get_all_events()
        blackout_event = next(
            (e for e in events if e.event_name == blackout_event_name), None
        )

        if blackout_event and blackout_event.status == "settled":
            if not session.get("is_admin"):
                is_ranking_visible = False

        if "team_id" in session:
            team = repositories.get_team_by_id(session["team_id"])
            if team:
                team_points = team.points

        return dict(
            team_points=team_points,
            is_ranking_visible=is_ranking_visible,
            is_bet_visible=is_bet_visible,
        )

    return app


def seed_event_data():
    from model.models import (
        Team,
        QuizQuestion,
        BetEvent,
        BingoTheme,
        BetOption,
        BingoSquare,
    )

    # 1. Sync Teams 1 to 20 by ID
    for i in range(1, 21):
        team = Team.query.get(i)
        if not team:
            db.session.add(Team(team_id=i, team_name=f"チーム {i}", points=500))

    # 2. Sync 9 Bingo Themes
    bingo_themes_data = [
        "血液型が同じ",
        "出身市町村が同じ",
        "趣味が同じ人がいる",
        "好きな食べ物が同じ",
        "FREE (真ん中)",
        "持っている資格が同じ",
        "学生時代の部活が同じ",
        "最近買った高いものが同じ",
        "実は苦手なものが同じ",
    ]
    for i, text in enumerate(bingo_themes_data, 1):
        theme = BingoTheme.query.filter_by(position=i).first()
        if theme:
            theme.theme_text = text
        else:
            db.session.add(BingoTheme(position=i, theme_text=text))

    db.session.flush()
    for i in range(1, 21):
        free_square = BingoSquare.query.filter_by(team_id=i, position=5).first()
        if not free_square:
            db.session.add(
                BingoSquare(team_id=i, position=5, content="★FREE★", status="approved")
            )

    # 3. Sync Quiz Questions
    quiz_data = [
        {
            "num": 1,
            "text": "全社員が、Excelを使いながら最も「自社への愛」を感じる瞬間は、当然「Shiftキー」を押すときですよね。 では、Excelで「Shiftキーを押しながら, F11キー」を叩くと、一体何が起きるでしょう？",
            "a": "無駄な工数の徹底的な削減",
            "b": "新たなフィールドの創出",
            "c": "自身の限界を超えるキャリアアップ",
            "d": "不具合の出ない完璧な品質保証",
            "correct": "B",
            "is_multiple": False,
        },
        {
            "num": 2,
            "text": "伏せたところに入る言葉は？",
            "a": "運命の恋人に出会う",
            "b": "隕石が衝突してくる",
            "c": "流れ星を捕まえる",
            "d": "丹下さんができないと言う",
            "correct": "A",
            "is_multiple": False,
        },
        {
            "num": 3,
            "text": "この中に含まれていない曲は？",
            "a": "天体観測",
            "b": "好きすぎて滅!",
            "c": "怪獣の花唄",
            "d": "立ち上がリーヨ",
            "correct": "B",
            "is_multiple": False,
        },
        {
            "num": 4,
            "text": "顔合成クイズ",
            "a": "A",
            "b": "B",
            "c": "C",
            "d": "D",
            "correct": "A",
            "is_multiple": False,
        },
        {
            "num": 5,
            "text": "この中でまんぷくんはどれ？",
            "a": "左上",
            "b": "右上",
            "c": "左下",
            "d": "右下",
            "correct": "ACD",
            "is_multiple": True,
        },
    ]

    current_nums = [q_item["num"] for q_item in quiz_data]
    QuizQuestion.query.filter(~QuizQuestion.question_num.in_(current_nums)).delete(
        synchronize_session=False
    )

    for q_item in quiz_data:
        q = QuizQuestion.query.filter_by(question_num=q_item["num"]).first()
        if q:
            q.question_text = q_item["text"]
            q.choice_a = q_item["a"]
            q.choice_b = q_item["b"]
            q.choice_c = q_item["c"]
            q.choice_d = q_item["d"]
            q.correct_choice = q_item["correct"]
            q.is_multiple_choice = q_item["is_multiple"]
        else:
            db.session.add(
                QuizQuestion(
                    question_num=q_item["num"],
                    question_text=q_item["text"],
                    choice_a=q_item["a"],
                    choice_b=q_item["b"],
                    choice_c=q_item["c"],
                    choice_d=q_item["d"],
                    correct_choice=q_item["correct"],
                    is_multiple_choice=q_item["is_multiple"],
                )
            )

    # 4. Sync Bet Events (格付け①のルールと倍率を更新)
    events_data = [
        {
            "name": "【格付け①】ハイチュウの味を何問当てられるか？",
            "options": [
                ("0問正解", 0.0),
                ("1問正解", 0.8),
                ("2問正解", 1.2),
                ("全問正解", 1.5),
            ],
        },
        {
            "name": "【格付け②】箱の中身はなんだろな？（あべりこ戦）",
            "options": [
                ("全滅", 1.5),
                ("Aのみ正解", 2.0),
                ("Bのみ正解", 2.5),
                ("Cのみ正解", 3.5),
                ("A & B 正解", 4.0),
                ("A & C 正解", 5.0),
                ("B & C 正解", 6.5),
                ("3つ全て正解", 10.0),
            ],
        },
        {
            "name": "【格付け③】箱の中身はなんだろな？（わっきー戦）",
            "options": [
                ("全滅", 1.5),
                ("Aのみ正解", 2.0),
                ("Bのみ正解", 2.5),
                ("Cのみ正解", 3.5),
                ("A & B 正解", 4.0),
                ("A & C 正解", 5.0),
                ("B & C 正解", 6.5),
                ("3つ全て正解", 10.0),
            ],
        },
    ]

    for e_item in events_data:
        event = BetEvent.query.filter_by(event_name=e_item["name"]).first()
        if not event:
            event = BetEvent(event_name=e_item["name"], multiplier=0.0)
            db.session.add(event)
            db.session.flush()

        existing_options = {
            opt.option_text: opt
            for opt in BetOption.query.filter_by(event_id=event.event_id).all()
        }
        for opt_text, mult in e_item["options"]:
            if opt_text in existing_options:
                existing_options[opt_text].multiplier = mult
            else:
                db.session.add(
                    BetOption(
                        event_id=event.event_id, option_text=opt_text, multiplier=mult
                    )
                )

    db.session.commit()
    logger.info("Sync completed successfully.")


app = create_app()

if __name__ == "__main__":
    with app.app_context():
        seed_event_data()
    socketio.run(app, debug=True, port=8080)
