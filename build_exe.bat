@echo off
setlocal EnableExtensions

for %%I in ("%~dp0.") do set "ROOT_DIR=%%~fI"
pushd "%ROOT_DIR%" >nul

python -m PyInstaller --noconfirm --clean --distpath "%ROOT_DIR%" --workpath "%ROOT_DIR%\build\pyinstaller" "%ROOT_DIR%\yourshiguan_register.spec"
if errorlevel 1 goto :fail

set "EXIT_CODE=0"
goto :done

:fail
set "EXIT_CODE=%ERRORLEVEL%"

:done
popd >nul
exit /b %EXIT_CODE%
