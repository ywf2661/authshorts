# 쿠팡 TOP3 유튜브 쇼츠 자동화 봇

`products.txt`에서 아직 안 올린 `[주제]` 묶음(상품 2~5개)을 골라 **3위 → 1위 공개형** 22~26초 세로 영상을 만들어
유튜브에 **바로 공개(public) 업로드**합니다. 대본은 Claude Sonnet 5가 상품 사진과 '포인트'만 근거로 쓰고,
1인칭 후기·근거 없는 주장·가격 언급은 코드가 검사해 걸러냅니다 (1회 재요청, 또 걸리면 그날은 건너뛰고 텔레그램 알림).
화면은 순위별 밝은 단색 배경 + 1:1 상품 사진(2초 이하 컷마다 확대·이동) + ASS 팝 자막, 소리는 나레이션 + BGM → -14 LUFS.

- **상품 추가**: `products.txt` 맨 위 안내대로 `[주제]` 줄과 `상품명 | 링크 | 이미지 주소들 | 포인트: ...` 줄을 추가.
- **실행 시각**: 평일 KST 19시, 주말 KST 11시. 하루 1편 상한. 남은 묶음이 2개 이하가 되면 텔레그램으로 알립니다.
- **설명란**: 쿠팡 파트너스 고지 → "왼쪽 아래 채널명 → 프로필 링크 #번호" → 순위별 상품명·링크 → 해시태그.
  업로드 시 '유료 광고 포함' 표시를 켜고, 실제 상품 사진만 쓰므로 '합성 콘텐츠' 표시는 끕니다.
- **프로필 링크 페이지**: 업로드 기록(`posted_videos.json`)으로 `site_page.py`가 영상별 상품 링크 페이지를 만들어
  GitHub Pages(`https://ywf2661.github.io/authshorts/`)에 배포합니다. 저장소 Settings → Pages → Source를
  "GitHub Actions"로 바꿔야 배포됩니다.
- **효과음(선택)**: `sfx/whoosh.mp3`(순위 전환), `sfx/ding.mp3`(1위 공개)를 넣으면 자동으로 씁니다. 없으면 생략.

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
| TELEGRAM_BOT_TOKEN | 사용 영상 봇 + TOP3 봇 알림 — @BotFather에서 발급 |
| TELEGRAM_OWNER_CHAT_ID | 사용 영상 봇 + TOP3 봇 알림 — 본인 chat id |
| AZURE_SPEECH_KEY / AZURE_SPEECH_REGION | 선택 — edge-tts가 막히면 Azure Speech(F0 무료)로 같은 현수 목소리 (자막 타이밍은 글자 수 비례) |

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
- ffmpeg(libass 포함)는 워크플로에서 `apt-get install`로 직접 설치합니다(`ubuntu-latest`에 기본 설치되어 있지 않음 —
  실제로 겪은 문제). 로컬 실행 시에도 직접 설치 필요합니다. 한글 폰트는 `fonts/`에 들어 있어 따로 설치할 필요 없습니다.

## 테스트

`python -m pytest -v`
