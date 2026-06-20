# PowerShell script to refresh Chrome YouTube cookies
# Runs with current user privileges - no admin needed

$cookiePath = "$env:USERPROFILE\matt-wolfe-podcast\cookies.txt"
$python = "C:\Users\30777\AppData\Local\Python\pythoncore-3.14-64\python.exe"

# Method 1: Launch Chrome with remote debugging port using the default profile
# We use a different user-data-dir but copy key files from the default profile
Write-Host "Starting Chrome headless for cookie extraction..."

$port = 9222
$tempDir = [System.IO.Path]::GetTempPath() + [System.Guid]::NewGuid().ToString()
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

try {
    # Start Chrome headless with a fresh profile
    $proc = Start-Process -FilePath "C:\Program Files\Google\Chrome\Application\chrome.exe" `
        -ArgumentList "--headless=new","--remote-debugging-port=$port","--remote-allow-origins=*","--no-first-run","--no-default-browser-check","--user-data-dir=$tempDir","https://www.youtube.com" `
        -PassThru -WindowStyle Hidden

    Start-Sleep -Seconds 4

    # Use Python script to extract cookies via CDP
    $pythonScript = @"
import urllib.request, json, websocket, time, sys

port = $port
try:
    resp = urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=5)
    data = json.loads(resp.read())
    ws_url = data['webSocketDebuggerUrl']

    ws = websocket.create_connection(ws_url, timeout=10)
    msg_id = 1
    def send(method, params=None):
        global msg_id
        mid = msg_id
        msg_id += 1
        msg = {'id': mid, 'method': method}
        if params: msg['params'] = params
        ws.send(json.dumps(msg))
        while True:
            r = json.loads(ws.recv())
            if r.get('id') == mid: return r.get('result', {})

    # Navigate to YouTube first to ensure cookies are loaded
    send('Page.navigate', {'url': 'https://www.youtube.com'})
    time.sleep(3)

    result = send('Network.getCookies', {'urls': ['https://www.youtube.com']})
    ws.close()
    cookies = result.get('cookies', [])
    yt_cookies = [c for c in cookies if 'youtube' in c.get('domain','')]

    if not yt_cookies:
        print('NO_COOKIES')
        sys.exit(1)

    lines = ['# Netscape HTTP Cookie File']
    for c in yt_cookies:
        domain = c.get('domain', '.youtube.com')
        if not domain.startswith('.'): domain = '.' + domain
        path = c.get('path', '/')
        secure = 'TRUE' if c.get('secure', False) else 'FALSE'
        expires = str(int(c.get('expires', 0))) if c.get('expires') else '0'
        name = c.get('name', '')
        value = c.get('value', '')
        lines.append(f'{domain}\tTRUE\t{path}\t{secure}\t{expires}\t{name}\t{value}')

    with open(r'$cookiePath', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'OK:{len(yt_cookies)}')

except Exception as e:
    print(f'ERROR:{e}')
    sys.exit(1)
"@

    $result = & $python -c $pythonScript 2>&1
    Write-Host "Result: $result"

    if ($result -like "OK:*") {
        Write-Host "Cookies exported successfully!"
    } else {
        Write-Host "CDP failed, trying browser-cookie3..."
        & $python -c "import browser_cookie3, os; cj=browser_cookie3.chrome(domain_name='youtube.com'); c=list(cj); open(r'$cookiePath','w').write('# Netscape HTTP Cookie File\n'+'\n'.join([f'.youtube.com\tTRUE\t{c.path}\t{\"TRUE\" if c.secure else \"FALSE\"}\t{str(int(c.expires)) if c.expires else \"0\"}\t{c.name}\t{c.value}' for c in c])+'\n'); print(f'OK:{len(c)}')" 2>&1
    }

} finally {
    # Cleanup
    if ($proc -and !$proc.HasExited) { $proc.Kill() | Out-Null }
    Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue | Out-Null
}

# Check result
if (Test-Path $cookiePath) {
    $size = (Get-Item $cookiePath).Length
    Write-Host "Cookies file: $cookiePath ($size bytes)"
} else {
    Write-Host "ERROR: No cookies file generated"
    exit 1
}
