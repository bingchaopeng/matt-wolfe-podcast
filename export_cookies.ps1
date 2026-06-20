# Export Chrome YouTube cookies to Netscape format for yt-dlp
# Uses .NET DPAPI + AESGcm for Chrome v20 cookie decryption

Add-Type -AssemblyName System.Security.Cryptography

# Kill Chrome to unlock cookie DB
Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

$localAppData = [Environment]::GetFolderPath('LocalApplicationData')
$userProfile = [Environment]::GetFolderPath('UserProfile')

$cookieDb = Join-Path $localAppData "Google\Chrome\User Data\Default\Network\Cookies"
$localState = Join-Path $localAppData "Google\Chrome\User Data\Local State"

if (-not (Test-Path $cookieDb)) {
    Write-Host "ERROR: Chrome cookies DB not found at $cookieDb"
    exit 1
}

# Read Local State and decrypt key
$ls = Get-Content $localState -Raw | ConvertFrom-Json
$encKeyB64 = $ls.os_crypt.encrypted_key
$encKeyAll = [Convert]::FromBase64String($encKeyB64)
$encKeyOnly = $encKeyAll[5..($encKeyAll.Length-1)]  # Remove 'DPAPI' prefix

try {
    $key = [System.Security.Cryptography.ProtectedData]::Unprotect(
        $encKeyOnly, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
} catch {
    Write-Host "ERROR: Failed to decrypt Chrome key: $_"
    exit 1
}

Write-Host "Chrome encryption key decrypted: $($key.Length) bytes"

# Copy cookie database (Chrome is now closed)
$tmpDb = [System.IO.Path]::GetTempFileName() + ".db"
Copy-Item $cookieDb $tmpDb -Force

# Read cookies using ADO.NET (System.Data).
# SQLite might not be available, so parse the SQLite DB via yt-dlp's method
# Instead, we use a simple approach: run yt-dlp with cookies-from-browser directly
# after Chrome is killed. The key is available in the session now.

# Actually, just try yt-dlp now that Chrome is closed and key is available
Write-Host "Chrome closed. Trying yt-dlp --cookies-from-browser chrome..."

$result = & python -m yt_dlp --cookies-from-browser chrome --cookies "$userProfile\matt-wolfe-podcast\cookies.txt" --skip-download --print filename "https://www.youtube.com/watch?v=Db260rUuKJg" 2>&1
Write-Host $result

if ($LASTEXITCODE -eq 0) {
    Write-Host "SUCCESS: YouTube cookies exported!"
    exit 0
} else {
    Write-Host "yt-dlp still failed. Trying manual decryption..."

    # Read cookies from the copied database
    $conn = New-Object System.Data.OleDb.OleDbConnection
    # We need SQLite ADO.NET provider - check if available
    $assemblies = [AppDomain]::CurrentDomain.GetAssemblies() | Where-Object { $_.FullName -like "*SQLite*" }
    if (-not $assemblies) {
        # Try with Microsoft.Data.Sqlite or System.Data.SQLite
        try {
            Add-Type -Path "$userProfile\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\System.Data.SQLite.dll" -ErrorAction Stop
        } catch {
            Write-Host "No SQLite ADO.NET provider available. Using Python instead."
            # Fallback: use Python to read and decrypt
            $pyScript = @'
import os, sqlite3, shutil, tempfile, json, base64
from win32crypt import CryptUnprotectData
from Cryptodome.Cipher import AES

ls_path = os.path.expanduser('~/AppData/Local/Google/Chrome/User Data/Local State')
with open(ls_path) as f:
    ls = json.load(f)
enc_key = base64.b64decode(ls['os_crypt']['encrypted_key'])[5:]
_, key = CryptUnprotectData(enc_key, None, None, None, 0)

# Copy DB
src = os.path.expanduser('~/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies')
# Try multiple times in case Chrome hasn't fully released the lock
for attempt in range(10):
    try:
        tmp = tempfile.mktemp(suffix='.db')
        shutil.copy2(src, tmp)
        break
    except PermissionError:
        if attempt < 9:
            import time; time.sleep(1)
        else:
            raise

conn = sqlite3.connect(tmp)
cursor = conn.cursor()
cursor.execute('SELECT host_key, name, encrypted_value, path, expires_utc, is_secure, is_httponly FROM cookies WHERE host_key LIKE "%.youtube.com"')
rows = cursor.fetchall()
conn.close()
os.unlink(tmp)

lines = ['# Netscape HTTP Cookie File']
count = 0
for host_key, name, enc_val, path, expires_utc, is_secure, is_httponly in rows:
    if not enc_val or len(enc_val) < 3:
        continue
    try:
        nonce = enc_val[3:15]
        ct = enc_val[15:-16]
        tag = enc_val[-16:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        value = cipher.decrypt_and_verify(ct, tag).decode('utf-8')
    except Exception:
        continue

    domain_flag = 'TRUE' if host_key.startswith('.') else 'FALSE'
    secure_flag = 'TRUE' if is_secure else 'FALSE'
    httponly_flag = '#HttpOnly_' if is_httponly else ''
    if expires_utc and expires_utc > 0:
        expires_unix = int((expires_utc / 1000000) - 11644473600)
        if expires_unix < 0: expires_unix = 0
    else:
        expires_unix = 0
    lines.append(f'{httponly_flag}{host_key}\t{domain_flag}\t{path or "/"}\t{secure_flag}\t{expires_unix}\t{name}\t{value}')
    count += 1

out = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cookies.txt')
# Hardcode path
out = os.path.expanduser('~/matt-wolfe-podcast/cookies.txt')
with open(out, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')
print(f'Exported {count} cookies to {out}')
'@
            python -c $pyScript
        }
    }
}
