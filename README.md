# WCA

IMEL 개인 대회 제출 데이터를 조회하고, 결과가 `X`인 Python 파일을 다운로드하고, 결과를 저장하는 Python 관리자 라이브러리입니다. 패키지 이름은 **WCA**, Python에서 사용하는 이름은 **`wca`**입니다.

| 명령어 | 동작 | 반환값 |
| --- | --- | --- |
| `wca.list()` | 현재 제출 전체를 업로드가 오래된 순서로 조회 | 메타데이터 딕셔너리 목록 |
| `wca.first(키)` 또는 `wca.frist()` | 결과가 `X`인 제출 중 가장 오래된 `.py` 파일 다운로드 | 이름·파일 정보·다운로드 경로 딕셔너리, 없으면 `None` |
| `wca.spend(이름, 값)` | 해당 이름의 가장 오래된 미처리 제출 1건에 결과 저장 | 갱신한 제출 딕셔너리 |

요청한 `frist()`도 계속 지원합니다. `first(키)`로 관리자 키를 직접 전달하거나, 기존처럼 환경변수를 설정한 뒤 `first()`로 호출할 수 있습니다.

## 설치

Python **3.10 이상**과 Git이 필요합니다. 실행에 추가 Python 패키지는 필요하지 않습니다.

macOS / Linux:

```bash
git clone https://github.com/choimagon/wca.git
cd wca
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
```

Windows PowerShell:

```powershell
git clone https://github.com/choimagon/wca.git
cd wca
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install .
```

설치 후 다른 폴더의 Python 프로그램에서도 `import wca`로 사용합니다. 개발하면서 소스를 바로 반영하려면 `python -m pip install -e .`로 설치합니다.

## 키를 직접 넣어 다운로드하기

환경변수를 설정하지 않아도 다음처럼 사용할 수 있습니다. 입력한 관리자 키는 화면에 표시되지 않습니다.

```python
from getpass import getpass
import wca

key = getpass("Supabase 관리자 키: ")
submission = wca.first(key)
if submission is not None:
    print("이름:", submission["name"])
    print("다운로드 경로:", submission["path"])
```

`first(key)`로 전달한 키는 현재 Python 프로세스의 WCA 클라이언트에 적용됩니다. 이후 `wca.list()`나 `wca.spend(...)`도 같은 키를 사용하며, 파일이나 환경변수에 키를 저장하지 않습니다. 이미 `configure()`로 정한 URL·저장 폴더·timeout은 유지됩니다.

저장 폴더를 바꾸려면 `wca.first(key, download_dir="received")`로 호출합니다. `first()`의 첫 번째 인자는 키이며, 폴더는 `download_dir=`로 지정합니다.

## Supabase 설정

현재 프로젝트 URL은 기본값으로 연결되어 있습니다:

```text
https://ufzrasrrhsmkfxribyqp.supabase.co
```

파일 원문 다운로드와 결과 수정에는 **관리자 비밀 키**가 필요합니다. Supabase 프로젝트의 **Settings → API Keys → Secret keys**에서 `sb_secret_...` 키를 가져와 `first(키)`에 전달하거나 관리자 PC·서버의 환경변수로 설정하세요. 기존 `service_role` 키도 지원합니다. 웹에서 쓰는 `sb_publishable_...` 공개 키는 사용할 수 없습니다. 비밀 키는 `.env` 등 로컬에만 보관하며, 웹사이트·GitHub·채팅에 넣지 않습니다. [Supabase API 키 안내](https://supabase.com/docs/guides/getting-started/api-keys)

macOS / Linux에서는 다음과 같이 설정합니다:

```bash
cp .env.example .env
# .env 파일을 편집해서 WCA_SUPABASE_SECRET_KEY를 실제 비밀 키로 바꿉니다.
set -a
source .env
set +a
```

`.env`는 Git에서 제외됩니다. WCA가 파일을 자동으로 읽지는 않으므로 새 터미널에서 사용할 때는 위의 `source` 단계로 환경변수를 다시 불러오세요.

Windows PowerShell에서는 환경변수를 직접 설정합니다:

```powershell
$env:WCA_SUPABASE_URL = "https://ufzrasrrhsmkfxribyqp.supabase.co"
$env:WCA_SUPABASE_SECRET_KEY = "여기에 실제 비밀 키"
$env:WCA_DOWNLOAD_DIR = "downloads"
```

| 환경변수 | 기본값 / 용도 |
| --- | --- |
| `WCA_SUPABASE_URL` | 위 프로젝트 URL |
| `WCA_SUPABASE_SECRET_KEY` | `first(키)`에 키를 전달하지 않을 때 사용하는 관리자 키 |
| `WCA_DOWNLOAD_DIR` | `downloads`, 파일 저장 폴더 |

일반적인 `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_SERVICE_ROLE_KEY` 환경변수도 지원합니다. `WCA_` 변수가 우선합니다.

## 사용 예제

```python
import wca

# 1. 제출 목록 가져오기
for row in wca.list():
    print(row["name"], row["file_name"], row["result"])

# 2. 가장 먼저 업로드된 미처리 파일과 이름 가져오기
submission = wca.frist()
if submission is None:
    print("결과가 X인 제출이 없습니다.")
else:
    print("이름:", submission["name"])
    print("원래 파일 이름:", submission["file_name"])
    print("다운로드한 파일:", submission["path"])

    # 3. 직접 계산한 결과 저장
    score = 100
    updated = wca.spend(
        submission["name"], score, submission_id=submission["id"]
    )
    print("저장된 결과:", updated["result"])
```

`first(키)`로 가장 오래된 미처리 파일을 가져오고 이름·다운로드 경로를 출력하려면 다음 예제를 실행하세요:

```bash
python examples/download_first.py
```

실행하면 관리자 키를 입력받습니다. Enter만 누르면 기존 환경변수를 사용합니다. 이 예제는 `wca.first(키)`로 다운로드하고 결과값은 수정하지 않습니다. 미처리 제출이 없으면 안내 문구를 출력하며, 연결·설정·파일 저장 오류는 종료 코드 1로 알립니다.

전체 목록 조회도 포함한 기존 예제는 `python examples/basic.py`로 실행할 수 있습니다.

### `wca.list()`

미처리·처리 완료를 모두 포함해 전체 제출을 반환합니다. 파일 원문은 다운로드하지 않습니다. 같은 업로드 시각이면 제출 ID로 순서를 정합니다.

```python
[
    {
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "name": "홍길동",
        "team_name": "홍길동",
        "file_name": "solution.py",
        "file_size": 1234,
        "created_at": "2026-10-14T04:05:06+00:00",
        "result": "X",
    }
]
```

`name`과 `team_name`은 같은 제출자 이름입니다. 기존 데이터베이스 컬럼명이 `team_name`이므로 호환성을 위해 두 이름을 반환합니다. 시각은 서버의 UTC 값이며 웹에서는 한국 시간으로 표시합니다. 목록은 페이지를 이어서 가져오므로 500건을 넘어도 조회할 수 있습니다.

### `wca.first(secret_key=None, *, download_dir=None)` / `wca.frist(download_dir=None)`

결과가 정확히 `X`인 가장 오래된 제출을 다운로드합니다. 저장 경로는 기본적으로 `downloads/<제출 ID>.py`입니다. 원래 파일 이름이 같아도 서로 다른 제출은 다른 경로에 저장됩니다. 파일 내용은 실행하거나 변환하지 않고 원본 바이트로 저장합니다.

반환값은 `list()`의 제출 정보에 `path`가 추가된 딕셔너리입니다. `path`는 절대 경로의 `pathlib.Path` 객체입니다.

```python
submission = wca.frist(download_dir="received")
if submission:
    name = submission["name"]      # submission["team_name"]도 동일
    path = submission["path"]
    print(name, str(path))
```

미처리 제출이 없으면 `None`을 반환합니다. 다운로드 실패는 예외로 알립니다. 다운로드만으로 `X`가 바뀌지는 않으므로 결과 저장 전에는 다시 호출해도 같은 제출을 가져올 수 있습니다.

### `wca.spend(name, value, *, submission_id=None)`

```python
wca.spend("홍길동", 100)
wca.spend("홍길동", "정답", submission_id=submission["id"])
```

결과는 문자열 또는 숫자를 받을 수 있으며 DB에는 문자열로 저장합니다. 예를 들어 `100`은 `"100"`으로 저장됩니다. 이름은 정확히 일치해야 합니다.

- `submission_id` 없이 호출하면 해당 이름의 가장 오래된 `X` 제출 **1건만** 갱신합니다.
- `submission_id`를 지정하면 이름과 ID가 모두 일치하는 미처리 제출만 갱신합니다. 다운로드한 파일의 결과를 저장할 때 이 방식을 사용하세요.
- 이미 처리된 제출은 덮어쓰지 않습니다. 해당 미처리 제출이 없으면 `WCANotFoundError`, 조회 후 다른 작업자가 먼저 처리했다면 `WCAConflictError`가 발생합니다.
- `"X"`는 미처리 표시입니다. 이 값을 저장하면 계속 다운로드 대상에 남습니다.

저장 후 웹사이트의 목록 새로고침 버튼을 누르면 새 결과를 볼 수 있습니다.

`frist()`는 작업 예약이나 잠금 기능을 제공하지 않습니다. 여러 작업자가 동시에 호출하면 같은 파일을 받을 수 있습니다. 단일 채점 작업자로 사용하거나 외부에서 작업 배분을 관리하세요.

## 독립적인 클라이언트 / 오류 처리

```python
from wca import WCA, WCAError

client = WCA(download_dir="received", timeout=30)
try:
    rows = client.list()
    submission = client.frist()
except WCAError as error:
    print("관리자 작업 실패:", error)
```

`wca.configure(download_dir="received", timeout=60)`으로 모듈 전체 설정을 바꿀 수도 있습니다. URL과 키를 직접 인자로 전달할 때는 `WCA(url=..., secret_key=...)` 또는 `wca.configure(url=..., secret_key=...)`를 사용합니다. 키는 `getpass()`로 입력받거나 환경변수에서 읽으세요.

설정 오류는 `WCAConfigError`, 서버·다운로드 오류는 `WCAAPIError`입니다. `WCAAPIError.status`와 `.code`로 서버 오류 종류를 확인할 수 있습니다. 파일 저장 폴더의 권한 등 로컬 파일 시스템 오류는 `OSError`로 전달됩니다.

## 데이터베이스 연결 구조

WCA는 `public.team_submissions` 테이블의 `id`, `team_name`, `file_name`, `file_size`, `created_at`, `result`를 사용합니다. 원본 파일은 비공개 `team-python-files` 버킷에서 행의 `storage_path`로 조회합니다. `result` 기본값은 `X`입니다. 다운로드와 결과 수정은 관리자 권한에서만 수행합니다.

현재 IMEL 프로젝트에는 결과 컬럼 설정이 적용되어 있습니다. 새 Supabase 프로젝트에 연결할 경우 [웹사이트 저장소](https://github.com/choimagon/contest_web)의 `supabase/schema.sql`로 먼저 제출용 테이블·버킷·권한을 구성하세요. 기존 IMEL 구조에 결과 컬럼만 추가할 때는 이 저장소의 `supabase/20261014235000_add_submission_results.sql`을 SQL Editor에서 실행합니다.

## 업데이트와 검증

```bash
git pull
python -m pip install --upgrade .
python -m unittest discover -s tests -v
```

검증은 메모리에서 모의 HTTP 응답을 사용하며 실제 Supabase 제출이나 결과를 변경하지 않습니다.
