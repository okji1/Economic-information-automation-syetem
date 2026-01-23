import os
import datetime
from datetime import timedelta
import requests
import whisper
import torch

# ==========================================
# 🔐 [보안 설정] GitHub Secrets에서 가져옴
# ==========================================
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ⚠️ GitHub Actions는 CPU만 제공하므로 강제로 CPU 모드 사용
device = "cpu"
print(f"🚀 시스템 가동: {device} 모드로 실행 중 (GitHub Actions 환경)")

# ==========================================
# 🗓️ [날짜 자동 탐색]
# ==========================================
target_date = datetime.date.today()
found_url = None
found_filename = None
file_date_label = None
max_search_days = 7

# 한국 시간(KST) 보정을 위해 서버시간(UTC)에 9시간 더하기 (선택 사항, 날짜 계산 정확도를 위해)
target_date = target_date + timedelta(hours=9) 

print(f"🔍 최신 에피소드 탐색 시작 (기준: {target_date.strftime('%Y%m%d')})")

def send_telegram(message):
    send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    if len(message) > 4000:
        for x in range(0, len(message), 4000):
            requests.post(send_url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': message[x:x+4000]})
    else:
        requests.post(send_url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': message})

for i in range(max_search_days):
    check_date = target_date - timedelta(days=i)
    date_str = check_date.strftime("%Y%m%d")
    
    temp_filename = f"ECONOMY_{date_str}.mp3"
    temp_url = f"https://podcastfiledown.imbc.com/originaldata/economy/{temp_filename}"
    
    try:
        check_res = requests.head(temp_url)
        if check_res.status_code == 200:
            print(f"✅ 발견! [{date_str}] 방송을 찾았습니다.")
            found_url = temp_url
            found_filename = temp_filename
            file_date_label = date_str
            break 
        else:
            print(f"   PASS: {date_str} 파일 없음")
    except Exception:
        continue

if not found_url:
    err_msg = "❌ 최근 7일간 업로드된 방송 파일이 없습니다."
    print(err_msg)
    # send_telegram(err_msg) # 너무 자주 실패 알림이 오면 주석 처리
    raise Exception(err_msg)

url = found_url
filename = found_filename
save_path = filename # 현재 폴더에 저장

# ==========================================
# Gemini 요약 함수
# ==========================================
def summarize_with_gemini(text):
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    다음은 경제 뉴스 팟캐스트 내용입니다. 
    투자자 관점에서 핵심 정보를 '두괄식'으로 요약해주세요.
    가독성을 위해 이모지를 사용하고, 대주제와 소주제로 구조화해주세요.
    md형식은 빼줘.
    
    [텍스트 내용]:
    {text[:30000]} 
    """ 
    
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    res = requests.post(endpoint, headers={"Content-Type": "application/json"}, json=body)
    
    if res.status_code != 200:
        raise Exception(f"Gemini API Error: {res.text}")
        
    return res.json()["candidates"][0]["content"]["parts"][0]["text"]

# ==========================================
# 메인 실행
# ==========================================
try:
    # 1. 다운로드
    print(f"📥 다운로드 시작: {filename}")
    response = requests.get(url)
    with open(save_path, "wb") as f:
        f.write(response.content)
    
    # 2. Whisper 변환 (CPU 최적화를 위해 'small' 모델 사용 권장)
    print("🎧 Whisper 음성 인식 시작 (CPU 모드, 'small' 모델)...")
    # medium은 CPU에서 너무 느리거나 메모리 초과될 수 있음 -> small로 변경
    model = whisper.load_model("small").to(device) 
    result = model.transcribe(save_path)
    raw_text = result["text"]
    print(f"✅ 변환 완료 (글자수: {len(raw_text)}자)")

    # 3. Gemini 요약
    print("🤖 Gemini에게 요약 요청 중...")
    summary = summarize_with_gemini(raw_text)

    # 4. 전송
    print("📩 텔레그램 전송 중...")
    header = f"📅 [경제뉴스 요약] {file_date_label}\n(GitHub Actions 자동발송)\n\n"
    final_message = header + summary
    
    send_telegram(final_message)
    print(f"🚀 [성공] 작업 완료")

except Exception as e:
    print(f"❌ 에러 발생: {e}")
    send_telegram(f"⚠️ GitHub Actions 에러:\n{e}")
    raise e
