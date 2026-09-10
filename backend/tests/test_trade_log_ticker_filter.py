"""거래 로그 종목별 조회 회귀 테스트.

포트폴리오 카드에서 "이 종목을 언제 얼마에 샀는지"를 보려면 티커로 원장을 좁혀야 한다.
필터가 없던 시절에는 전 종목 최신 100건을 받아 화면에서 걸렀는데, 그러면 최근 거래가
활발한 종목들에 밀려 조용한 보유분의 매수 기록이 아예 응답에 들어오지 않았다.

여기서 고정하는 계약은 네 가지다.
  1. 필터는 DB에서 적용된다 - limit보다 먼저 걸려야 한다. 화면 필터링과의 차이가 이 테스트의 핵심이다.
  2. 사용자 격리는 필터를 걸어도 유지된다.
  3. 접두·대소문자 표기가 달라도 같은 원장을 가리킨다(AAPL == nas_aapl).
  4. 티커를 주지 않으면 종전 동작(전체 최신순) 그대로다.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.models import TradeLog, User
from app.trades.router_trades import get_trade_logs

BASE_TIME = datetime(2026, 9, 1, 14, 30, tzinfo=timezone.utc)


def _make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _make_user(db, username):
    user = User(username=username, hashed_password="hashed")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _add_log(db, user, ticker, trade_type, price, quantity, minutes, strategy="regime_switching"):
    db.add(TradeLog(
        user_id=user.id,
        ticker=ticker,
        ticker_name=f"{ticker} Inc",
        trade_type=trade_type,
        price=price,
        quantity=quantity,
        strategy_type=strategy,
        executed_at=BASE_TIME + timedelta(minutes=minutes),
    ))
    db.commit()


def test_filter_applies_before_limit():
    """필터는 DB에서 걸린다 - 최신 limit건을 받아 화면에서 거르는 것과 결과가 다르다.

    조용한 종목의 매수는 활발한 종목들 뒤로 밀린다. 필터가 limit 뒤에 적용되면
    바로 이 매수 기록이 응답에서 사라지고, 화면은 "이력 없음"을 보여주게 된다.
    """
    db = _make_db()
    user = _make_user(db, "quiet")

    _add_log(db, user, "AAPL", "BUY", 180.0, 10, minutes=0)
    for i in range(150):
        _add_log(db, user, "TSLA", "BUY", 300.0 + i, 1, minutes=i + 1)

    logs = get_trade_logs(ticker="AAPL", current_user=user, db=db)

    assert [log.ticker for log in logs] == ["AAPL"]
    assert float(logs[0].price) == 180.0
    assert logs[0].quantity == 10
    assert logs[0].executed_at is not None

    # 네거티브 대조 - 같은 limit으로 필터 없이 부르면 AAPL은 응답에 없다.
    unfiltered = get_trade_logs(current_user=user, db=db)
    assert "AAPL" not in {log.ticker for log in unfiltered}


def test_filter_keeps_user_isolation():
    """다른 사용자의 같은 티커 체결은 절대 섞이지 않는다."""
    db = _make_db()
    mine = _make_user(db, "mine")
    other = _make_user(db, "other")

    _add_log(db, mine, "QLD", "BUY", 100.0, 5, minutes=0)
    _add_log(db, other, "QLD", "BUY", 999.0, 77, minutes=1)
    # 내 계정의 다른 종목. 필터가 실제로 걸리지 않으면 이 행까지 딸려 와 개수 단언이 깨진다.
    _add_log(db, mine, "TQQQ", "BUY", 80.0, 3, minutes=2)

    logs = get_trade_logs(ticker="QLD", current_user=mine, db=db)

    assert len(logs) == 1
    assert logs[0].user_id == mine.id
    assert float(logs[0].price) == 100.0


def test_ticker_notation_is_normalized():
    """증권사 접두·소문자 표기로 물어도 같은 원장을 가리킨다."""
    db = _make_db()
    user = _make_user(db, "notation")

    _add_log(db, user, "AAPL", "BUY", 180.0, 10, minutes=0)
    # 미끼 종목 - 정규화만 되고 필터가 걸리지 않으면 이 행이 결과에 섞인다.
    _add_log(db, user, "AAPU", "BUY", 20.0, 1, minutes=1)

    for notation in ("AAPL", "nas_aapl", "NAS_AAPL", " aapl "):
        logs = get_trade_logs(ticker=notation, current_user=user, db=db)
        assert [log.ticker for log in logs] == ["AAPL"], notation


def test_no_ticker_preserves_existing_contract():
    """티커를 주지 않으면 종전대로 전체를 최신순으로 준다 - 대시보드 전체 로그가 이 경로다.

    공백만 들어온 경우도 전체 조회다. 정규화 결과가 빈 문자열이면 어떤 행과도 매칭되지
    않아 "이력 없음"으로 오인되므로, 필터를 걸지 않는 쪽이 안전하다.
    """
    db = _make_db()
    user = _make_user(db, "全体")

    _add_log(db, user, "AAPL", "BUY", 180.0, 10, minutes=0)
    _add_log(db, user, "TSLA", "BUY", 300.0, 2, minutes=5)
    _add_log(db, user, "AAPL", "SELL", 190.0, 10, minutes=9)

    logs = get_trade_logs(current_user=user, db=db)
    assert [log.ticker for log in logs] == ["AAPL", "TSLA", "AAPL"]
    assert logs[0].trade_type == "SELL"

    blank = get_trade_logs(ticker="   ", current_user=user, db=db)
    assert len(blank) == 3


def test_pagination_walks_a_single_ticker():
    """skip/limit은 필터된 결과 위에서 동작한다 - 이력이 길어도 끝까지 넘길 수 있다."""
    db = _make_db()
    user = _make_user(db, "paged")

    for i in range(5):
        _add_log(db, user, "NVDA", "BUY", 100.0 + i, 1, minutes=i)
        _add_log(db, user, "AMD", "BUY", 50.0, 1, minutes=i)

    first = get_trade_logs(ticker="NVDA", limit=2, current_user=user, db=db)
    second = get_trade_logs(ticker="NVDA", skip=2, limit=2, current_user=user, db=db)

    assert [float(log.price) for log in first] == [104.0, 103.0]
    assert [float(log.price) for log in second] == [102.0, 101.0]
    assert all(log.ticker == "NVDA" for log in first + second)
