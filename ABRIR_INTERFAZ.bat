@echo off
rem Doble clic para abrir la interfaz de Girls in the Loop en el navegador.
cd /d "%~dp0"
python -m pip show streamlit >nul 2>&1 || python -m pip install --quiet streamlit plotly pandas matplotlib tabulate
python -m streamlit run app.py
pause
