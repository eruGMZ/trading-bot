"""
Actualiza ~/trading-bot/rsi_cache.json cada 60 segundos
leyendo el RSI estándar (14) desde TradingView vía CDP WebSocket.
Los precios de BTC usan coma de miles (75,596), el RSI usa punto decimal (29.86).
"""
import json
import time
import requests
import websocket
from config import CACHE_FILE, CDP_PORT, RSI_UPDATE_INTERVAL

JS_GET_RSI = r"""
(function(){
    var rows = document.querySelectorAll("[class*='valueItem'],[class*='value-']");
    var vals = [];
    rows.forEach(function(el){
        var t = el.textContent.trim();
        if(t) vals.push(t);
    });
    // RSI aparece como "29.86" (punto decimal, 1-2 dígitos antes del punto)
    // Precios BTC usan coma de miles: "75,596" — los excluimos así
    var dotNumRe = /^[0-9]{1,2}\.[0-9]+$/;
    var rsi = null;
    for(var i=0; i<vals.length; i++){
        if(!dotNumRe.test(vals[i])) continue;
        var n = parseFloat(vals[i]);
        if(n >= 1 && n <= 100){
            rsi = n;
            break;
        }
    }
    return JSON.stringify({rsi: rsi});
})()
"""


def get_chart_ws_url():
    pages = requests.get(f"http://localhost:{CDP_PORT}/json", timeout=3).json()
    page = next(
        (p for p in pages if "tradingview.com/chart" in p.get("url", "")),
        None,
    )
    return page.get("webSocketDebuggerUrl") if page else None


def eval_js(ws_url, expression):
    ws = websocket.create_connection(ws_url, timeout=5)
    ws.send(json.dumps({
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {"expression": expression, "returnByValue": True},
    }))
    result = None
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            ws.settimeout(2)
            msg = ws.recv()
            data = json.loads(msg)
            if data.get("id") == 1:
                result = data.get("result", {}).get("result", {}).get("value")
                break
        except Exception:
            break
    ws.close()
    return result


def fetch_rsi():
    try:
        ws_url = get_chart_ws_url()
        if not ws_url:
            print("[rsi_updater] TradingView no activo")
            return None
        raw = eval_js(ws_url, JS_GET_RSI)
        if not raw:
            return None
        data = json.loads(raw)
        rsi = data.get("rsi")
        return float(rsi) if rsi is not None else None
    except Exception as e:
        print(f"[rsi_updater] Error: {e}")
        return None


def save_cache(rsi):
    with open(CACHE_FILE, "w") as f:
        json.dump({"rsi": rsi, "timestamp": time.time()}, f)
    print(f"[rsi_updater] RSI → {rsi:.2f}")


def main():
    print(f"[rsi_updater] Iniciado — intervalo: {RSI_UPDATE_INTERVAL}s")
    while True:
        rsi = fetch_rsi()
        if rsi is not None:
            save_cache(rsi)
        else:
            print("[rsi_updater] RSI no disponible")
        time.sleep(RSI_UPDATE_INTERVAL)


if __name__ == "__main__":
    main()
