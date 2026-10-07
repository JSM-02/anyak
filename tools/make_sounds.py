"""운동 안내 소리(`assets/sounds/*.wav`)를 합성한다. 외부 음원이나 의존성 없이 표준 라이브러리만 쓴다.

사용법 (프로젝트 폴더에서):
    .venv\\Scripts\\python tools\\make_sounds.py                      # assets/sounds에 4개 파일을 다시 만든다
    .venv\\Scripts\\python tools\\make_sounds.py 출력폴더              # 다른 폴더에 만든다
    .venv\\Scripts\\python tools\\make_sounds.py 출력폴더 --preview 미리듣기.wav   # 실제 흐름을 이어 붙인 미리듣기도 만든다

만드는 파일 (모두 16bit 모노 44.1kHz, 최대 음량 50%)
    prepare.wav   준비: 낮고 둥근 종 한 번과 잔잔한 화음
    cycle.wav     한 사이클(감기·유지·뜨기·쉬기). 감기 시작에 낮은 종, 뜨기 시작에 높은 종이 울린다
    finish.wav    마무리: 종 두 번이 올라가며 마친다
    look_away.wav 먼 곳 바라보기: 느리게 울리는 낮은 종 두 번

사이클 길이와 단계 시간은 `eyeexercise.core.exercises`의 상수를 그대로 가져온다. 그 상수를 바꾸면
이 스크립트를 다시 실행해 소리를 맞춰야 한다. (패키지가 설치돼 있어야 한다: pip install -e .)

이어지는 방법
    cycle.wav는 사이클 길이 + 겹침 1.5초 + 잔향 꼬리다. 앱이 사이클마다 다음 파일을 재생하면 앞 사이클의
    끝 1.5초와 다음 사이클의 앞 1.5초가 겹친다. 바탕(화음·숨결)이 서로 반대로 사라지고 나타나서 겹친 구간의
    크기가 일정하다. 화음은 주파수를 사이클 길이에 정수 번 진동하도록 맞춰서 겹쳐도 위상이 어긋나지 않는다.

기계음을 줄이는 방법
    - 잔향: 규칙적인 반사음 대신 불규칙한 반사음 수십 개를 더하고 어둡게 걸러서 금속성 울림을 없앤다
    - 화음: 같은 음을 미세하게 어긋나게 여러 겹 쌓고, 아주 느린 흔들림을 넣는다
    - 종: 실제 싱잉볼처럼 미세하게 울렁이는 쌍과, 부드럽게 두드리는 소리를 넣는다
    난수 시드가 고정돼 있어서 실행할 때마다 같은 파일이 나온다.
"""

import argparse
import math
import random
import struct
import wave
from pathlib import Path

from eyeexercise.core.exercises import (
    CLOSE_SECONDS,
    CYCLE_SECONDS,
    HOLD_SECONDS,
    OPEN_SECONDS,
    PREPARE_SECONDS,
    blink_timeline,
)

SR = 44100
PEAK = 0.5
PERIOD = CYCLE_SECONDS
OVERLAP = 1.5  # 다음 사이클과 겹치는 길이(초)
TAIL = 0.9  # 잔향 꼬리(초)
DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "sounds"

# 음높이(Hz)
G2, G3, C4, E4, G4, C5, D5 = 98.0, 196.0, 261.63, 329.63, 392.0, 523.25, 587.33


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def snap(f):
    """사이클 안에 정수 번 진동하도록 주파수를 맞춘다. 사이클을 겹쳐도 위상이 같다."""
    return round(f * PERIOD) / PERIOD


def mix(parts):
    """(시작 초, 샘플 목록) 여러 개를 겹쳐 하나로 만든다."""
    length = max(int(start * SR) + len(s) for start, s in parts)
    out = [0.0] * length
    for start, s in parts:
        off = int(start * SR)
        for i, v in enumerate(s):
            out[off + i] += v
    return out


def save(path, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", max(-32767, min(32767, round(v * 32767)))) for v in samples))


def lowpass(samples, cutoff):
    a = 1.0 - math.exp(-2 * math.pi * cutoff / SR)
    out, y = [], 0.0
    for x in samples:
        y += a * (x - y)
        out.append(y)
    return out


def lowpass_var(samples, cutoff_fn):
    out, y = [], 0.0
    for i, x in enumerate(samples):
        a = 1.0 - math.exp(-2 * math.pi * cutoff_fn(i / SR) / SR)
        y += a * (x - y)
        out.append(y)
    return out


def diffuse_reverb(samples, tail_seconds=TAIL, seed=3):
    """불규칙한 반사음 여러 개를 더하고 어둡게 걸러서 부드럽게 퍼지는 잔향을 만든다."""
    rng = random.Random(seed)
    n = len(samples)
    wet = [0.0] * (n + int(tail_seconds * SR))
    for _ in range(48):
        delay = rng.uniform(0.03, tail_seconds)
        gain = 0.2 * math.exp(-delay / 0.4) * rng.uniform(0.6, 1.0)
        d = int(delay * SR)
        seg = wet[d : d + n]
        wet[d : d + n] = [w + s * gain for w, s in zip(seg, samples)]
    wet = lowpass(wet, 1800)
    out = samples + [0.0] * int(tail_seconds * SR)
    return [o + w for o, w in zip(out, wet)]


def bowl(duration, freq, tau, level=1.0, seed=1):
    """싱잉볼: 미세하게 울렁이는 쌍(실제 볼의 특징) + 부드럽게 두드리는 소리."""
    n = int(duration * SR)
    partials = ((1.0, 1.0, 1.0), (1.0035, 0.7, 1.0), (2.0, 0.2, 0.55), (3.9, 0.06, 0.25))  # (배율, 세기, 감쇠 배율)
    out = []
    for i in range(n):
        t = i / SR
        attack = smooth(t / 0.07)
        s = sum(a * math.sin(2 * math.pi * freq * r * t) * math.exp(-t / (tau * d)) for r, a, d in partials)
        out.append(level * attack * s)
    rng = random.Random(seed)
    thump = lowpass([rng.uniform(-1, 1) for _ in range(int(0.12 * SR))], 500)
    for i, v in enumerate(thump):
        out[i] += level * 0.5 * v * math.exp(-i / SR / 0.03)
    return out


def pad(length, voices, level, fade_in, fade_out, periodic):
    """고정된 음높이의 화음. 같은 음을 어긋나게 겹치고 느리게 흔들어 살아 있는 소리로 만든다."""
    n = int(length * SR)
    out = []
    detunes = (0.0, 3 / PERIOD, -2 / PERIOD)  # 사이클 길이에 맞춘 미세한 어긋남(코러스)
    for i in range(n):
        t = i / SR
        s = 0.0
        for vi, (f, amp) in enumerate(voices):
            for di, dt in enumerate(detunes):
                ff = snap(f) + dt
                vib = 0.5 * math.sin(2 * math.pi * (2 / PERIOD) * t + vi + di)  # 느린 흔들림(주기에 맞춤)
                s += amp * math.sin(2 * math.pi * ff * t + vib)
        out.append(level * s / 3.0 * (periodic(t) if periodic else 1.0) * fade_in(t) * fade_out(t))
    return out


def breath(length, shape, level, fade_in, fade_out, seed):
    """필터를 거친 아주 부드러운 바람 소리. shape(t)로 크기와 밝기가 숨 쉬듯 변한다."""
    rng = random.Random(seed)
    noise = [rng.uniform(-1, 1) for _ in range(int(length * SR))]
    cutoff = lambda t: 500 + 700 * shape(t % PERIOD)  # noqa: E731
    filtered = lowpass_var(lowpass_var(noise, cutoff), cutoff)
    return [level * shape((i / SR) % PERIOD) * v * fade_in(i / SR) * fade_out(i / SR) for i, v in enumerate(filtered)]


def finalize(samples):
    """전체를 어둡게 다듬고 최대 음량을 맞춘다. 끝의 클릭만 막는다."""
    dark = lowpass(samples, 2400)
    peak = max(abs(v) for v in dark) or 1.0
    out = [v * (PEAK / peak) for v in dark]
    fade = int(0.05 * SR)
    for i in range(fade):
        out[len(out) - 1 - i] *= i / fade
    return out


def edge_fades(total, fade=0.6):
    """양 끝을 부드럽게 줄이는 (들어오는, 나가는) 곡선."""
    return (
        lambda t: math.sin(math.pi / 2 * min(1.0, t / fade)) ** 2,
        lambda t: math.cos(math.pi / 2 * min(1.0, max(0.0, (t - (total - fade)) / fade))) ** 2,
    )


def cycle_track():
    t_hold = CLOSE_SECONDS  # 감기 끝, 유지 시작
    t_open = CLOSE_SECONDS + HOLD_SECONDS  # 뜨기 시작: 높은 종
    length = PERIOD + OVERLAP

    # 겹치는 구간(사이클 끝 1.5초 ↔ 다음 사이클 앞 1.5초)에서 합이 일정하도록 서로 반대로 사라지고 나타난다.
    # 화음은 위상이 같아 sin²/cos²(합 1), 숨결은 위상이 달라 sin/cos(제곱합 1)를 쓴다.
    def fin_pad(t):
        return math.sin(math.pi / 2 * min(1.0, t / OVERLAP)) ** 2

    def fout_pad(t):
        return math.cos(math.pi / 2 * min(1.0, max(0.0, (t - PERIOD) / OVERLAP))) ** 2

    def fin_noise(t):
        return math.sin(math.pi / 2 * min(1.0, t / OVERLAP))

    def fout_noise(t):
        return math.cos(math.pi / 2 * min(1.0, max(0.0, (t - PERIOD) / OVERLAP)))

    def swell(t):  # 사이클 가운데에서 가장 부풀고 양 끝에서도 완전히 꺼지지 않는다 (주기 함수)
        return 0.45 + 0.55 * math.sin(math.pi * t / PERIOD) ** 2

    def shape(t):  # 숨결 크기. 주기의 처음과 끝 값이 같다(0.35)
        if t < t_hold:  # 눈을 천천히 감을 때: 숨을 내쉬듯 가라앉는다
            return 0.35 - 0.23 * smooth(t / t_hold)
        if t < t_open:  # 감은 채 머문다: 고요하다
            return 0.12
        if t < t_open + OPEN_SECONDS:  # 눈을 천천히 뜰 때: 숨을 들이쉬듯 차오른다
            return 0.12 + 0.68 * smooth((t - t_open) / OPEN_SECONDS)
        return 0.8 - 0.45 * smooth((t - t_open - OPEN_SECONDS) / (PERIOD - t_open - OPEN_SECONDS))

    chord = pad(length, [(G2, 0.9), (G3, 0.7), (C4, 0.55), (E4, 0.4)], 0.55, fin_pad, fout_pad, swell)
    wind = breath(length, shape, 0.9, fin_noise, fout_noise, seed=7)
    low = bowl(3.2, G4, 1.2, 0.9, seed=11)  # 감기 시작: 낮고 둥근 종
    high = bowl(3.2, C5, 1.1, 0.7, seed=12)  # 뜨기 시작: 한 단계 높고 맑은 종

    n = int(length * SR)
    bed = [a + b for a, b in zip(chord, wind)]
    mixed = mix([(0.0, bed), (0.0, low), (float(t_open), high)])[: n + int(TAIL * SR)]
    return finalize(diffuse_reverb(mixed))


def prepare_track():
    fi, fo = edge_fades(2.4)
    parts = [(0.0, pad(2.4, [(G3, 0.7), (C4, 0.55)], 0.35, fi, fo, None)), (0.1, bowl(2.0, G4, 1.0, 0.9, 21))]
    return finalize(diffuse_reverb(mix(parts)))


def finish_track():
    fi, fo = edge_fades(2.8)
    parts = [
        (0.0, bowl(2.2, G4, 0.9, 0.8, 22)),
        (0.45, bowl(2.2, C5, 1.0, 0.9, 23)),
        (0.0, pad(2.8, [(C4, 0.5), (G3, 0.6)], 0.3, fi, fo, None)),
    ]
    return finalize(diffuse_reverb(mix(parts)))


def look_away_track():
    fi, fo = edge_fades(3.4, 0.9)
    parts = [
        (0.0, pad(3.4, [(G2, 0.8), (G3, 0.7), (D5 / 2, 0.4)], 0.4, fi, fo, None)),
        (0.0, bowl(3.0, C4, 1.6, 0.8, 24)),
        (1.0, bowl(2.6, G4, 1.4, 0.7, 25)),
    ]
    return finalize(diffuse_reverb(mix(parts)))


def preview(tracks, duration_seconds=30):
    """앱이 재생할 타이밍 그대로 이어 붙인 미리듣기. 사이클은 사이클 길이마다 겹쳐서 재생한다."""
    timeline = blink_timeline(duration_seconds)
    parts = [(0.0, tracks["prepare"])]
    for i in range(timeline.cycles):
        parts.append((PREPARE_SECONDS + i * PERIOD, tracks["cycle"]))
    parts.append((timeline.total_seconds - 3, tracks["finish"]))
    parts.append((float(timeline.total_seconds), tracks["look_away"]))
    mixed = mix(parts)
    peak = max(abs(v) for v in mixed)
    return [v * (PEAK / peak) for v in mixed]


def main():
    parser = argparse.ArgumentParser(description="운동 안내 소리를 합성한다.")
    parser.add_argument("out_dir", nargs="?", type=Path, default=DEFAULT_OUT_DIR, help="출력 폴더 (기본: assets/sounds)")
    parser.add_argument("--preview", type=Path, help="실제 흐름을 이어 붙인 미리듣기 파일 경로")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    tracks = {
        "cycle": cycle_track(),
        "prepare": prepare_track(),
        "finish": finish_track(),
        "look_away": look_away_track(),
    }
    for name, samples in tracks.items():
        save(args.out_dir / f"{name}.wav", samples)
        print(f"{args.out_dir / (name + '.wav')}  {len(samples) / SR:.2f}초")
    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        save(args.preview, preview(tracks))
        print(f"{args.preview}  미리듣기")


if __name__ == "__main__":
    main()
