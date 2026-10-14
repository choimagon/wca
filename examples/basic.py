"""Run after loading the environment variables described in README.md."""
import wca

print(wca.list())
submission = wca.frist()
if submission is None:
    print("결과가 X인 제출이 없습니다.")
else:
    print("이름:", submission["name"])
    print("원래 파일 이름:", submission["file_name"])
    print("다운로드 경로:", submission["path"])
    # 직접 채점한 뒤 다음처럼 결과를 저장하세요.
    # wca.spend(submission["name"], 100, submission_id=submission["id"])
