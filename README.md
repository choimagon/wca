# WCA 사용법

Python 3.10 이상에서 사용합니다.

```bash
git clone https://github.com/choimagon/wca.git
cd wca
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
```

기존 설치를 업데이트하려면 저장소에서 `git pull` 후 `python -m pip install --upgrade .`를 실행합니다.

## 파일과 이름 가져오기

키는 Supabase 관리자 Secret key를 사용합니다.

```python
from getpass import getpass
import wca

key = getpass("Supabase 관리자 키: ")
submission = wca.first(key)

if submission is None:
    print("결과가 X인 제출이 없습니다.")
else:
    print("이름:", submission["name"])
    print("파일 이름:", submission["file_name"])
    print("다운로드 경로:", submission["path"])
```

결과가 `X`인 제출 중 가장 오래된 파일을 `downloads/`에 저장합니다. 폴더를 바꾸려면 `wca.first(key, download_dir="received")`로 호출합니다.

입력형 예제를 실행하려면:

```bash
python examples/download_first.py
```

## 전체 목록 가져오기

`first(key)` 호출 후에는 같은 키를 계속 사용합니다.

```python
rows = wca.list()
for row in rows:
    print(row["name"], row["file_name"], row["result"])
```

## 결과 저장하기

```python
wca.spend("홍길동", 100)
```

해당 이름의 가장 오래된 `X` 제출 1건에 결과를 저장합니다. 다운로드한 제출을 정확히 지정하려면:

```python
if submission is not None:
    wca.spend(submission["name"], 100, submission_id=submission["id"])
```

저장 후 웹 목록을 새로고침하면 결과가 표시됩니다.
