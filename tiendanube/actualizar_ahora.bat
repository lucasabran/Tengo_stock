@echo off
rem Recalcula la garantia de los productos modificados en las ultimas 24 horas (tarda segundos).
cd /d "%~dp0"
C:\Python314\python.exe garantia.py --recientes 24 --aplicar
pause
