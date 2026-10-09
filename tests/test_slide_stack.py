from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QLabel

from eyeexercise.ui.slide_stack import SlideStack


def make_stack(animations=lambda: True, shown=True):
    stack = SlideStack(animations=animations)
    for text in ("가", "나", "다"):
        stack.addWidget(QLabel(text))
    stack.resize(400, 300)
    if shown:
        stack.show()
    return stack


def test_보이지_않는_창에서는_움직임_없이_바로_바뀐다(qapp):
    stack = make_stack(shown=False)
    stack.setCurrentIndex(2)
    assert stack.currentIndex() == 2 and not stack.sliding


def test_애니메이션을_끄면_바로_바뀐다(qapp):
    stack = make_stack(animations=lambda: False)
    stack.setCurrentIndex(1)
    assert stack.currentIndex() == 1 and not stack.sliding


def test_오른쪽_메뉴로_가면_새_화면이_오른쪽에서_들어온다(qapp):
    stack = make_stack()
    old, new = stack.widget(0), stack.widget(1)
    stack.setCurrentIndex(1)
    assert stack.sliding and stack.currentWidget() is new  # 미끄러지는 동안에도 가려는 화면을 가리킨다
    assert new.isVisible() and new.pos() == QPoint(400, 0) and old.isVisible()


def test_왼쪽_메뉴로_가면_새_화면이_왼쪽에서_들어온다(qapp):
    stack = make_stack()
    stack.setCurrentIndex(2)
    stack._finish()
    stack.setCurrentIndex(0)
    assert stack.widget(0).pos() == QPoint(-400, 0)


def test_끝나면_떠난_화면은_숨고_새_화면은_제자리에_있다(qapp):
    stack = make_stack()
    old, new = stack.widget(0), stack.widget(1)
    stack.setCurrentIndex(1)
    stack._finish()
    assert not stack.sliding and stack.currentIndex() == 1
    assert old.isHidden() and new.isVisible() and new.pos() == QPoint(0, 0) and old.pos() == QPoint(0, 0)


def test_미끄러지는_중에_다시_고르면_앞의_것을_끝내고_이어서_간다(qapp):
    stack = make_stack()
    stack.setCurrentIndex(1)
    stack.setCurrentIndex(2)
    assert stack.currentIndex() == 2 and stack.widget(0).isHidden()  # 처음 이동은 끝났고 1→2가 진행 중이다
    stack._finish()
    assert stack.currentWidget() is stack.widget(2) and stack.widget(2).pos() == QPoint(0, 0)


def test_같은_화면이나_없는_번호는_무시한다(qapp):
    stack = make_stack()
    stack.setCurrentIndex(0)
    stack.setCurrentIndex(9)
    assert not stack.sliding and stack.currentIndex() == 0
