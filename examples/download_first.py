"""Download the oldest pending submission using WCA's first() API."""

import sys

import wca


def main() -> int:
    try:
        submission = wca.first()
    except (wca.WCAError, OSError) as error:
        print(f"가져오기 실패: {error}", file=sys.stderr)
        return 1

    if submission is None:
        print("결과가 X인 제출이 없습니다.")
        return 0

    print("이름:", submission["name"])
    print("원래 파일 이름:", submission["file_name"])
    print("다운로드 경로:", submission["path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
