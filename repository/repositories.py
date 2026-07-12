from typing import List
from extensions import db
from model.models import (
    Team,
    BingoTheme,
    BingoSquare,
    QuizQuestion,
    QuizSubmission,
    BetEvent,
    TeamBet,
    BetOption,
)

# Team Repositories
def get_all_teams() -> List[Team]:
    return Team.query.order_by(Team.points.desc()).all()

def get_team_by_id(team_id: int) -> Team:
    return Team.query.get(team_id)

def update_team_points(team_id: int, points: int):
    team = Team.query.get(team_id)
    if team:
        team.points = points
        db.session.commit()

# Bingo Repositories
def get_all_bingo_themes() -> list[BingoTheme]:
    return BingoTheme.query.order_by(BingoTheme.position).all()

def get_bingo_theme_by_position(position: int) -> BingoTheme | None:
    return BingoTheme.query.filter_by(position=position).first()

def update_bingo_theme(position: int, theme_text: str):
    theme = get_bingo_theme_by_position(position)
    if theme:
        theme.theme_text = theme_text
    else:
        theme = BingoTheme(position=position, theme_text=theme_text)
        db.session.add(theme)
    db.session.commit()

def get_bingo_squares_by_team(team_id: int) -> list[BingoSquare]:
    return BingoSquare.query.filter_by(team_id=team_id).all()

def get_bingo_square_by_team_and_pos(team_id: int, position: int) -> BingoSquare | None:
    return BingoSquare.query.filter_by(team_id=team_id, position=position).first()

def insert_or_update_bingo_square(team_id: int, position: int, content: str) -> BingoSquare:
    square = get_bingo_square_by_team_and_pos(team_id, position)
    if square:
        square.content = content
        square.status = 'pending' # Reset status to pending on update
    else:
        square = BingoSquare(team_id=team_id, position=position, content=content, status='pending')
        db.session.add(square)
    db.session.commit()
    return square

def get_pending_bingo_squares() -> list[BingoSquare]:
    return BingoSquare.query.filter_by(status='pending').all()

def get_bingo_square_by_id(square_id: int) -> BingoSquare | None:
    return BingoSquare.query.get(square_id)

def update_bingo_square_status(square_id: int, status: str):
    square = BingoSquare.query.get(square_id)
    if square:
        square.status = status
        db.session.commit()

# Quiz Repositories
def get_all_questions() -> list[QuizQuestion]:
    return QuizQuestion.query.order_by(QuizQuestion.question_num).all()

def get_question_by_id(quiz_id: int) -> QuizQuestion:
    return QuizQuestion.query.get(quiz_id)

def get_active_question() -> QuizQuestion | None:
    return QuizQuestion.query.filter_by(status='active').first()

def get_last_revealed_question() -> QuizQuestion | None:
    return QuizQuestion.query.filter_by(status='revealed').order_by(QuizQuestion.question_num.desc()).first()

def update_question_status(quiz_id: int, status: str):
    q = QuizQuestion.query.get(quiz_id)
    if q:
        q.status = status
        db.session.commit()

# Quiz Submission Repositories
def insert_submission(quiz_id: int, team_id: int, choice: str) -> QuizSubmission:
    sub = QuizSubmission(quiz_id=quiz_id, team_id=team_id, selected_choice=choice)
    db.session.add(sub)
    db.session.commit()
    return sub

def get_submissions_for_question(quiz_id: int) -> list[QuizSubmission]:
    return QuizSubmission.query.filter_by(quiz_id=quiz_id).all()

def get_submission_by_team_and_quiz(quiz_id: int, team_id: int) -> QuizSubmission | None:
    return QuizSubmission.query.filter_by(quiz_id=quiz_id, team_id=team_id).first()

# Bet Repositories
def get_all_events() -> list[BetEvent]:
    return BetEvent.query.all()

def get_event_by_id(event_id: int) -> BetEvent:
    return BetEvent.query.get(event_id)

def get_active_bet_event() -> BetEvent | None:
    return BetEvent.query.filter(BetEvent.status.in_(['betting', 'closed'])).first()


def update_event_status(event_id: int, status: str):
    event = BetEvent.query.get(event_id)
    if event:
        event.status = status
        # Recovery Rule: If starting betting, give 100pt to teams with 0pt
        if status == 'betting':
            teams_with_zero = Team.query.filter(Team.points <= 0).all()
            for team in teams_with_zero:
                team.points = 100
        db.session.commit()

def insert_bet(event_id: int, team_id: int, bet_points: int, prediction: str, multiplier: float) -> TeamBet:
    bet = TeamBet(event_id=event_id, team_id=team_id, bet_points=bet_points, prediction=prediction, multiplier=multiplier)
    db.session.add(bet)
    db.session.commit()
    return bet

def get_bets_for_event(event_id: int) -> list[TeamBet]:
    return TeamBet.query.filter_by(event_id=event_id).all()

def get_bet_by_event_and_team(event_id: int, team_id: int) -> TeamBet | None:
    return TeamBet.query.filter_by(event_id=event_id, team_id=team_id).first()

# BetOption Repositories
def get_options_for_event(event_id: int) -> list[BetOption]:
    return BetOption.query.filter_by(event_id=event_id).all()

def get_option_by_id(option_id: int) -> BetOption | None:
    return BetOption.query.get(option_id)
