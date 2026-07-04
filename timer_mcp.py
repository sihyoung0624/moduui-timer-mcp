"""
========================================================================
 모두의 타이머 MCP 서버  (timer_mcp.py)
========================================================================
"모두의 타이머"(https://shared-timer-d07t.onrender.com)를
Claude가 직접 "만들고 + 제어"할 수 있게 해주는 MCP 서버입니다.

------------------------------------------------------------------------
[동작 원리 — 한눈에]
  - 타이머 '생성'      : HTTP(POST /create)           ← httpx 사용
  - 타이머 '제어'      : socket.io(실시간 소켓)         ← python-socketio 사용
    (시작/정지/리셋/시간증감/문구/예약 전부 소켓)

  즉, 이 서버는 "HTTP 한 번 + 소켓 명령 여러 번"을 감싼 얇은 번역기입니다.

------------------------------------------------------------------------
[검증 완료 — 실제 서버에 붙여 눈으로 확인한 사실(FACT)]
  1) socket.io 서버 버전 = 4.5.4  → python-socketio 5.x 와 호환됨
  2) 접속 방식            = io() 기본 네임스페이스, websocket 전송으로 연결됨
  3) 방 입장             = emit('join', {room_id})
  4) 제어 신호           = emit('control', {room_id, token, action, ...추가값})
  5) 서버가 되쏘는 상태   = 'state' / 'tick' 이벤트
                          = {remaining, duration, status, viewers, message, start_at}
  6) adjust의 delta 단위  = '초'(+/- 모두 가능). delta=30 → 60초가 90초로 늘어남 확인
  7) 상태 읽기(remaining) = join만 하면 토큰 없이도 tick으로 받아짐 확인
  8) schedule_add 의 'at' = "남은 시간(초)" 정수. 실서버 실측으로 확정:
       at=60(정수)   → 등록됨 {'at': 60, 'text': ..., 'fired': False}
       at='30'(숫자 문자열) → 30으로 변환되어 등록됨
       at='15:00'(시:분 문자열) → 조용히 무시됨(등록 안 됨)
     유효 범위 1~86400(24시간). 남은 시간이 at초 이하가 되는 순간 문구가 자동 표시됨.
     ※ 이 도구의 정체는 '어젠다'가 아니라 "예약 메시지"(남은 시간 기준 자동 표출)임.

------------------------------------------------------------------------
[보안 핵심 — token 취급]
  - token 은 "제어 비밀번호"입니다. (room_id + token 을 아는 사람은 그 타이머를 조종 가능)
  - 그래서 이 코드에는 token 을 절대 하드코딩하지 않았고,
    각 도구를 호출할 때 '인자'로 받습니다. 로그로도 출력하지 않습니다.

------------------------------------------------------------------------
[설치 & 실행]
  # 파이썬 3.10 이상 필요
  pip install "mcp>=1.27,<2" httpx "python-socketio[client]>=5,<6"
  #  ※ mcp 는 v2 출시가 임박(2026-07-28경)해서 <2 로 버전을 고정합니다.
  python timer_mcp.py     # 로컬에서 stdio 방식으로 실행됨

[Claude Desktop 에 연결하는 설정 예시]
  (claude_desktop_config.json 의 "mcpServers" 안에 추가)
  {
    "mcpServers": {
      "moduui-timer": {
        "command": "python",
        "args": ["/절대경로/timer_mcp.py"],
        "env": { "TIMER_BASE_URL": "https://shared-timer-d07t.onrender.com" }
      }
    }
  }
========================================================================
"""

import os
import httpx
import socketio
from mcp.server.fastmcp import FastMCP

# ── 설정 ────────────────────────────────────────────────────────────
# 타이머 서버 주소. (비밀정보가 아니라서 기본값을 두되, 환경변수로 교체 가능)
BASE_URL = os.environ.get("TIMER_BASE_URL", "https://shared-timer-d07t.onrender.com")

# MCP 서버 객체 생성. 괄호 안 이름은 Claude에게 보이는 서버 이름.
mcp = FastMCP("모두의 타이머")


# ── 내부 헬퍼: 소켓으로 제어 명령 1건 보내고 최신 상태 받아오기 ────────
def _send_control(room_id: str, token: str, action: str, **extra) -> dict:
    """
    소켓에 '잠깐' 붙어서 control 명령 하나를 보내고,
    서버가 되쏘는 최신 상태(state/tick)를 받아 돌려준다.
    (명령 1건마다 붙었다 끊는 단발성 연결 — 제어용으로는 이 방식이 간단하고 안전)
    """
    result = {"ok": False, "action": action, "state": None, "error": None}
    latest = {}                       # 서버가 알려준 최신 상태를 담아둘 곳
    sio = socketio.Client()

    @sio.on("state")
    def _on_state(data):
        latest.update(data)

    @sio.on("tick")
    def _on_tick(data):
        latest.update(data)

    @sio.on("error_msg")
    def _on_error(data):
        # 토큰이 틀렸거나 방이 없으면 서버가 여기로 알려줌
        result["error"] = data

    try:
        sio.connect(BASE_URL, transports=["websocket"], wait_timeout=10)
        sio.emit("join", {"room_id": room_id})           # 먼저 방에 들어가고
        payload = {"room_id": room_id, "token": token, "action": action}
        payload.update(extra)                            # adjust의 delta 등 추가값 합치기
        sio.emit("control", payload)                     # 제어 명령 전송
        sio.sleep(1.5)                                   # 상태 되쏠 시간을 잠깐 기다림
        result["ok"] = result["error"] is None
        result["state"] = latest or None
    except Exception as e:
        result["error"] = f"연결/전송 실패: {e}"
    finally:
        try:
            sio.disconnect()
        except Exception:
            pass
    return result


# ════════════════════════════════════════════════════════════════════
#  도구(Tools) — Claude가 부를 수 있는 기능들
# ════════════════════════════════════════════════════════════════════

@mcp.tool()
def create_timer(minutes: int, seconds: int = 0, usage: str = "") -> dict:
    """새 타이머를 만든다.

    minutes: 분
    seconds: 초 (기본 0)
    usage:   용도 메모 (예: '발표', '회의') — 타이머 화면에 표시됨

    반환: room_id, token, 컨트롤러/뷰어 링크.
          (token 은 제어 비밀번호이므로 공유에 주의)
    """
    resp = httpx.post(
        f"{BASE_URL}/create",
        json={"minutes": minutes, "seconds": seconds, "usage": usage},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()

    # control_url 은 "/c/{room_id}/{token}" 형태 → token 부분만 따로 뽑아둔다
    control_url = data.get("control_url", "")
    parts = control_url.strip("/").split("/")   # 예: ["c", "roomid", "token문자열"]
    token = parts[2] if len(parts) >= 3 else ""

    return {
        "room_id": data.get("room_id"),
        "token": token,
        "control_url": f"{BASE_URL}{control_url}",
        "viewer_url": f"{BASE_URL}{data.get('viewer_url', '')}",
        "viewer_lan_url": data.get("viewer_lan_url"),
        "안내": "제어하려면 room_id 와 token 이 필요합니다. token 은 비밀이니 공유 주의.",
    }


@mcp.tool()
def get_timer_state(room_id: str) -> dict:
    """현재 타이머 상태(남은 시간/상태/시청자 수)를 읽는다.
    읽기 전용이라 token 이 필요 없다."""
    latest = {}
    sio = socketio.Client()

    @sio.on("state")
    def _s(data):
        latest.update(data)

    @sio.on("tick")
    def _t(data):
        latest.update(data)

    try:
        sio.connect(BASE_URL, transports=["websocket"], wait_timeout=10)
        sio.emit("join", {"room_id": room_id})
        sio.sleep(1.5)
    except Exception as e:
        return {"error": f"연결 실패: {e}"}
    finally:
        try:
            sio.disconnect()
        except Exception:
            pass

    return latest or {"error": "상태를 받지 못했습니다. room_id 를 확인하세요."}


@mcp.tool()
def start_timer(room_id: str, token: str) -> dict:
    """타이머를 시작한다."""
    return _send_control(room_id, token, "start")


@mcp.tool()
def pause_timer(room_id: str, token: str) -> dict:
    """타이머를 일시정지한다."""
    return _send_control(room_id, token, "pause")


@mcp.tool()
def reset_timer(room_id: str, token: str) -> dict:
    """타이머를 처음 설정 시간으로 되돌린다."""
    return _send_control(room_id, token, "reset")


@mcp.tool()
def adjust_timer(room_id: str, token: str, delta_seconds: int) -> dict:
    """남은 시간을 '초' 단위로 늘리거나 줄인다.
    예) delta_seconds=30 → +30초,  delta_seconds=-10 → -10초"""
    return _send_control(room_id, token, "adjust", delta=delta_seconds)


@mcp.tool()
def show_message(room_id: str, token: str, text: str) -> dict:
    """타이머 화면에 문구를 띄운다. (예: '곧 시작합니다')"""
    return _send_control(room_id, token, "message", text=text)


@mcp.tool()
def clear_message(room_id: str, token: str) -> dict:
    """화면에 띄운 문구를 지운다."""
    return _send_control(room_id, token, "clear_message")


@mcp.tool()
def schedule_start(room_id: str, token: str, start_at_ms: int) -> dict:
    """지정한 시각에 타이머가 '자동 시작'되도록 예약한다.
    start_at_ms: 시작할 시각을 '에폭 밀리초(1970년 기준 밀리초)'로 지정."""
    return _send_control(room_id, token, "schedule_start", start_at_ms=start_at_ms)


@mcp.tool()
def cancel_scheduled_start(room_id: str, token: str) -> dict:
    """예약해 둔 자동 시작을 취소한다."""
    return _send_control(room_id, token, "cancel_start")


@mcp.tool()
def schedule_add(room_id: str, token: str, at_seconds_remaining: int, text: str) -> dict:
    """예약 메시지를 추가한다 — 타이머의 '남은 시간'이 지정한 초 이하가 되는 순간
    화면에 문구가 자동 표시된다. (예: at_seconds_remaining=60 → 1분 남았을 때 표시)

    at_seconds_remaining: 남은 시간(초). 정수, 1~86400.
                          ※ 시각('15:00')이나 밀리초가 아님 — 실서버 실측으로 확정.
    text: 표시할 문구 (200자 제한)
    """
    return _send_control(room_id, token, "schedule_add",
                         at=at_seconds_remaining, text=text)


@mcp.tool()
def schedule_remove(room_id: str, token: str, index: int) -> dict:
    """추가한 일정 항목을 순번(index)으로 제거한다. (첫 항목이 0)"""
    return _send_control(room_id, token, "schedule_remove", index=index)


# ── 실행 진입점 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    # 기본 stdio 방식으로 실행 (Claude Desktop / Claude Code 가 로컬에서 이 방식으로 붙음)
    mcp.run()
