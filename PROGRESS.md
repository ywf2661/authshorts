# 진행상황 (2026-09-23 기준)

## 현재 상태: ❌ 업로드 실패 중 (YouTube 토큰 문제)

GitHub Actions 실행 시 매번 아래 에러로 중단됨:

```
RuntimeError: 토큰 갱신 실패 400: {"error": "invalid_grant", "error_description": "Bad Request"}
```

- `invalid_grant` = client ID/secret은 정상, **refresh token이 무효**
  (다른 클라이언트로 발급됐거나, 만료/취소됐거나, 값이 잘못 들어감)
- 배경: 업로드 채널을 다른 채널로 바꾸려고 토큰을 재발급하던 중 발생

## 완료한 작업

- [x] 설명란에 쿠팡 파트너스 수수료 고지 문구 자동 추가 (`description_builder.py`)
- [x] 업로드 시 AI 합성 콘텐츠 표시 `containsSyntheticMedia: True` (`youtube_api.py`)
- [x] 토큰 갱신 실패 시 구글 응답 사유 + 토큰 형태(길이, `1//` 시작 여부) 로그 출력
- [x] Secrets 값의 앞뒤 공백·줄바꿈·따옴표 자동 제거 (`config.py`)

## 다음에 할 일 (순서대로)

1. **로컬에서 토큰 검증** — `check_token.py`(아래)로 client ID / secret / refresh token 세 값이
   "성공"이 나오는지 확인. 로컬에서 실패하면 GitHub에서도 무조건 실패.
   - 실패 시: `get_token.py`를 **같은** client ID/secret으로 **한 번만** 실행해 새 토큰 발급
2. **GitHub Secrets 3개 동시 교체** — `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`
   - 반드시 Settings → Secrets and variables → Actions → **Repository secrets** 에 넣을 것
     (Environment secrets / Variables 탭 ❌, 다른 저장소 ❌)
3. **Actions → ai-shortsbot → Run workflow** 로 실행 (실패한 실행의 "Re-run"은 옛 커밋으로 돌아가니 ❌)
4. 또 실패하면 로그 마지막 줄 확인:
   - `'1//'로 시작=False` → 토큰 아닌 값이 들어감 (`None`, `ya29.` access token 등)
   - `True` + 길이 100자 안팎 → 무효 토큰. OAuth 동의 화면을 **프로덕션으로 게시** 후 재발급
     (테스트 상태면 토큰이 7일 후 만료됨)
5. `YOUTUBE_CHANNEL_ID`도 새 채널 ID(`UC...`, youtube.com/account_advanced)로 교체

### 로컬 검증 스크립트 (secret 포함 → 커밋 금지, 사용 후 삭제)

`get_token.py` (토큰 발급, `python -m pip install google-auth-oauthlib` 필요):

```python
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_config(
    {"installed": {
        "client_id": "여기에_GOOGLE_CLIENT_ID",
        "client_secret": "여기에_GOOGLE_CLIENT_SECRET",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }},
    scopes=["https://www.googleapis.com/auth/youtube.upload"],
)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
print("REFRESH TOKEN:", creds.refresh_token)
```

`check_token.py` (세 값 검증):

```python
import urllib.parse, urllib.request, urllib.error

data = urllib.parse.urlencode({
    "client_id": "여기에_GOOGLE_CLIENT_ID",
    "client_secret": "여기에_GOOGLE_CLIENT_SECRET",
    "refresh_token": "여기에_YOUTUBE_REFRESH_TOKEN",
    "grant_type": "refresh_token",
}).encode()
try:
    urllib.request.urlopen("https://oauth2.googleapis.com/token", data)
    print("성공")
except urllib.error.HTTPError as e:
    print(e.read().decode())
```

## 별도 이슈

- **Hugging Face 월 무료 크레딧 소진 (402)** — 이미지 생성이 건너뛰어지고 단색 배경으로 대체됨(봇은 안 멈춤).
  다음 달 초기화 대기 / PRO 구독(월 약 $9) / 선불 크레딧 중 선택.

## 수익화 TODO

- [ ] 채널 프로필 링크에 텔레그램·쿠팡 링크 추가 (쇼츠 설명란 링크는 클릭 안 됨) + 채널 설명에 쿠팡 고지 문구
- [ ] 상품 매칭을 영상 주제와 직접 관련된 것만으로 좁히기
- [ ] 반복 콘텐츠(inauthentic content) YPP 거절 대비: 사람의 코멘트/템플릿 다양화
- [ ] 구독자 1,000명 이후 YPP + YouTube 쇼핑 제휴 신청
