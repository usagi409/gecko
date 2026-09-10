@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
"%~dp0gecko.exe" %*
