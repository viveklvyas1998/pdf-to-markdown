@echo off
rem Drag and drop one or more PDF files onto this .bat to convert them to Markdown.
rem The .md file is created next to each PDF.
if "%~1"=="" (
    echo Drag and drop PDF files onto this file to convert them to Markdown.
    pause
    exit /b
)
python "%~dp0pdf2md.py" %*
echo.
pause
