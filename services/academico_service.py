import subprocess
import sys
import tempfile
import os
import json
import time
from typing import Dict


class AcademicoService:
    BASE_URL = "https://academico.unas.edu.pe"

    def __init__(self):
        self._cookies = None
        self._session_valid = False
        self._session_proc = None
        self._session_dir = None

    def start_login_session(self, username: str, password: str) -> Dict:
        """Lanza proceso Playwright que queda vivo. Devuelve imagen CAPTCHA."""
        import tempfile

        # Directorio de comunicación entre Flask y el proceso Playwright
        session_dir = tempfile.mkdtemp(prefix='unas_session_')
        self._session_dir = session_dir

        captcha_file = os.path.join(session_dir, 'captcha.png')
        result_file = os.path.join(session_dir, 'result.json')
        command_file = os.path.join(session_dir, 'command.json')
        ready_file = os.path.join(session_dir, 'ready.flag')

        script = f'''
import sys, json, time, os, base64

session_dir    = {repr(session_dir)}
captcha_file   = os.path.join(session_dir, "captcha.png")
result_file    = os.path.join(session_dir, "result.json")
command_file   = os.path.join(session_dir, "command.json")
ready_file     = os.path.join(session_dir, "ready.flag")

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={{"width": 1280, "height": 800}},
            locale="es-PE",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto({repr(self.BASE_URL + "/login")}, timeout=15000)
        page.wait_for_load_state("networkidle", timeout=10000)

        # Rellenar usuario y contraseña
        try: page.fill("#username", {repr(username)}, timeout=2000)
        except: pass
        try: page.fill("#userpasw", {repr(password)}, timeout=2000)
        except: pass

        # Capturar CAPTCHA
        try:
            el = page.query_selector("#capcode")
            if el:
                el.screenshot(path=captcha_file)
            else:
                page.screenshot(path=captcha_file)
        except:
            page.screenshot(path=captcha_file)

        # Señal: listo para recibir CAPTCHA
        open(ready_file, "w").close()

        # Esperar comando con solución del CAPTCHA (máx 3 min)
        deadline = time.time() + 180
        captcha_solution = None
        while time.time() < deadline:
            if os.path.exists(command_file):
                try:
                    with open(command_file) as f:
                        cmd = json.load(f)
                    captcha_solution = cmd.get("captcha")
                    break
                except: pass
            time.sleep(0.5)

        if not captcha_solution:
            with open(result_file, "w") as f:
                json.dump({{"success": False, "error": "Timeout esperando CAPTCHA"}}, f)
            context.close(); browser.close()
            sys.exit(0)

        # Setear CAPTCHA en ambos campos
        page.evaluate("""
            (val) => {{
                ["#captcha", "#usercaptcha"].forEach(sel => {{
                    const el = document.querySelector(sel);
                    if (el) {{
                        el.value = val;
                        el.dispatchEvent(new Event("input", {{bubbles:true}}));
                        el.dispatchEvent(new Event("change", {{bubbles:true}}));
                    }}
                }});
            }}
        """, captcha_solution)

        # Verificar valores y hacer click
        vals = page.evaluate("""
            () => ({{
                user: (document.querySelector("#username")||{{}}).value||"",
                pass_len: ((document.querySelector("#userpasw")||{{}}).value||"").length,
                captcha: (document.querySelector("#captcha")||{{}}).value||"",
                usercaptcha: (document.querySelector("#usercaptcha")||{{}}).value||"",
                usertoken: (document.querySelector("#usertoken")||{{}}).value||""
            }})
        """)

        try: page.click("button:has-text('Ingresar')", timeout=2000)
        except:
            try: page.click("button[type=submit]", timeout=2000)
            except: pass

        time.sleep(3)
        try: page.wait_for_load_state("networkidle", timeout=8000)
        except: pass

        page.screenshot(path=os.path.join(session_dir, "after_submit.png"))

        if "/login" not in page.url:
            cookies_list = context.cookies()
            cookies_str = "; ".join([f"{{c['name']}}={{c['value']}}" for c in cookies_list])
            unas_username = None
            for sel in [".navbar-user", ".user-name", ".profile-name", ".navbar-right .dropdown-toggle"]:
                try:
                    el = page.query_selector(sel)
                    if el:
                        txt = el.inner_text().strip()
                        if txt and len(txt) > 2:
                            unas_username = txt; break
                except: continue
            with open(result_file, "w") as f:
                json.dump({{"success": True, "cookies": cookies_str,
                            "username": unas_username or {repr(username)},
                            "debug_vals": vals, "debug_url": page.url}}, f)
        else:
            error_msg = "Login fallido"
            for sel in [".alert", ".alert-danger", "[class*=alert]"]:
                try:
                    el = page.query_selector(sel)
                    if el:
                        txt = el.inner_text().strip()
                        if txt: error_msg = txt[:300]; break
                except: continue
            with open(result_file, "w") as f:
                json.dump({{"success": False, "error": error_msg, "debug_vals": vals}}, f)

        context.close(); browser.close()

except Exception as e:
    import traceback
    with open(os.path.join(session_dir, "result.json"), "w") as f:
        json.dump({{"success": False, "error": str(e),
                    "traceback": traceback.format_exc()}}, f)
'''

        script_path = os.path.join(session_dir, 'pw_session.py')
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script)

        # Lanzar proceso en background (no bloqueante)
        self._session_proc = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        # Esperar a que Playwright esté listo (max 30s)
        deadline = time.time() + 30
        while time.time() < deadline:
            if os.path.exists(ready_file):
                break
            time.sleep(0.3)
        else:
            self._session_proc.terminate()
            return {"success": False, "error": "Timeout cargando la página de UNAS"}

        # Leer imagen del CAPTCHA
        if not os.path.exists(captcha_file):
            return {"success": False, "error": "No se generó imagen del CAPTCHA"}

        with open(captcha_file, 'rb') as f:
            captcha_b64 = __import__('base64').b64encode(f.read()).decode()

        return {"success": True, "captcha_image": captcha_b64}

    def complete_login_with_captcha(self, username: str, password: str, captcha_solution: str) -> Dict:
        """Envía la solución del CAPTCHA al proceso Playwright que sigue vivo."""
        if not self._session_dir:
            return {"success": False, "error": "No hay sesión activa. Inicia el proceso nuevamente."}

        command_file = os.path.join(self._session_dir, 'command.json')
        result_file = os.path.join(self._session_dir, 'result.json')

        # Enviar solución al proceso
        with open(command_file, 'w') as f:
            json.dump({"captcha": captcha_solution}, f)

        # Esperar resultado (max 30s)
        deadline = time.time() + 30
        while time.time() < deadline:
            if os.path.exists(result_file):
                try:
                    with open(result_file) as f:
                        result = json.load(f)
                    print(f"[ACADEMICO debug_vals]: {result.get('debug_vals')}")
                    print(f"[ACADEMICO debug_url]: {result.get('debug_url')}")
                    return result
                except:
                    pass
            time.sleep(0.4)

        # Timeout
        if self._session_proc:
            self._session_proc.terminate()
        return {"success": False, "error": "Timeout esperando resultado del login"}

    def set_cookies(self, cookies_str: str):
        self._cookies = cookies_str
        self._session_valid = True

    def verify_session(self) -> bool:
        return self._session_valid and bool(self._cookies)

    def get_pages(self) -> Dict:
        return {
            "notas": {"label": "Notas", "icon": "bi-journal-check", "description": "Calificaciones por período"},
            "horario": {"label": "Horario", "icon": "bi-calendar3", "description": "Horario de clases"},
            "matricula": {"label": "Matrícula", "icon": "bi-person-check", "description": "Estado de matrícula"},
            "pagos": {"label": "Pagos", "icon": "bi-credit-card", "description": "Estado de pagos"},
        }

    def _get_current_semester(self, cookies: str) -> str:
        """Obtiene el semestre activo del sistema."""
        import requests
        from bs4 import BeautifulSoup
        try:
            resp = requests.post(
                "https://academico.unas.edu.pe/",
                data={"load": "SemesterController@show"},
                headers={
                    "Cookie": cookies,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Mozilla/5.0",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://academico.unas.edu.pe/"
                },
                timeout=10
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            sem = soup.find(id="semactivo")
            return sem.text.strip() if sem else "2026-1"
        except:
            return "2026-1"

    def _scrape_section(self, controller: str, cookies: str, codsem: str = None) -> str:
        import requests
        from bs4 import BeautifulSoup

        if not codsem:
            codsem = self._get_current_semester(cookies)

        try:
            resp = requests.post(
                "https://academico.unas.edu.pe/",
                data={"load": controller, "codsem": codsem},
                headers={
                    "Cookie": cookies,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Mozilla/5.0",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://academico.unas.edu.pe/"
                },
                timeout=15
            )
            if resp.status_code != 200:
                return ""

            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Detectar tipo de contenido por controlador
            if "Qualifications" in controller or "RecordNotes" in controller:
                return self._parse_calificaciones(soup, codsem)
            elif "Schedule" in controller:
                return self._parse_horario(soup, codsem)
            elif "Enrollment" in controller or "EnrolledCourses" in controller:
                return self._parse_cursos(soup, codsem)
            elif "Payment" in controller or "Debt" in controller or "Tuition" in controller:
                return self._parse_pagos(soup, codsem)
            elif "OrderOfMerit" in controller:
                return self._parse_generic(soup, codsem, "Orden de Mérito")
            else:
                return self._parse_generic(soup, codsem, "")

        except Exception as e:
            print(f"[SCRAPE ERROR] {controller}: {e}")
            return ""

    def _get_cell_text(self, td) -> str:
        """Extrae texto limpio de una celda, uniendo elementos internos con espacio."""
        from bs4 import NavigableString
        parts = []
        for child in td.children:
            if isinstance(child, NavigableString):
                t = child.strip()
                if t:
                    parts.append(t)
            elif child.name in ["br"]:
                parts.append(" | ")
            else:
                t = child.get_text(separator=" ", strip=True)
                if t:
                    parts.append(t)
        return " ".join(parts).strip()

    def _parse_calificaciones(self, soup, codsem: str) -> str:
        """Parser específico para calificaciones — genera Markdown estructurado."""
        lines = [f"# Calificaciones del Semestre {codsem}\n"]
        
        # Info del estudiante
        first_table = soup.find("table")
        if first_table:
            tbody = first_table.find("tbody")
            if tbody:
                row = tbody.find("tr")
                if row:
                    cells = [self._get_cell_text(td) for td in row.find_all("td")]
                    if any(cells):
                        lines.append(f"**Estudiante:** {' | '.join(c for c in cells if c)}\n")
        
        # Cada curso
        for ibox in soup.find_all("div", class_="ibox"):
            title_el = ibox.find("div", class_="ibox-title")
            if not title_el:
                continue
            
            # Código y nombre del curso
            label = title_el.find("span", class_="label")
            codigo = label.get_text(strip=True) if label else ""
            nombre = title_el.get_text(separator=" ", strip=True)
            if codigo:
                nombre = nombre.replace(codigo, "").strip()
            
            lines.append(f"\n## {codigo} — {nombre}")
            
            table = ibox.find("table")
            if not table:
                continue
            
            # Encabezados
            thead = table.find("thead")
            headers = []
            if thead:
                headers = [self._get_cell_text(th) for th in thead.find_all("th")]
            
            # Filas de evaluaciones
            tbody = table.find("tbody")
            eval_rows = []
            if tbody:
                for tr in tbody.find_all("tr"):
                    cells = [self._get_cell_text(td) for td in tr.find_all(["td","th"])]
                    if any(c for c in cells if c):
                        eval_rows.append(cells)
            
            # Promedios del tfoot
            tfoot = table.find("tfoot")
            tfoot_rows = []
            if tfoot:
                for tr in tfoot.find_all("tr"):
                    cells = [self._get_cell_text(th) for th in tr.find_all(["td","th"])]
                    if any(c for c in cells if c):
                        tfoot_rows.append(cells)
            
            if eval_rows and headers:
                lines.append("| " + " | ".join(headers) + " |")
                lines.append("|" + "|".join(["---"] * len(headers)) + "|")
                for row in eval_rows:
                    lines.append("| " + " | ".join(row) + " |")
            elif not eval_rows:
                lines.append("*Sin evaluaciones registradas aún*")
            
            # Mostrar promedios
            for row in tfoot_rows:
                badge = row[0] if row else ""
                desc = row[1] if len(row) > 1 else ""
                puntaje = row[-1] if row else "0"
                val = puntaje if puntaje and puntaje != "0" else "Sin registro"
                lines.append(f"- **{badge} {desc}:** {val}")
        
        return "\n".join(lines)

    def _parse_horario(self, soup, codsem: str) -> str:
        """Parser específico para horario — genera tabla Markdown."""
        lines = [f"# Horario de Clases — Semestre {codsem}\n"]
        
        table = soup.find("table")
        if not table:
            return f"# Horario {codsem}\nSin datos disponibles."
        
        # Encabezados (días)
        thead = table.find("thead")
        if thead:
            headers = [self._get_cell_text(th) for th in thead.find_all("th")]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|" + "|".join(["---"] * len(headers)) + "|")
        
        # Filas por hora
        tbody = table.find("tbody")
        if tbody:
            for tr in tbody.find_all("tr"):
                cells = []
                for td in tr.find_all(["td","th"]):
                    # Dentro de cada celda del horario hay divs con curso/docente/aula
                    inner_divs = td.find_all("div", recursive=False)
                    if inner_divs:
                        # Extraer texto de cada div interno
                        parts = []
                        for div in inner_divs:
                            t = div.get_text(separator=" ", strip=True)
                            if t:
                                parts.append(t)
                        cells.append("<br>".join(parts) if parts else "")
                    else:
                        cells.append(self._get_cell_text(td))
                
                if cells:
                    lines.append("| " + " | ".join(cells) + " |")
        
        return "\n".join(lines)

    def _parse_cursos(self, soup, codsem: str) -> str:
        """Parser para cursos matriculados."""
        lines = [f"# Cursos Matriculados — Semestre {codsem}\n"]
        
        table = soup.find("table")
        if not table:
            return "\n".join(lines) + "Sin datos."
        
        thead = table.find("thead")
        if thead:
            headers = [self._get_cell_text(th) for th in thead.find_all("th")]
            lines.append("| " + " | ".join(h for h in headers if h) + " |")
            lines.append("|" + "|".join(["---"] * len([h for h in headers if h])) + "|")
        
        tbody = table.find("tbody")
        if tbody:
            for tr in tbody.find_all("tr"):
                cells = [self._get_cell_text(td) for td in tr.find_all(["td","th"])]
                if any(c for c in cells if c):
                    lines.append("| " + " | ".join(cells) + " |")
        
        return "\n".join(lines)

    def _parse_pagos(self, soup, codsem: str) -> str:
        """Parser para pagos y deudas."""
        h2 = soup.find("h2")
        titulo = h2.get_text(strip=True) if h2 else "Estado de Pagos"
        lines = [f"# {titulo} — Semestre {codsem}\n"]
        
        for table in soup.find_all("table"):
            thead = table.find("thead")
            if thead:
                headers = [self._get_cell_text(th) for th in thead.find_all("th")]
                if any(headers):
                    lines.append("| " + " | ".join(h for h in headers if h) + " |")
                    lines.append("|" + "|".join(["---"] * len([h for h in headers if h])) + "|")
            
            tbody = table.find("tbody")
            if tbody:
                for tr in tbody.find_all("tr"):
                    cells = [self._get_cell_text(td) for td in tr.find_all(["td","th"])]
                    if any(c for c in cells if c):
                        lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
        
        return "\n".join(lines)

    def _parse_generic(self, soup, codsem: str, titulo: str) -> str:
        """Parser genérico para cualquier sección."""
        h2 = soup.find("h2")
        t = h2.get_text(strip=True) if h2 else titulo
        lines = [f"# {t} — Semestre {codsem}\n"]
        
        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                cells = [self._get_cell_text(td) for td in tr.find_all(["td","th"])]
                if any(c for c in cells if c):
                    lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
        
        if len(lines) <= 2:
            # Sin tablas — extraer texto general
            for tag in soup.find_all(["p","li","h3","h4","h5"]):
                t = tag.get_text(strip=True)
                if t:
                    lines.append(f"- {t}")
        
        return "\n".join(lines)

    def query_realtime(self, question: str, cookies: str) -> str:
        codsem = self._get_current_semester(cookies)
        if codsem == "" or "login" in codsem.lower():
            return "SESION_EXPIRADA"

        q = question.lower()

        if any(w in q for w in ["nota", "calificacion", "calificación", "promedio", "jalar"]):
            controllers = ["StudentQualificationsController@index"]
        elif any(w in q for w in ["horario", "clase", "hora", "aula"]):
            controllers = ["StudentScheduleController@index"]
        elif any(w in q for w in ["pago", "pagar", "pagué"]):
            controllers = ["StudentPaymentReportController@index"]
        elif any(w in q for w in ["deuda", "debo", "debe", "monto"]):
            controllers = ["StudentDebtReportController@index"]
        elif any(w in q for w in ["matrícula", "matricula", "matriculado", "cursos matriculados"]):
            controllers = ["StudentEnrolledCoursesController@index"]
        elif any(w in q for w in ["orden", "mérito", "merito", "ranking", "puesto"]):
            controllers = ["StudenOrderOfMeritController@index"]
        elif any(w in q for w in ["sílabo", "silabo", "syllabus"]):
            controllers = ["StudentSyllabusController@index"]
        elif any(w in q for w in ["curso", "disponible", "activado"]):
            controllers = ["StudentActivatedCoursesController@index"]
        else:
            controllers = ["StudentQualificationsController@index",
                           "StudentEnrolledCoursesController@index"]

        results = []
        for ctrl in controllers:
            content = self._scrape_section(ctrl, cookies, codsem)
            if content:
                results.append(content)

        return "\n\n".join(results)

    def scrape_page(self, page_key: str, cookies: str) -> str:
        # Legacy method - mantenido por compatibilidad
        return f"Contenido de {page_key} extraído correctamente."