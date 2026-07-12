from extensions import db


class Team(db.Model):
    __tablename__ = "teams"

    team_id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(50), unique=True, nullable=False)
    points = db.Column(db.Integer, default=500, nullable=False)  # Start with 500pt

    submissions = db.relationship(
        "QuizSubmission", backref="team", cascade="all, delete-orphan"
    )
    bets = db.relationship("TeamBet", backref="team", cascade="all, delete-orphan")
    squares = db.relationship(
        "BingoSquare", backref="team", cascade="all, delete-orphan"
    )


class BingoTheme(db.Model):
    __tablename__ = "bingo_themes"

    theme_id = db.Column(db.Integer, primary_key=True)
    position = db.Column(
        db.Integer, unique=True, nullable=False
    )  # 1 to 9 (1:top-left, ..., 9:bottom-right)
    theme_text = db.Column(
        db.String(255), nullable=False
    )  # Question/Theme for this square


class BingoSquare(db.Model):
    __tablename__ = "bingo_squares"

    square_id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(
        db.Integer, db.ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False
    )
    position = db.Column(db.Integer, nullable=False)  # 1 to 9
    content = db.Column(db.String(255), nullable=False)  # Team's answer/common point
    status = db.Column(
        db.String(20), default="pending", nullable=False
    )  # 'pending', 'approved', 'rejected'

    __table_args__ = (
        db.UniqueConstraint("team_id", "position", name="uq_team_position_square"),
    )


class QuizQuestion(db.Model):
    __tablename__ = "quiz_questions"

    quiz_id = db.Column(db.Integer, primary_key=True)
    question_num = db.Column(db.Integer, unique=True, nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    choice_a = db.Column(db.String(255), nullable=False)
    choice_b = db.Column(db.String(255), nullable=False)
    choice_c = db.Column(db.String(255), nullable=False)
    choice_d = db.Column(db.String(255), nullable=False)
    correct_choice = db.Column(db.String(4), nullable=False)  # e.g., 'A', 'BC', 'ACD'
    is_multiple_choice = db.Column(
        db.Boolean, default=False, nullable=False
    )
    status = db.Column(
        db.String(20), default="hidden", nullable=False
    )  # 'hidden', 'active', 'revealed'


class QuizSubmission(db.Model):
    __tablename__ = "quiz_submissions"

    submission_id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(
        db.Integer,
        db.ForeignKey("quiz_questions.quiz_id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id = db.Column(
        db.Integer, db.ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False
    )
    selected_choice = db.Column(db.String(10), nullable=False)  # e.g., 'A', 'B', or 'ABD'
    is_correct = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("quiz_id", "team_id", name="uq_quiz_team_submission"),
    )

    question = db.relationship("QuizQuestion", backref="submissions")


class BetEvent(db.Model):
    __tablename__ = "bet_events"

    event_id = db.Column(db.Integer, primary_key=True)
    event_name = db.Column(db.String(100), nullable=False)
    multiplier = db.Column(db.Float, default=2.0, nullable=False)  # Odds e.g. 2.0x
    status = db.Column(
        db.String(20), default="waiting", nullable=False
    )  # 'waiting', 'betting', 'closed', 'settled'


class BetOption(db.Model):
    __tablename__ = "bet_options"

    option_id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer,
        db.ForeignKey("bet_events.event_id", ondelete="CASCADE"),
        nullable=False,
    )
    option_text = db.Column(db.String(100), nullable=False)
    multiplier = db.Column(db.Float, nullable=False)

    event = db.relationship("BetEvent", backref="options")


class TeamBet(db.Model):
    __tablename__ = "team_bets"

    bet_id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer,
        db.ForeignKey("bet_events.event_id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id = db.Column(
        db.Integer, db.ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False
    )
    bet_points = db.Column(db.Integer, nullable=False)
    prediction = db.Column(db.String(100), nullable=False)  # Prediction text
    multiplier = db.Column(db.Float, default=2.0, nullable=False)  # Multiplier at the time of betting
    status = db.Column(
        db.String(20), default="pending", nullable=False
    )  # 'pending', 'won', 'lost'

    __table_args__ = (
        db.UniqueConstraint("event_id", "team_id", name="uq_event_team_bet"),
    )

    event = db.relationship("BetEvent", backref="bets")
