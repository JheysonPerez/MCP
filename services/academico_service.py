import requests
import time
import uuid
from typing import Dict, Tuple
from bs4 import BeautifulSoup

# Diccionario global para mantener sesiones requests entre llamadas
# Key: session_id, Value: (requests.Session, timestamp)
SESSIONS_DICT: Dict[str, Tuple[requests.Session, float]] = {}
SESSION_TTL_SECONDS = 300  # 5 minutos


def _cleanup_old_sessions():
    """Elimina sesiones expiradas del diccionario global."""
    now = time.time()
    expired = [sid for sid, (session, ts) in SESSIONS_DICT.items() if now - ts > SESSION_TTL_SECONDS]
    for sid in expired:
        del SESSIONS_DICT[sid]


class AcademicoService:
    BASE_URL = "https://academico.unas.edu.pe"

    def __init__(self):
        self._cookies = None
        self._session_valid = False
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-PE,es;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }

    def start_login_session(self, username: str, password: str) -> Dict:
        """
        Inicia sesión requests, obtiene página de login, extrae CAPTCHA y usertoken.
        Devuelve session_id, captcha_image (base64) y token para uso posterior.
        """
        _cleanup_old_sessions()
        
        try:
            # Crear nueva sesión requests
            session = requests.Session()
            session.headers.update(self._headers)
            
            # GET a la página de login
            login_url = f"{self.BASE_URL}/login"
            resp = session.get(login_url, timeout=15, allow_redirects=True)
            resp.raise_for_status()
            
            # Parsear HTML con BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Extraer imagen CAPTCHA (data:image/jpeg;base64,...)
            captcha_img = soup.find('img', {'id': 'capcode'})
            captcha_b64 = ""
            if captcha_img and captcha_img.get('src'):
                src = captcha_img['src']
                if src.startswith('data:image'):
                    # Extraer solo la parte base64 después de la coma
                    captcha_b64 = src.split(',', 1)[1] if ',' in src else src
                else:
                    captcha_b64 = src
            
            # Extraer usertoken (puede estar vacío, pero lo enviamos igual)
            token_input = soup.find('input', {'id': 'usertoken'})
            usertoken = token_input.get('value', '') if token_input else ''
            
            # Generar session_id único
            session_id = uuid.uuid4().hex
            
            # Guardar en diccionario global con timestamp
            SESSIONS_DICT[session_id] = (session, time.time())
            
            return {
                "success": True,
                "captcha_image": captcha_b64,
                "session_id": session_id,
                "usertoken": usertoken
            }
            
        except requests.RequestException as e:
            return {"success": False, "error": f"Error de conexión: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Error inesperado: {str(e)}"}

    def complete_login_with_captcha(self, username: str, password: str, captcha_solution: str, session_id: str, usertoken: str = "") -> Dict:
        """
        Completa el login enviando POST con credenciales + CAPTCHA.
        Verifica éxito por presencia de cookie SGASID.
        """
        _cleanup_old_sessions()
        
        # Recuperar sesión del diccionario
        if session_id not in SESSIONS_DICT:
            return {"success": False, "error": "Sesión expirada. Por favor intenta nuevamente."}
        
        session, _ = SESSIONS_DICT[session_id]
        
        try:
            # Construir payload exacto como el navegador
            payload = {
                "username": username,
                "userpasw": password,
                "captcha": captcha_solution,
                "usercaptcha": captcha_solution,
                "usertoken": usertoken  # puede ser "" — se envía igual
            }
            
            # Headers específicos para el POST (incluir Referer)
            post_headers = {
                **self._headers,
                'Referer': f"{self.BASE_URL}/login",
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': self.BASE_URL,
            }
            
            # POST al login
            login_url = f"{self.BASE_URL}/login"
            resp = session.post(login_url, data=payload, headers=post_headers, timeout=15, allow_redirects=True)
            
            # DEBUG: Ver exactamente qué responde UNAS
            print(f"[LOGIN DEBUG] payload={payload}")
            print(f"[LOGIN DEBUG] status={resp.status_code}")
            print(f"[LOGIN DEBUG] final_url={resp.url}")
            print(f"[LOGIN DEBUG] cookies={dict(session.cookies)}")
            print(f"[LOGIN DEBUG] response_preview={resp.text[:500]}")
            
            # Verificar éxito: UNAS responde con JSON {"login":true,"status":"success"}
            # o podemos verificar por cookie SGASID como backup
            login_ok = False
            
            # Opción 1: verificar JSON response
            try:
                json_resp = resp.json()
                login_ok = json_resp.get("login") == True or json_resp.get("status") == "success"
                print(f"[LOGIN DEBUG] json_parsed={json_resp}, login_ok={login_ok}")
            except Exception as e:
                print(f"[LOGIN DEBUG] json_parse_failed: {e}")
                login_ok = False
            
            # Opción 2: verificar cookie SGASID como backup
            if not login_ok:
                cookies_dict = session.cookies.get_dict()
                login_ok = "SGASID" in cookies_dict
                print(f"[LOGIN DEBUG] cookie_check: SGASID in cookies = {login_ok}")
            
            if not login_ok:
                # Extraer mensaje de error del JSON o HTML
                error_msg = "Login fallido. Verifica credenciales y CAPTCHA."
                try:
                    json_resp = resp.json()
                    error_msg = json_resp.get("message", error_msg)
                except:
                    # Intentar extraer de HTML
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    alert = soup.find('div', class_='alert-danger') or soup.find('div', class_='alert')
                    if alert:
                        error_msg = alert.get_text(strip=True)
                
                return {"success": False, "error": error_msg}
            
            # Éxito: construir string de cookies
            cookies_dict = session.cookies.get_dict()
            cookies_str = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
            
            # Limpiar sesión del diccionario (ya no se necesita)
            del SESSIONS_DICT[session_id]
            
            return {
                "success": True,
                "cookies": cookies_str,
                "username": username
            }
            
        except requests.RequestException as e:
            return {"success": False, "error": f"Error de conexión: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Error inesperado: {str(e)}"}
        finally:
            # Cleanup siempre, aunque falle
            if session_id in SESSIONS_DICT:
                del SESSIONS_DICT[session_id]

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