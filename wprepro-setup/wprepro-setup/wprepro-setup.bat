@echo off
chcp 65001 >nul
cls

:: ============================================================
::  WPRecover 2.0 — Setup Plugin + Backend Integration
::  Ejecutar desde: C:\Users\rcaceres\Desktop\WPRecover
:: ============================================================

set PROJECT=C:\Users\rcaceres\Desktop\WPRecover
set SETUP_DIR=%~dp0
set SITE_URL=https://espaciosunicos.cl
set API_KEY=wprepro-espaciosunicos-2024-x9k2m7p
set BACKEND_URL=http://localhost:8000

echo.
echo ================================================
echo   WPRecover 2.0 - Setup Automatizado
echo ================================================
echo   Proyecto : %PROJECT%
echo   Sitio    : %SITE_URL%
echo   Backend  : %BACKEND_URL%
echo ================================================
echo.
pause

:: ============================================================
:: PASO 1 - Verificar plugin WordPress
:: ============================================================
echo.
echo [1/5] Verificando WPRepro Agent en %SITE_URL%...
echo.

curl -s -w "\nHTTP Status: %%{http_code}\n" ^
     -H "X-WPRepro-Key: %API_KEY%" ^
     %SITE_URL%/wp-json/wprepro/v1/status

echo.
echo Si ves "success: true" continua. Si ves 403/404:
echo   - Verifica que el plugin esta activado en WordPress
echo   - Verifica que WPREPRO_API_KEY esta en wp-config.php
echo.
pause

:: ============================================================
:: PASO 2 - Copiar archivos Python al proyecto
:: ============================================================
echo.
echo [2/5] Copiando archivos Python al proyecto...
echo.

:: Crear carpetas si no existen
if not exist "%PROJECT%\api" mkdir "%PROJECT%\api"
if not exist "%PROJECT%\api\routers" mkdir "%PROJECT%\api\routers"

:: Copiar archivos desde la carpeta del setup
copy /Y "%SETUP_DIR%api\wp_agent_client.py" "%PROJECT%\api\wp_agent_client.py"
copy /Y "%SETUP_DIR%api\routers\fix_router.py" "%PROJECT%\api\routers\fix_router.py"

echo.
if exist "%PROJECT%\api\wp_agent_client.py" (
    echo [OK] wp_agent_client.py copiado
) else (
    echo [ERROR] No se pudo copiar wp_agent_client.py
)

if exist "%PROJECT%\api\routers\fix_router.py" (
    echo [OK] fix_router.py copiado
) else (
    echo [ERROR] No se pudo copiar fix_router.py
)
echo.
pause

:: ============================================================
:: PASO 3 - Instalar dependencia httpx
:: ============================================================
echo.
echo [3/5] Instalando httpx...
echo.

cd /d "%PROJECT%"
pip install httpx

echo.
:: Agregar httpx a requirements.txt si no esta
if exist "requirements.txt" (
    findstr /C:"httpx" requirements.txt >nul 2>&1
    if errorlevel 1 (
        echo httpx >> requirements.txt
        echo [OK] httpx agregado a requirements.txt
    ) else (
        echo [OK] httpx ya estaba en requirements.txt
    )
) else (
    echo httpx > requirements.txt
    echo [OK] requirements.txt creado con httpx
)
echo.
pause

:: ============================================================
:: PASO 4 - Probar fix/cache directo al sitio
:: ============================================================
echo.
echo [4/5] Probando fix/cache directo en %SITE_URL%...
echo.

curl -s -X POST ^
     -H "X-WPRepro-Key: %API_KEY%" ^
     -H "Content-Type: application/json" ^
     -w "\nHTTP Status: %%{http_code}\n" ^
     %SITE_URL%/wp-json/wprepro/v1/fix/cache

echo.
pause

:: ============================================================
:: PASO 5 - Probar flujo via backend FastAPI
:: ============================================================
echo.
echo [5/5] Probando flujo via FastAPI en %BACKEND_URL%...
echo      (El backend debe estar corriendo)
echo.

curl -s -X POST ^
     -H "Content-Type: application/json" ^
     -d "{\"site_url\":\"%SITE_URL%\",\"api_key\":\"%API_KEY%\"}" ^
     -w "\nHTTP Status: %%{http_code}\n" ^
     %BACKEND_URL%/api/fix/cache

echo.
echo.
echo ================================================
echo   Setup completado
echo ================================================
echo   Recuerda agregar en main.py:
echo.
echo   from api.routers.fix_router import router as fix_router
echo   app.include_router(fix_router)
echo ================================================
echo.
pause
