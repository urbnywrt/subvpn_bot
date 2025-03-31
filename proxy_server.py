from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
import uvicorn
import urllib.parse
import os

app = FastAPI()

# Словарь с URL-схемами для разных приложений
APP_URL_SCHEMES = {
    'ios': {
        'streisand': 'streisand://import/{url}#{name}',
        'karing': 'karing://install-config?url={url}&name={name}',
        'foxray': 'foxray://yiguo.dev/sub/add/?url={url}#{name}',
        'v2box': 'v2box://install-sub?url={url}&name={name}',
        'singbox': 'sing-box://import-remote-profile?url={url}#{name}',
        'happ': 'happ://add/{url}'
    },
    'android': {
        'nekoray': 'sn://subscription?url={url}&name={name}',
        'v2rayng': 'v2rayng://install-sub?url={url}&name={name}',
        'hiddify': 'hiddify://install-config/?url={url}'
    },
    'pc': {
        'clashx': 'clashx://install-config?url={url}',
        'clash': 'clash://install-config?url={url}',
        'hiddify': 'hiddify://install-config/?url={url}'
    }
}
@app.get("/redirect/{system}/{app}")
async def redirect_to_app(system: str, app: str, url: str, name: str = None):
    """Перенаправляет на URL-схему приложения."""
    if system not in APP_URL_SCHEMES or app not in APP_URL_SCHEMES[system]:
        raise HTTPException(status_code=404, detail="Invalid system or app")
    
    scheme = APP_URL_SCHEMES[system][app]
    
    # Используем стандартное форматирование для всех приложений
    app_url = scheme.format(url=url, name=name if name else "")
    
    # Создаем HTML-страницу с автоматическим перенаправлением
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Перенаправление...</title>
        <meta http-equiv="refresh" content="0;url={app_url}">
    </head>
    <body>
        <p>Перенаправление на приложение...</p>
        <p>Если перенаправление не произошло автоматически, <a href="{app_url}">нажмите здесь</a></p>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    port = int(os.environ.get("PROXY_PORT", "8443"))
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        ssl_keyfile="./privkey5.pem",
        ssl_certfile="./fullchain5.pem"
    ) 