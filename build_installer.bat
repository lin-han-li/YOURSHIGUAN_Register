@echo off
setlocal EnableExtensions

for %%I in ("%~dp0.") do set "ROOT_DIR=%%~fI"
set "ISCC_PATH="

for %%P in (
    "D:\Inno Setup 6\ISCC.exe"
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
) do (
    if not defined ISCC_PATH if exist %%~P set "ISCC_PATH=%%~P"
)

if not defined ISCC_PATH (
    echo [ERROR] ISCC.exe not found.
    exit /b 1
)

if not exist "%ROOT_DIR%\YOURSHIGUAN_Register.exe" (
    echo [ERROR] YOURSHIGUAN_Register.exe not found. Build exe first.
    exit /b 1
)

pushd "%ROOT_DIR%" >nul
"%ISCC_PATH%" "%ROOT_DIR%\yourshiguan_register_installer.iss"
if errorlevel 1 goto :fail

set "EXIT_CODE=0"
goto :done

:fail
set "EXIT_CODE=%ERRORLEVEL%"

:done
popd >nul
exit /b %EXIT_CODE%
