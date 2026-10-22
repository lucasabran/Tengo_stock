@echo off
rem Mantenimiento nocturno de Tengo Stock: garantias (precios/stock) y productos sin stock.
cd /d "%~dp0"
echo ==== %date% %time% ==== >> mantenimiento.log
C:\Python314\python.exe -u garantia.py --categoria 30783413 30783491 30783650 30783583 34076862 35241954 --aplicar >> mantenimiento.log 2>&1
C:\Python314\python.exe -u mejoras.py stock --aplicar >> mantenimiento.log 2>&1
echo ==== fin %date% %time% ==== >> mantenimiento.log
