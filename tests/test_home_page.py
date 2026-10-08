import math
from datetime import datetime, timedelta, timezone

from fakes import FakeClock, FakeIdle
from PySide6.QtGui import QColor

from eyeexercise.core.history import History, HistoryEvent
from eyeexercise.core.home import filled_cells, timer_progress
from eyeexercise.core.scheduler import ReminderScheduler, State
from eyeexercise.core.settings import Settings
from eyeexercise.core.settings_manager import SettingsManager
from eyeexercise.core.usage import UsageLog
from eyeexercise.ui import theme
from eyeexercise.ui.controller import Controller
from eyeexercise.ui.gauge import RingGauge
from eyeexercise.ui.home_page import PROGRESS_CELLS, CellBar, HomePage
from eyeexercise.ui.main_window import MainWindow

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 7, 14, 30, tzinfo=KST)


def at(hour, minute=0):
    return datetime(2026, 10, 7, hour, minute, tzinfo=KST)


def rest(ts):
    return HistoryEvent(ts, "completed", "blink", 36)


def exercise(ts):
    return HistoryEvent(ts, "completed", "dot_follow", 60)


def page(events=(), usage=None, settings=None):
    return HomePage(lambda: events, lambda: NOW, lambda: usage or UsageLog(), lambda: settings or Settings(), tz=KST)


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


# ---- 홈 화면 ----


def test_홈_화면은_오늘_요약을_보여_준다(qapp):
    usage = UsageLog()
    for hour in (9, 10, 11, 13):
        usage.add(at(hour, 59), 3600)
    events = [rest(at(9, 30)) for _ in range(6)] + [exercise(at(10)), exercise(at(11))]
    home = page(events, usage)
    assert home.gauge.text == "50%" and home.gauge.tone == "mid"
    assert home._gauge_detail.text() == "6회 / 권장 12회"
    assert home._tiles["screen"].text() == "4시간"
    assert home._tiles["exercise"].text() == "2/2회"


def test_기록이_없으면_빈_값으로_뜬다(qapp):
    home = page()
    assert home.gauge.text == "–"
    assert home._gauge_detail.text() == "사용 시간이 짧아요"
    assert home._tiles["screen"].text() == "0분" and home._tiles["longest"].text() == "–"
    assert home._tiles["exercise"].text() == "0/2회"


def test_운동_목표가_0이면_횟수만_보여_준다(qapp):
    settings = SettingsManager(Settings()).update({"exercises.daily_goal": 0}).settings
    home = page(settings=settings)  # 변수에 담아 둬야 위젯이 지워지지 않는다
    assert home._tiles["exercise"].text() == "0회"


def test_다시_그리면_새_기록을_따라간다(qapp):
    events = []
    home = HomePage(lambda: events, lambda: NOW, lambda: UsageLog(), Settings, tz=KST)
    assert home._tiles["exercise"].text() == "0/2회"
    events.append(exercise(at(10)))
    home.refresh()
    assert home._tiles["exercise"].text() == "1/2회"


def test_타이머_카드는_상태에_따라_바뀐다(qapp):
    home = page()
    home.set_timer(State.RUNNING, 600, 1200, None)
    assert home._kicker.text() == "다음 눈 휴식까지" and home._clock.text() == "10:00"
    assert home._bar.filled == PROGRESS_CELLS // 2
    assert home._rest_button.isEnabled() and home._snooze_button.isHidden()
    home.set_timer(State.DUE, None, 1200, None)
    assert home._bar.filled == PROGRESS_CELLS
    assert not home._snooze_button.isHidden() and home._snooze_button.text() == "5분 미루기"
    home.set_timer(State.EXERCISING, None, None, "rest")
    assert home._kicker.text() == "눈 휴식 중" and not home._rest_button.isEnabled()
    home.set_timer(State.PAUSED, 300, 1200, None)
    assert home._clock.text() == "5:00" and not home._rest_button.isEnabled()


def test_미루기_버튼_글자는_설정의_미루기_시간을_따른다(qapp):
    home = page(settings=SettingsManager(Settings()).update({"snooze_minutes": 10}).settings)
    home.set_timer(State.DUE, None, 1200, None)
    assert home._snooze_button.text() == "10분 미루기"


def test_진행_바의_채워진_칸이_모래색으로_그려진다(qapp):
    bar = CellBar()  # 홈 화면 안의 바는 부모 레이아웃이 크기를 바꿀 수 있어서 따로 만들어 검사한다
    bar.resize(400, 10)
    bar.set_filled(filled_cells(timer_progress(900, 1200)))  # 25% → 5칸
    assert bar.filled == 5
    for index, sand in ((0, True), (4, True), (5, False), (PROGRESS_CELLS - 1, False)):
        center = bar.cell_rect(index).center().toPoint()
        assert (pixel(bar, center.x(), center.y()).name() == theme.color("sand").name()) is sand


# ---- 메인 창과 컨트롤러 ----


def make_window():
    clock = FakeClock()
    controller = Controller(ReminderScheduler(Settings(), clock, FakeIdle()), History(), now=clock.now)
    window = MainWindow(now=clock.now)
    window.attach_controller(controller)
    return window, controller, clock


def test_홈_화면은_컨트롤러의_남은_시간을_따라간다(qapp):
    window, controller, clock = make_window()
    assert window.home_page._clock.text() == "20:00"
    for _ in range(90):
        clock.advance(1)
        controller._on_tick()
    assert window.home_page._clock.text() == "18:30" and window.home_page._bar.filled == 1


def test_홈의_지금_휴식_버튼은_휴식을_시작한다(qapp):
    window, controller, _ = make_window()
    started = []
    controller.activity_started.connect(started.append)
    window.home_page._rest_button.click()
    assert started == ["rest"] and controller.state is State.EXERCISING
    assert window.home_page._kicker.text() == "눈 휴식 중"


def test_홈의_미루기_버튼은_알림을_미룬다(qapp):
    window, controller, clock = make_window()
    for _ in range(1200):
        clock.advance(1)
        controller._on_tick()
    assert controller.state is State.DUE and not window.home_page._snooze_button.isHidden()
    window.home_page._snooze_button.click()
    assert controller.state is State.SNOOZED
    assert window.home_page._kicker.text() == "다시 알림까지"


def test_눈_운동을_마치면_홈의_오늘_요약이_바뀐다(qapp):
    clock = FakeClock()
    history = History()
    controller = Controller(ReminderScheduler(Settings(), clock, FakeIdle()), history, now=clock.now)
    window = MainWindow(history, now=clock.now)
    window.attach_controller(controller)
    window.home_page._tz = KST
    assert window.home_page._tiles["exercise"].text() == "0/2회"
    controller.start_exercise()
    controller.complete_exercise("dot_follow", 60)
    assert window.home_page._tiles["exercise"].text() == "1/2회"


def test_설정에서_운동_목표를_바꾸면_홈이_따라간다(qapp):
    manager = SettingsManager(Settings())
    window = MainWindow(settings_manager=manager)
    manager.update({"exercises.daily_goal": 4})
    assert window.home_page._tiles["exercise"].text() == "0/4회"


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
    assert window.home_page._kicker.text() == "눈 운동 중"


def test_홈의_일시정지_버튼은_멈췄다가_이어서_센다(qapp):
    window, controller, clock = make_window()
    for _ in range(60):
        clock.advance(1)
        controller._on_tick()
    window.home_page._pause_button.click()
    assert controller.state is State.PAUSED
    assert window.home_page._pause_button.text() == "재개" and window.home_page._kicker.text() == "일시정지됨"
    assert not window.home_page._rest_button.isEnabled() and not window.home_page._exercise_button.isEnabled()
    window.home_page._pause_button.click()
    assert controller.state is State.RUNNING and window.home_page._pause_button.text() == "일시정지"
    assert window.home_page._clock.text() == "19:00"  # 멈춘 곳에서 이어서 센다


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
