# 쿠팡 잇템 유튜브 쇼츠 자동화 봇

`products.txt`에서 아직 안 올린 쿠팡 상품 1개를 골라 TTS 나레이션 + 이미지 슬라이드(첫 장면은 실제
상품 사진, 나머지는 AI 삽화) + 자막으로 30~45초 세로 영상을 만들어 유튜브에 **바로 공개(public) 업로드**합니다.
설명란 맨 위에 쿠팡 파트너스 수수료 고지와 상품 링크를 넣습니다.

**상품 추가**: `products.txt`에 한 줄 추가 — `상품명 | 쿠팡 파트너스 링크 | 이미지 주소(선택)`.
GitHub 웹/앱에서 파일 열고 ✏️ 편집 → 한 줄 붙여넣기 → Commit 하면 끝. 위에서부터 하루 1개씩 소진되고,
다 쓰면 봇은 업로드 없이 종료하니 주기적으로 채워주세요. 영상 제목엔 자동으로 `[광고]`가 붙습니다.
(쿠팡은 봇 접근을 403으로 막아 링크만으로 상품명·이미지를 자동으로 가져올 수는 없습니다.)

## 사용 영상 봇 (텔레그램 → 쇼츠)

휴대폰으로 찍은 쿠팡템 사용 영상(목소리 없음)을 텔레그램 봇에게 보내면, 장면을 골라 나레이션·자막을 입힌
미리보기를 보내줍니다. **[✅ 업로드]** 를 누르면 유튜브에 올라갑니다 (`usage_bot.py`, 15분마다 확인).

- 캡션에 `상품명 | 쿠팡 파트너스 링크`를 꼭 적어 보내세요.
- '파일'이 아니라 **일반 동영상**으로 보내야 20MB 안으로 압축됩니다 (텔레그램 봇 다운로드 한도).
- 15분마다 확인하므로 미리보기·업로드까지 각각 최대 15분 정도 걸릴 수 있습니다.

**설정**
1. 텔레그램에서 `@BotFather` → `/newbot` → 받은 토큰을 GitHub Secret `TELEGRAM_BOT_TOKEN`에 저장
2. 만든 봇에게 아무 메시지나 보내고 Actions → usage-video-bot → Run workflow 실행
   → 봇이 `내 chat id: 123...`로 답장하면 그 숫자를 Secret `TELEGRAM_OWNER_CHAT_ID`에 저장
   (이 id가 아닌 사람이 보낸 영상은 처리하지 않습니다)

## 로컬 실행

1. `pip install -r requirements.txt`
2. `.env.example`을 `.env`로 복사 후 값 채우기
3. `python main.py`

## 환경변수

| 이름 | 설명 |
|---|---|
| ANTHROPIC_API_KEY | Anthropic API 키 |
| GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET | Google Cloud Console에서 발급한 OAuth 클라이언트(데스크톱 앱) |
| YOUTUBE_REFRESH_TOKEN | `youtube.upload` 스코프로 1회 동의해서 받은 refresh token |
| YOUTUBE_CHANNEL_ID | 업로드 대상 채널 ID |
| TELEGRAM_CHANNEL_URL | 설명란에 넣을 텔레그램 채널 초대 링크 |
| HF_API_KEY | 선택 — 없거나 실패하면 무료 Pollinations 이미지로 대체 |
| TELEGRAM_BOT_TOKEN | 사용 영상 봇 전용 — @BotFather에서 발급 |
| TELEGRAM_OWNER_CHAT_ID | 사용 영상 봇 전용 — 영상을 보낼 본인 chat id |
| AZURE_SPEECH_KEY / AZURE_SPEECH_REGION | 선택 — Azure Speech(F0 무료) 키·지역. 없거나 실패하면 edge-tts로 같은 현수 목소리 |

## 사전 준비

1. Google Cloud Console에서 프로젝트 생성 → YouTube Data API v3 활성화
2. OAuth 동의 화면 설정(User Type: 외부) → 데이터 액세스에 스코프 `https://www.googleapis.com/auth/youtube.upload` 추가 →
   잠재고객 탭에서 게시 상태를 "테스트"로 유지하고 본인 계정을 테스트 사용자로 등록
3. 사용자 인증 정보에서 OAuth 클라이언트 ID(데스크톱 앱) 생성 → `client_id`/`client_secret` 저장
4. 로컬에서 1회 OAuth 동의 플로우를 실행해 `YOUTUBE_REFRESH_TOKEN` 발급
5. 업로드 대상 채널의 `channel_id` 확인 (youtube.com/account_advanced)
6. 텔레그램 채널 초대 링크 준비

## 주의사항

- **완전 자동 공개**: draft 없이 바로 `public`으로 업로드됩니다. 오탈자/저품질 영상이 그대로 노출될 수 있음을
  감수하는 구조입니다.
- **edge-tts는 비공식 라이브러리**: 마이크로소프트가 예고 없이 막을 수 있습니다. 막히면 `tts.py`의 TTS 엔진을
  교체해야 합니다.
- ffmpeg는 워크플로에서 `apt-get install`로 직접 설치합니다(`ubuntu-latest`에 기본 설치되어 있지 않음 —
  실제로 겪은 문제). 로컬 실행 시에도 직접 설치 필요합니다. 한글 자막 렌더링을 위해 `fonts-nanum`(또는
  Hangul 지원 폰트)도 로컬에 설치되어 있어야 합니다(워크플로에는 이미 설치 스텝이 포함되어 있음).

## 테스트

`python -m pytest -v`
