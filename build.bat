@echo off
rem Local Windows build: produces dist\iOSPair.exe (and dist\iOSPair-Setup.exe if Inno Setup is installed)
py -3.12 -m venv .venv || python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt pyinstaller==6.22.2
pyinstaller --onefile --windowed --noconfirm --name iOSPair --icon assets\icon.ico --paths . ^
  --exclude-module IPython --exclude-module jedi --exclude-module parso --exclude-module fastapi ^
  --exclude-module uvicorn --exclude-module starlette --exclude-module pydantic ^
  --exclude-module matplotlib --exclude-module numpy run.py
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer.iss
