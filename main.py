import json
import math
import re
import time
from pathlib import Path


EPSILON = 1e-9
REPEAT = 100


def validate_matrix(matrix, n):
    """n×n 배열인지, 모든 값이 유한한 숫자인지 검사한다."""
    if not isinstance(matrix, list) or len(matrix) != n:
        raise ValueError(f"행 개수는 {n}개여야 합니다.")

    for i, row in enumerate(matrix, 1):
        if not isinstance(row, list) or len(row) != n:
            raise ValueError(f"{i}행의 숫자는 {n}개여야 합니다.")

        for value in row:
            if isinstance(value, bool) or not isinstance(
                value, (int, float)
            ):
                raise ValueError(f"{i}행에 숫자가 아닌 값이 있습니다.")

            try:
                finite = math.isfinite(value)
            except OverflowError:
                finite = False

            if not finite:
                raise ValueError("유한한 범위의 숫자만 입력하세요.")

    return matrix


def read_matrix(name):
    """입력 오류가 있으면 해당 행을 다시 입력받는다."""
    print(f"\n[{name} 입력]")
    print("각 줄에 숫자 3개를 공백으로 구분하세요.")

    matrix = []

    for i in range(3):
        while True:
            try:
                text = input(f"{i + 1}행: ")
                row = [float(value) for value in text.split()]

                if len(row) != 3:
                    raise ValueError("숫자 3개가 필요합니다.")

                if not all(math.isfinite(value) for value in row):
                    raise ValueError("유한한 숫자만 허용됩니다.")

                matrix.append(row)
                break

            except ValueError as error:
                print(f"입력 형식 오류: {error}")
                print("예시: 0 1 0")

    print(f"저장된 {name}:")
    for row in matrix:
        print(row)

    return matrix


def mac(pattern, kernel):
    """검증된 같은 크기 배열의 위치별 곱을 누적한다."""
    score = 0.0
    n = len(pattern)

    for i in range(n):
        for j in range(n):
            score += pattern[i][j] * kernel[i][j]

    if not math.isfinite(score):
        raise ValueError("MAC 결과가 숫자 표현 범위를 초과했습니다.")

    return score


def decide(score_a, score_b, label_a, label_b):
    if abs(score_a - score_b) < EPSILON:
        return "UNDECIDED"

    if score_a > score_b:
        return label_a

    return label_b


def normalize_label(label):
    if not isinstance(label, str):
        raise ValueError("라벨은 문자열이어야 합니다.")

    labels = {
        "+": "Cross",
        "cross": "Cross",
        "x": "X",
    }

    normalized = labels.get(label.strip().lower())

    if normalized is None:
        raise ValueError(f"지원하지 않는 라벨: {label}")

    return normalized


def generate_pattern(n, label):
    """성능 측정에도 사용할 기본 패턴을 생성한다."""
    matrix = []

    for i in range(n):
        row = []

        for j in range(n):
            if label == "Cross":
                value = i == n // 2 or j == n // 2
            else:
                value = i == j or i + j == n - 1

            row.append(float(value))

        matrix.append(row)

    return matrix


def benchmark(samples):
    print(f"\n[성능 분석: 단일 MAC 호출, {REPEAT}회 평균]")
    print("크기       평균 시간(ms)    연산 횟수(N²)")
    print("-" * 44)

    for n in sorted(samples):
        pattern, kernel = samples[n]

        # 첫 호출 준비 비용은 측정에서 제외한다.
        mac(pattern, kernel)

        total_ns = 0

        for _ in range(REPEAT):
            start = time.perf_counter_ns()
            mac(pattern, kernel)
            total_ns += time.perf_counter_ns() - start

        average_ms = total_ns / REPEAT / 1_000_000

        print(
            f"{n:2}×{n:<2}      "
            f"{average_ms:12.6f}    "
            f"{n * n:6}"
        )


def user_mode():
    filter_a = read_matrix("필터 A")
    filter_b = read_matrix("필터 B")
    pattern = read_matrix("패턴")

    start = time.perf_counter_ns()

    score_a = mac(pattern, filter_a)
    score_b = mac(pattern, filter_b)

    elapsed_ms = (
        time.perf_counter_ns() - start
    ) / 1_000_000

    result = decide(score_a, score_b, "A", "B")

    print("\n[MAC 결과]")
    print(f"A 점수: {score_a:.17g}")
    print(f"B 점수: {score_b:.17g}")
    print(f"연산 시간(두 MAC 호출): {elapsed_ms:.6f} ms")

    if result == "UNDECIDED":
        print("판정: 판정 불가 (UNDECIDED)")
    else:
        print(f"판정: {result}")

    benchmark({3: (pattern, filter_a)})


def load_filter_group(raw_filters, n):
    if not isinstance(raw_filters, dict):
        raise ValueError("filters는 객체여야 합니다.")

    key = f"size_{n}"
    group = raw_filters.get(key)

    if not isinstance(group, dict):
        raise ValueError(f"{key} 필터 객체가 없습니다.")

    normalized = {}

    for label, matrix in group.items():
        standard_label = normalize_label(label)

        if standard_label in normalized:
            raise ValueError(
                f"중복 필터 라벨: {standard_label}"
            )

        normalized[standard_label] = validate_matrix(matrix, n)

    if set(normalized) != {"Cross", "X"}:
        raise ValueError("Cross와 X 필터가 모두 필요합니다.")

    return normalized


def json_mode():
    # 실행 위치가 달라도 main.py 옆의 파일을 읽는다.
    path = Path(__file__).resolve().with_name("data.json")

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)
    except (OSError, ValueError) as error:
        print(f"파일 읽기 오류: {error}")
        return

    if not isinstance(data, dict):
        print("스키마 오류: 최상위 데이터는 객체여야 합니다.")
        return

    patterns = data.get("patterns")

    if not isinstance(patterns, dict):
        print("스키마 오류: patterns는 객체여야 합니다.")
        return

    raw_filters = data.get("filters")
    filters = {}
    filter_errors = {}

    print("\n[필터 로드]")

    for n in (5, 13, 25):
        try:
            filters[n] = load_filter_group(raw_filters, n)
            print(f"size_{n}: Cross, X 로드 완료")
        except (ValueError, OverflowError) as error:
            filter_errors[n] = str(error)
            print(f"size_{n}: 오류 — {error}")

    # 데이터가 잘못되어도 필수 크기의 성능 표는 출력한다.
    samples = {}

    for n in (3, 5, 13, 25):
        cross = generate_pattern(n, "Cross")
        samples[n] = (cross, cross)

    measured_sizes = set()
    failures = []
    passed = 0

    print("\n[패턴 분석]")

    for case_id, case in patterns.items():
        print(f"\n--- {case_id} ---")

        try:
            match = re.fullmatch(
                r"size_([1-9][0-9]*)_([0-9]+)", case_id
            )

            if match is None:
                raise ValueError(
                    "패턴 키는 size_N_idx 형식이어야 합니다."
                )

            n = int(match.group(1))

            if n in filter_errors:
                raise ValueError(filter_errors[n])

            if n not in filters:
                filters[n] = load_filter_group(raw_filters, n)

            if not isinstance(case, dict):
                raise ValueError("패턴 항목은 객체여야 합니다.")

            expected = normalize_label(case.get("expected"))
            pattern = validate_matrix(case.get("input"), n)
            group = filters[n]

            score_cross = mac(pattern, group["Cross"])
            score_x = mac(pattern, group["X"])

            result = decide(
                score_cross, score_x, "Cross", "X"
            )

            print(f"Cross 점수: {score_cross:.17g}")
            print(f"X 점수: {score_x:.17g}")

            if result == expected:
                passed += 1
                status = "PASS"
            else:
                status = "FAIL"

                if result == "UNDECIDED":
                    reason = (
                        f"점수 차이가 {EPSILON} 미만으로 동점. "
                        f"expected는 {expected}"
                    )
                else:
                    reason = (
                        f"판정 {result}와 "
                        f"expected {expected}가 다름"
                    )

                failures.append((case_id, reason))

            print(
                f"판정: {result} | "
                f"expected: {expected} | {status}"
            )

            if n not in measured_sizes:
                samples[n] = (pattern, group["Cross"])
                measured_sizes.add(n)

        except (ValueError, TypeError, OverflowError) as error:
            reason = f"스키마/수치 오류: {error}"
            failures.append((case_id, reason))
            print(f"FAIL | {reason}")

    print("\n실제 데이터의 첫 유효 케이스로 성능을 측정합니다.")
    print("해당 데이터가 없는 크기는 생성한 Cross 패턴을 사용합니다.")
    benchmark(samples)

    print("\n[결과 요약]")
    print(f"총 테스트: {len(patterns)}개")
    print(f"통과: {passed}개")
    print(f"실패: {len(failures)}개")

    if failures:
        print("\n실패 케이스:")

        for case_id, reason in failures:
            print(f"- {case_id}: {reason}")
    else:
        print("실패 케이스 없음")


def main():
    print("=== Mini NPU Simulator ===")

    while True:
        print("\n1. 사용자 입력 (3×3)")
        print("2. data.json 분석")
        mode = input("선택: ").strip()

        if mode == "1":
            user_mode()
            break

        if mode == "2":
            json_mode()
            break

        print("1 또는 2를 입력하세요.")


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print("\n프로그램을 종료합니다.")
    except (ValueError, OverflowError) as error:
        print(f"연산 오류: {error}")