@echo off
rem Double-click this file to start the PDF to Markdown web app.
echo Starting PDF to Markdown web app...
echo Open http://localhost:5001 in your browser. Press Ctrl+C here to stop.
start "" http://localhost:5001
python "%~dp0app.py"
pause
