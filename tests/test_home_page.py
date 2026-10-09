import math
from datetime import datetime, timedelta, timezone

from fakes import FakeClock, FakeIdle
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

from eyeexercise.core.history import History, HistoryEvent
from eyeexercise.core.scheduler import ReminderScheduler, State
from eyeexercise.core.settings import Settings
from eyeexercise.core.settings_manager import SettingsManager
from eyeexercise.core.usage import UsageLog
from eyeexercise.ui import theme
from eyeexercise.ui.controller import Controller
from eyeexercise.ui.gauge import RingGauge
from eyeexercise.ui.home_page import MAX_EYES, HomePage
from eyeexercise.ui.main_window import MainWindow

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 7, 14, 30, tzinfo=KST)


def at(hour, minute=0):
    return datetime(2026, 10, 7, hour, minute, tzinfo=KST)


def rest(ts):
    return HistoryEvent(ts, "completed", "blink", 36)


def exercise(ts):
    return HistoryEvent(ts, "completed", "dot_follow", 60)


@pytest.fixture(autouse=True)
def clean_theme():
    theme._reset_for_tests()
    yield
    theme._reset_for_tests()  # 다크로 바꾼 테스트가 다른 테스트에 남지 않게


def page(events=(), usage=None, settings=None, animations=False, clock=None):
    """애니메이션을 끈 홈 화면(수위가 목표로 바로 간다). 움직임을 시험할 때만 animations=True로 켠다."""
    return HomePage(
        lambda: events,
        lambda: NOW,
        lambda: usage or UsageLog(),
        lambda: settings or Settings(),
        tz=KST,
        animations=lambda: animations,
        motion_clock=clock or (lambda: 0.0),
    )


def pixel(widget, x, y) -> QColor:
    return QColor(widget.grab().toImage().pixel(x, y))


def ring_pixel(gauge, fraction):
    """고리 위에서 12시부터 시계 방향으로 fraction만큼 돈 곳의 색."""
    rect = gauge.ring_rect()
    angle = math.radians(90 - fraction * 360)
    radius = rect.width() / 2
    return pixel(gauge, round(rect.center().x() + radius * math.cos(angle)), round(rect.center().y() - radius * math.sin(angle)))


# ---- 게이지 ----


def test_게이지_글자와_색_단계(qapp):
    gauge = RingGauge()
    assert gauge.text == "–" and gauge.tone == "none"
    for rate, text, tone in ((0.3, "30%", "low"), (0.5, "50%", "mid"), (0.79, "79%", "mid"), (0.8, "80%", "good"), (1.0, "100%", "good")):
        gauge.set_rate(rate)
        assert (gauge.text, gauge.tone) == (text, tone)


def test_게이지_값은_0에서_1_사이로_보정한다(qapp):
    gauge = RingGauge()
    gauge.set_rate(1.7)
    assert gauge.rate == 1.0
    gauge.set_rate(-0.2)
    assert gauge.rate == 0.0


def test_게이지_호는_달성률_색으로_차오르고_나머지는_빈_색이다(qapp):
    gauge = RingGauge()
    gauge.resize(200, 200)
    for rate, name in ((0.9, "gauge_good"), (0.6, "gauge_mid"), (0.3, "gauge_low")):
        gauge.set_rate(rate)
        assert ring_pixel(gauge, rate / 2).name() == theme.color(name).name()  # 호의 가운데
    gauge.set_rate(0.3)
    assert ring_pixel(gauge, 0.6).name() == theme.color("track").name()  # 호 바깥은 빈 고리


def test_달성률이_없으면_고리가_모두_빈_색이다(qapp):
    gauge = RingGauge()
    gauge.resize(200, 200)
    gauge.set_rate(None)
    assert ring_pixel(gauge, 0.25).name() == theme.color("track").name()


def test_80퍼센트_목표선이_고리를_가로질러_그려진다(qapp):
    gauge = RingGauge()
    gauge.resize(200, 200)
    gauge.set_rate(0.3)
    x, y = gauge.target_point()
    cx, cy = gauge.ring_rect().center().x(), gauge.ring_rect().center().y()
    # 목표 지점 근처(선은 가늘고 안티앨리어싱되므로 2px 안쪽)에 글자색에 가까운 진한 픽셀이 있다
    nearby = [pixel(gauge, round(x - (x - cx) * 0.03) + dx, round(y - (y - cy) * 0.03) + dy) for dx in range(-2, 3) for dy in range(-2, 3)]
    assert any(c.lightness() < 90 for c in nearby)
    # 반대편(목표선이 없는 곳)에는 같은 반경에 진한 픽셀이 없다
    ox, oy = 2 * cx - x, 2 * cy - y
    opposite = [pixel(gauge, round(ox - (ox - cx) * 0.03) + dx, round(oy - (oy - cy) * 0.03) + dy) for dx in range(-2, 3) for dy in range(-2, 3)]
    assert all(c.lightness() >= 90 for c in opposite)


# ---- 홈 화면: 오늘 요약 ----


def test_홈_화면은_오늘_요약을_보여_준다(qapp):
    usage = UsageLog()
    for hour in (9, 10, 11, 13):
        usage.add(at(hour, 59), 3600)
    events = [rest(at(9, 30)) for _ in range(6)] + [exercise(at(10)), exercise(at(11))]
    home = page(events, usage)
    assert home.eye_label == "오늘 눈 휴식 6회 / 권장 12회 · 50%"
    assert (home.eyes.closed, home.eyes.open, home.eyes.hidden) == (6, 6, 0)
    assert home.stat("screen") == "4시간"
    assert home.stat("exercise") == "2/2회"


def test_눈_휴식_글자에_달성률이_붙는다(qapp):
    usage = UsageLog()
    for hour in (9, 10):
        usage.add(at(hour, 59), 3600)  # 권장 6회
    assert page([rest(at(9, 30)) for _ in range(3)], usage).eye_label == "오늘 눈 휴식 3회 / 권장 6회 · 50%"
    assert page([rest(at(9, 30)) for _ in range(9)], usage).eye_label.endswith("· 100%")  # 많이 쉬어도 100%까지만
    assert "%" not in page().eye_label  # 권장 횟수가 없으면 퍼센트도 없다


def test_큰_창에서는_큰_글자가_한_단계씩_가늘어진다(qapp):
    from PySide6.QtGui import QFont

    small, mid, big = sized(page(), 800, 600), sized(page(), 1000, 700), sized(page(), 1700, 1000)
    assert small._weight() == QFont.Weight.Black
    assert big._weight() == QFont.Weight.Bold
    assert small._weight() >= mid._weight() >= big._weight()


def test_기록이_없으면_빈_값으로_뜬다(qapp):
    home = page()
    assert home.eye_label == "사용 시간이 짧아요"
    assert (home.eyes.closed, home.eyes.open) == (0, 0)
    assert home.stat("screen") == "0분" and home.stat("longest") == "–"
    assert home.stat("exercise") == "0/2회"


def test_권장_횟수가_없어도_쉰_횟수는_보여_준다(qapp):
    home = page([rest(at(9, 30))])  # 사용 기록이 없어 권장은 0회
    assert home.eye_label == "오늘 눈 휴식 1회"
    assert (home.eyes.closed, home.eyes.open) == (1, 0)


def test_눈_아이콘은_상한까지만_그린다(qapp):
    usage = UsageLog()
    for hour in range(0, 14):
        usage.add(at(hour, 59), 3600)  # 14시간 사용 → 권장 42회
    home = page([rest(at(9, 30)) for _ in range(5)], usage)
    assert home.eyes.closed + home.eyes.open == MAX_EYES
    assert home.eyes.hidden == 42 - MAX_EYES
    assert home.eye_label == "오늘 눈 휴식 5회 / 권장 42회 · 12%"  # 정확한 숫자는 글자로 보여 준다


def test_운동_목표가_0이면_횟수만_보여_준다(qapp):
    settings = SettingsManager(Settings()).update({"exercises.daily_goal": 0}).settings
    home = page(settings=settings)  # 변수에 담아 둬야 위젯이 지워지지 않는다
    assert home.stat("exercise") == "0회"


def test_다시_그리면_새_기록을_따라간다(qapp):
    events = []
    home = HomePage(lambda: events, lambda: NOW, lambda: UsageLog(), Settings, tz=KST, animations=lambda: False)
    assert home.stat("exercise") == "0/2회"
    events.append(exercise(at(10)))
    home.refresh()
    assert home.stat("exercise") == "1/2회"


def test_그림으로_그린_글자도_화면_읽기_설명에_담긴다(qapp):
    home = page()
    home.set_timer(State.RUNNING, 754, 1200, None)
    description = home.accessibleDescription()
    assert "다음 눈 휴식까지 12:34" in description and "오늘 스크린 타임" in description and "사용 시간이 짧아요" in description


# ---- 홈 화면: 타이머와 물의 높이 ----


def test_타이머는_상태에_따라_글자와_물의_높이가_바뀐다(qapp):
    home = page()
    home.set_timer(State.RUNNING, 600, 1200, None)
    assert home.kicker_text == "다음 눈 휴식까지" and home.clock_text == "10:00" and home.water_target == 0.5
    assert home._rest_button.isEnabled() and home._snooze_button.isHidden()
    assert home.sub_text == "20분마다 눈을 쉬어 줘요"
    home.set_timer(State.DUE, None, 1200, None)
    assert home.kicker_text == "눈 휴식 시간" and home.clock_text == "지금" and home.water_target == 1.0
    assert not home._snooze_button.isHidden() and home._snooze_button.text() == "5분 미루기"
    home.set_timer(State.EXERCISING, None, None, "rest")
    assert home.kicker_text == "눈 휴식 중" and home.water_target == 0.0 and not home._rest_button.isEnabled()
    home.set_timer(State.PAUSED, 300, 1200, None)
    assert home.clock_text == "5:00" and home.water_target == 0.75 and not home._rest_button.isEnabled()


def test_미루기_버튼_글자는_설정의_미루기_시간을_따른다(qapp):
    home = page(settings=SettingsManager(Settings()).update({"snooze_minutes": 10}).settings)
    home.set_timer(State.DUE, None, 1200, None)
    assert home._snooze_button.text() == "10분 미루기"


def test_애니메이션이_꺼져_있으면_물이_목표_높이로_바로_간다(qapp):
    home = page(animations=False)
    home.set_timer(State.RUNNING, 300, 1200, None)
    assert home.water_level == home.water_target == 0.75


def test_애니메이션이_켜져_있으면_물이_목표를_향해_서서히_차오른다(qapp):
    home = page(animations=True)
    home.set_timer(State.DUE, None, 1200, None)  # 목표 100%
    assert home.water_level == 0.0
    levels = []
    for _ in range(12):
        home._on_frame()
        levels.append(home.water_level)
    assert levels == sorted(levels) and 0.0 < levels[0] < levels[-1] < 1.0  # 뛰지 않고 조금씩 오른다
    for _ in range(200):
        home._on_frame()
    assert home.water_level == 1.0  # 결국 목표에 닿는다


def test_파도_시간은_움직임_시계를_따라간다(qapp):
    now = {"t": 100.0}
    home = page(animations=True, clock=lambda: now["t"])
    now["t"] = 107.5
    home._on_frame()
    assert home._wave_t == 7.5


def test_보이는_동안에만_물결을_다시_그린다(qapp):
    moving = page(animations=True)
    moving.show()
    assert moving._frame.isActive()
    moving.hide()
    assert not moving._frame.isActive()
    still = page(animations=False)
    still.show()
    assert not still._frame.isActive()  # 애니메이션을 끄면 타이머를 돌리지 않는다
    moving.deleteLater()
    still.deleteLater()


# ---- 홈 화면: 물이 그려지는 모양 ----


def sized(home, width=800, height=600):
    home.resize(width, height)
    return home


def test_수위_0이어도_물결이_바닥에_얇게_보인다(qapp):
    # 처음 열었을 때(20:00) 파도가 아예 안 보이면 고장 난 것처럼 보인다
    home = sized(page())
    home.set_timer(State.RUNNING, 1200, 1200, None)
    assert home.water_target == 0.0
    front, _back, _line = home.water_paths()
    h = home.height()
    assert 0.8 * h < front.boundingRect().top() < h  # 바닥의 얇은 띠
    assert pixel(home, 5, h - 3).name() == theme.color("hero").name()
    assert pixel(home, 5, h // 2).name() == theme.color("paper").name()


def test_시계_글자_크기는_보이는_숫자가_바뀌어도_그대로다(qapp):
    home = sized(page())
    sizes = set()
    for state, remaining in ((State.RUNNING, 1199), (State.RUNNING, 588), (State.RUNNING, 59), (State.DUE, None), (State.EXERCISING, None)):
        home.set_timer(state, remaining, 1200, "rest" if state is State.EXERCISING else None)
        sizes.add(home._geometry().clock_px)
    assert len(sizes) == 1, sizes


def test_시계_글자_크기는_오늘_요약_값이_바뀌어도_그대로다(qapp):
    usage = UsageLog()
    home = sized(page(usage=usage))
    home.set_timer(State.RUNNING, 600, 1200, None)
    before = home._geometry().clock_px
    for hour in range(9, 14):
        usage.add(at(hour, 59), 3600)
    home.refresh()
    assert home.stat("screen") == "5시간" and home._geometry().clock_px == before


def test_수위_100이면_물이_화면을_빈틈없이_덮는다(qapp):
    home = sized(page())
    home.set_timer(State.DUE, None, 1200, None)
    front, _back, _line = home.water_paths()
    assert front.boundingRect().top() <= 0
    for x in (0, 5, home.width() // 2, home.width() - 5):
        assert front.contains(QPointF(x, 1))
    assert pixel(home, 5, home.height() // 2).name() == theme.color("hero").name()


def test_물은_수위만큼_아래에서부터_차오른다(qapp):
    home = sized(page())
    home.set_timer(State.RUNNING, 600, 1200, None)  # 50%
    h = home.height()
    # 왼쪽 가장자리(글자가 없는 곳)에서, 수면에서 충분히 떨어진 위와 아래를 본다
    assert pixel(home, 5, h // 2 - 90).name() == theme.color("paper").name()
    assert pixel(home, 5, h // 2 + 90).name() == theme.color("hero").name()


def test_뒤쪽_물결은_앞쪽_물과_다른_모양으로_깔린다(qapp):
    home = sized(page())
    home.set_timer(State.RUNNING, 600, 1200, None)
    front, back, _line = home.water_paths()
    assert back != front and back.boundingRect().height() > 0


def test_글자는_물_밖에서는_짙은색_물_안에서는_모래색으로_두_번_그린다(qapp, monkeypatch):
    calls = []
    original = HomePage._paint_content

    def spy(self, painter, color):
        calls.append((color.name(), painter.hasClipping()))
        original(self, painter, color)

    monkeypatch.setattr(HomePage, "_paint_content", spy)
    home = sized(page())
    home.set_timer(State.RUNNING, 600, 1200, None)
    home.grab()
    assert calls == [(theme.color("text").name(), False), (theme.color("sand").name(), True)]


def test_다크_모드에서는_바탕과_물이_어두운_색으로_칠해진다(qapp):
    theme.set_dark(True)
    home = sized(page())
    home.set_timer(State.RUNNING, 600, 1200, None)
    h = home.height()
    assert pixel(home, 5, h // 2 - 90).name() == theme.DARK.paper
    assert pixel(home, 5, h // 2 + 90).name() == theme.DARK.hero


def test_창이_커지면_글자와_아이콘도_같은_비율로_커진다(qapp):
    small, big = sized(page(), 800, 600), sized(page(), 1700, 1000)
    for home in (small, big):
        home.set_timer(State.RUNNING, 588, 1200, None)
    gs, gb = small._geometry(), big._geometry()
    assert gb.clock_px > gs.clock_px * 1.1  # 전체 화면에서 시계가 작게 남지 않는다(너무 키우지는 않는다)
    assert gb.stats[0].height() > gs.stats[0].height()
    assert small._scale() == 1.0 and 1.0 < big._scale() <= 1.25
    assert gb.clock.left() > gs.clock.left()  # 여백도 창 너비에 비례해 늘어난다
    assert gb.stats[0].right() - gb.clock.left() <= 1180 + 1  # 글자 영역은 최대 너비를 넘지 않는다


def test_큰_창에서도_글자가_서로_겹치거나_창_밖으로_나가지_않는다(qapp):
    for width, height in ((1280, 720), (1700, 1000), (2400, 1300), (900, 560)):
        home = sized(page(), width, height)
        home.set_timer(State.RUNNING, 754, 1200, None)
        g = home._geometry()
        assert g.clock.left() >= 0 and g.clock.right() <= g.stats[0].left(), (width, height)
        assert all(rect.right() <= width and rect.bottom() <= g.eyes_top for rect in g.stats), (width, height)
        assert g.clock.bottom() + g.sub.height() <= g.eyes_top, (width, height)


def test_버튼은_글자와_같은_왼쪽_여백에서_시작한다(qapp):
    for width, height in ((800, 600), (1700, 1000)):
        home = sized(page(), width, height)
        home.show()
        qapp.processEvents()
        assert abs(home._rest_button.x() - home._geometry().clock.left()) <= 1
        home.hide()
        home.deleteLater()


def test_큰_창에서는_버튼도_함께_커진다(qapp):
    heights = []
    for width, height in ((800, 600), (1700, 1000)):
        home = sized(page(), width, height)
        home.show()
        qapp.processEvents()
        heights.append(home._rest_button.height())
        # 버튼 줄은 아래 여백 위에 놓이고 눈 아이콘 줄과 겹치지 않는다
        assert home._rest_button.geometry().bottom() <= home.height()
        assert home._rest_button.geometry().top() >= home._geometry().eyes_top + 44 * home._scale() - 1
        home.hide()
        home.deleteLater()
    assert heights[1] > heights[0] * 1.1


def test_큰_창에서도_물은_창_전체를_채운다(qapp):
    home = sized(page(), 2200, 900)
    home.set_timer(State.DUE, None, 1200, None)
    assert pixel(home, 5, 450).name() == theme.color("hero").name() and pixel(home, 2195, 450).name() == theme.color("hero").name()


def test_모든_상태에서_화면이_그려진다(qapp):
    home = sized(page())
    for state, remaining in ((State.RUNNING, 700), (State.SNOOZED, 120), (State.PAUSED, 300), (State.DUE, None), (State.EXERCISING, None)):
        home.set_timer(state, remaining, 1200, "rest" if state is State.EXERCISING else None)
        assert not home.grab().isNull()
    for dark in (False, True):
        theme.set_dark(dark)
        assert not home.grab().isNull()


def test_창이_좁아도_글자가_겹치지_않도록_자리를_계산한다(qapp):
    home = sized(page(), 560, 440)
    home.set_timer(State.RUNNING, 754, 1200, None)
    g = home._geometry()
    assert g.clock.left() >= 0 and g.clock.right() <= home.width()
    assert g.clock.right() <= g.stats[0].left()  # 큰 시계가 오른쪽 요약 글자와 겹치지 않는다
    assert 24 <= g.clock_px <= 260
    assert all(rect.right() <= home.width() for rect in g.stats)


# ---- 메인 창과 컨트롤러 ----


def make_window():
    clock = FakeClock()
    controller = Controller(ReminderScheduler(Settings(), clock, FakeIdle()), History(), now=clock.now)
    window = MainWindow(now=clock.now)
    window.attach_controller(controller)
    return window, controller, clock


def test_홈_화면은_컨트롤러의_남은_시간을_따라간다(qapp):
    window, controller, clock = make_window()
    assert window.home_page.clock_text == "20:00"
    for _ in range(90):
        clock.advance(1)
        controller._on_tick()
    assert window.home_page.clock_text == "18:30" and 0 < window.home_page.water_target < 0.1


def test_홈의_지금_휴식_버튼은_휴식을_시작한다(qapp):
    window, controller, _ = make_window()
    started = []
    controller.activity_started.connect(started.append)
    window.home_page._rest_button.click()
    assert started == ["rest"] and controller.state is State.EXERCISING
    assert window.home_page.kicker_text == "눈 휴식 중"


def test_홈의_미루기_버튼은_알림을_미룬다(qapp):
    window, controller, clock = make_window()
    for _ in range(1200):
        clock.advance(1)
        controller._on_tick()
    assert controller.state is State.DUE and not window.home_page._snooze_button.isHidden()
    window.home_page._snooze_button.click()
    assert controller.state is State.SNOOZED
    assert window.home_page.kicker_text == "다시 알림까지"


def test_눈_운동을_마치면_홈의_오늘_요약이_바뀐다(qapp):
    clock = FakeClock()
    history = History()
    controller = Controller(ReminderScheduler(Settings(), clock, FakeIdle()), history, now=clock.now)
    window = MainWindow(history, now=clock.now)
    window.attach_controller(controller)
    window.home_page._tz = KST
    assert window.home_page.stat("exercise") == "0/2회"
    controller.start_exercise()
    controller.complete_exercise("dot_follow", 60)
    assert window.home_page.stat("exercise") == "1/2회"


def test_설정에서_운동_목표를_바꾸면_홈이_따라간다(qapp):
    manager = SettingsManager(Settings())
    window = MainWindow(settings_manager=manager)
    manager.update({"exercises.daily_goal": 4})
    assert window.home_page.stat("exercise") == "0/4회"


def test_홈이_첫_화면이다(qapp):
    window = MainWindow()
    assert window.sidebar.label(0) == "홈" and window._stack.currentWidget() is window.home_page


# ---- 지금 운동·일시정지 ----


def test_홈의_지금_운동_버튼은_눈_운동을_시작한다(qapp):
    window, controller, _ = make_window()
    started = []
    controller.activity_started.connect(started.append)
    window.home_page._exercise_button.click()
    assert started == ["exercise"] and controller.state is State.EXERCISING
    assert window.home_page.kicker_text == "눈 운동 중"


def test_홈의_일시정지_버튼은_멈췄다가_이어서_센다(qapp):
    window, controller, clock = make_window()
    for _ in range(60):
        clock.advance(1)
        controller._on_tick()
    window.home_page._pause_button.click()
    assert controller.state is State.PAUSED
    assert window.home_page._pause_button.text() == "재개" and window.home_page.kicker_text == "일시정지됨"
    assert not window.home_page._rest_button.isEnabled() and not window.home_page._exercise_button.isEnabled()
    window.home_page._pause_button.click()
    assert controller.state is State.RUNNING and window.home_page._pause_button.text() == "일시정지"
    assert window.home_page.clock_text == "19:00"  # 멈춘 곳에서 이어서 센다


def test_운동과_일시정지_버튼은_상태에_따라_켜지고_꺼진다(qapp):
    home = page()
    for state, startable, pausable in (
        (State.RUNNING, True, True),
        (State.SNOOZED, True, True),
        (State.DUE, True, False),
        (State.EXERCISING, False, False),
        (State.PAUSED, False, True),
    ):
        home.set_timer(state, 100, 1200, None)
        assert home._exercise_button.isEnabled() is startable, state
        assert home._pause_button.isEnabled() is pausable, state
