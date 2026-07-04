# 모두의 타이머 MCP

[모두의 타이머](https://shared-timer-d07t.onrender.com)를 **Claude가 직접 만들고 제어**할 수 있게 해주는 MCP 서버입니다.

Claude에게 이렇게 말하면 됩니다:
- "발표용 5분 타이머 만들어줘" → 뷰어 링크가 생김
- "타이머 시작해줘" / "1분 더 추가해줘" / "화면에 '곧 시작합니다' 띄워줘"
- "점심 메뉴 투표 열어줘. 짜장 vs 짬뽕" / "지금 몇 표야?" / "결과 공개해줘"
- "선착순 손들기 열어줘" / "퀴즈 내줘. 정답은 2번"

---

## 무엇을 할 수 있나 (도구 18개)

**타이머 (12개)**

| 도구 | 설명 |
|---|---|
| `create_timer` | 새 타이머 생성 (뷰어·컨트롤러 링크 발급) |
| `get_timer_state` | 남은 시간·상태 읽기 (토큰 불필요) |
| `start_timer` / `pause_timer` / `reset_timer` | 시작 / 일시정지 / 리셋 |
| `adjust_timer` | 남은 시간 ± 초 단위 조절 |
| `show_message` / `clear_message` | 화면에 문구 표시 / 지우기 |
| `schedule_start` / `cancel_scheduled_start` | 지정 시각 자동 시작 예약 / 취소 |
| `schedule_add` / `schedule_remove` | 예약 메시지 추가 / 제거 — 남은 시간이 N초가 되면 문구 자동 표시 |

**투표·선착순 (6개)** — 뷰어들이 폰으로 참여, 진행자가 집계를 봄

| 도구 | 설명 |
|---|---|
| `open_poll` | 선택 투표 열기 (질문 + 선택지 2~4개, 실시간 집계) |
| `open_race` | 선착순 손들기 열기 (누른 순서대로 1~10등 명단) |
| `open_quiz` | 선착순 퀴즈 열기 (정답을 빨리 누른 순서로 순위, 정답은 공개 전 은닉) |
| `get_poll_results` | 실시간 집계·순위 읽기 (진행자용) |
| `reveal_poll_results` | 뷰어에게 결과 공개/비공개 전환 (토글) |
| `close_poll` | 종료하고 결과 고정 |

---

## 동작 원리 (한눈에)

- **타이머 생성**은 HTTP(`POST /create`)로 합니다.
- **타이머 제어**(시작·정지·리셋 등)는 실시간 소켓(socket.io)으로 합니다.

즉, 이미 있는 "모두의 타이머" 서버에 붙어서 명령을 전달하는 **얇은 번역기**입니다. 별도 서버 배포가 필요 없고, 각자 자기 PC에서 실행합니다.

---

## 설치

```bash
# 파이썬 3.10 이상 필요
pip install -r requirements.txt
```

## Claude Desktop 에 연결하기

`claude_desktop_config.json` 파일의 `mcpServers` 안에 아래를 추가하세요.
(`/절대경로/` 부분은 이 파일이 있는 실제 경로로 바꾸세요.)

```json
{
  "mcpServers": {
    "moduui-timer": {
      "command": "python",
      "args": ["/절대경로/timer_mcp.py"],
      "env": { "TIMER_BASE_URL": "https://shared-timer-d07t.onrender.com" }
    }
  }
}
```

설정 후 Claude Desktop 을 다시 시작하고 이렇게 말해보세요:
> "발표용 3분 타이머 만들어줘"

---

## ⚠️ 알아두어야 할 점

- **token 은 '제어 비밀번호'입니다.** 타이머를 만들면 `room_id` 와 `token` 이 나오는데, 이 둘을 아는 사람은 그 타이머를 조종할 수 있습니다. **남에게는 뷰어 링크(`viewer_url`)만** 주고, 컨트롤러 링크(토큰 포함)는 본인만 가지세요.
- **이 MCP 는 기본적으로 위 render 서버에 붙습니다.** 자기만의 서버를 따로 운영한다면 `TIMER_BASE_URL` 환경변수를 그 주소로 바꾸면 됩니다.
- **`schedule_add` 의 시간 형식** — "남은 시간(초)" **정수**입니다(실서버 실측으로 확정). 예: `60` = 남은 시간이 1분이 되는 순간 문구가 표시됩니다. 시각 문자열(`"15:00"`)은 서버가 무시합니다. 특정 시각에 시작하려면 `schedule_start`(에폭 밀리초)를 쓰세요.
- **무료 호스팅 특성** — 타이머 서버는 render 무료 플랜이라 15분간 미사용 시 잠들며, 첫 요청이 50초쯤 걸릴 수 있습니다. 도구 호출이 timeout 나면 한 번 더 시도하세요.

---

## 라이선스

MIT License — 자유롭게 쓰고 고치고 공유할 수 있습니다. (`LICENSE` 파일 참고)
