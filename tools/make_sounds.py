"""운동 안내 소리(`assets/sounds/*.wav`)를 합성한다. 외부 음원이나 의존성 없이 표준 라이브러리만 쓴다.

사용법 (프로젝트 폴더에서):
    .venv\\Scripts\\python tools\\make_sounds.py                      # assets/sounds에 4개 파일을 다시 만든다
    .venv\\Scripts\\python tools\\make_sounds.py 출력폴더              # 다른 폴더에 만든다
    .venv\\Scripts\\python tools\\make_sounds.py 출력폴더 --preview 미리듣기.wav   # 실제 흐름을 이어 붙인 미리듣기도 만든다

만드는 파일 (모두 16bit 모노 44.1kHz, 최대 음량 50%)
    prepare.wav   준비: 낮고 둥근 종 한 번과 잔잔한 화음
    finish.wav    마무리: 종 두 번이 올라가며 마친다
    look_away.wav 먼 곳 바라보기: 느리게 울리는 낮은 종 두 번
    alert.wav     알림 팝업: 짧고 부드러운 종 두 번이 올라가며 울린다 (놀라지 않게 작고 맑게)

소리 합성에 쓰는 기준 길이(`PERIOD`)는 예전 깜빡임 사이클 길이(6초)와 같게 두었다. 그래야 기존 소리 파일이 그대로 다시 만들어진다.

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

SR = 44100
PEAK = 0.5
PERIOD = 6  # 소리 합성의 기준 길이(초). 화음의 주파수와 미세한 어긋남을 이 길이에 맞춘다(예전 깜빡임 사이클 길이와 같다)
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


def alert_track():
    """알림 팝업이 뜰 때 나는 소리. 일하는 중에 울려도 놀라지 않도록 짧고 작고 맑게 만든다."""
    parts = [(0.0, bowl(1.3, E4 * 2, 0.45, 0.55, 26)), (0.22, bowl(1.6, C5 * 1.5, 0.55, 0.6, 27))]
    return [v * 0.7 for v in finalize(diffuse_reverb(mix(parts), tail_seconds=0.6))]  # 운동 안내보다 작게


def preview(tracks):
    """앱이 재생할 타이밍 그대로 이어 붙인 미리듣기. 점 따라가기(준비 → 마무리) 다음에 눈 휴식의 먼 곳 바라보기가 이어지는 모양이다."""
    parts = [
        (0.0, tracks["prepare"]),
        (57.0, tracks["finish"]),  # 점 따라가기 60초: 마무리 3초 전
        (70.0, tracks["look_away"]),  # 눈 휴식 시작
        (91.0, tracks["finish"]),  # 20초가 지났다
    ]
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
        "prepare": prepare_track(),
        "finish": finish_track(),
        "look_away": look_away_track(),
        "alert": alert_track(),
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
