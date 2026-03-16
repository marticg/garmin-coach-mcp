# Garmin Coach IA — Servidor MCP

Servidor MCP que connecta les teves dades reals de Garmin Connect
directament amb Claude i ChatGPT. Sense exportar res, sense copiar JSONs.
Simplement pregunta i obté respostes basades en les teves dades reals.

---

## Eines disponibles (18 total)

| Eina                  | Descripció                                          |
|-----------------------|-----------------------------------------------------|
| `get_sleep`           | Dades de son d'una nit (HRV, SpO2, fases)          |
| `get_sleep_summary`   | Resum de son N dies (tendències, alertes)           |
| `get_hrv`             | Variabilitat de la FC — indicador de recuperació    |
| `get_activities`      | Activitats esportives (running, cycling, etc.)      |
| `get_steps`           | Passos diaris i minuts d'intensitat                 |
| `get_today_stats`     | Estadístiques d'avui en temps real                  |
| `get_body_battery`    | Historial de Body Battery                           |
| `get_stress`          | Historial d'estrès                                  |
| `get_heart_rate`      | FC en repòs i tendència                             |
| `get_vo2max`          | VO2max i edat de forma física                       |
| `get_training_status` | Readiness, càrrega i temps de recuperació           |
| `get_training_load`   | Càrrega d'entrenament setmanal                      |
| `get_weight`          | Pes i composició corporal                           |
| `get_user_profile`    | Perfil personal configurat                          |
| `get_full_snapshot`   | Tot en una sola crida — resum complet               |

---

## Desplegament pas a pas

### PART 1 — Preparar el codi a GitHub

1. Crea un compte a https://github.com (si no en tens)
2. Crea un repositori nou anomenat `garmin-coach-mcp`
3. Puja els 3 fitxers:
   - `server.py`
   - `requirements.txt`
   - `render.yaml`

   Pots fer-ho des del navegador: a GitHub, clica "Add file" → "Upload files"

### PART 2 — Desplegar a Render

1. Ves a https://render.com i crea un compte (gratuït)
2. Clica "New +" → "Web Service"
3. Connecta el teu compte de GitHub
4. Selecciona el repositori `garmin-coach-mcp`
5. Render detecta automàticament el `render.yaml` — clica "Deploy"

### PART 3 — Configurar les variables d'entorn

Al panell de Render → el teu servei → "Environment":

| Variable        | Valor                    | Obligatori |
|-----------------|--------------------------|------------|
| GARMIN_EMAIL    | el_teu@email.com         | ✓          |
| GARMIN_PASSWORD | la_teva_contrasenya      | ✓          |
| MCP_TOKEN       | (Render el genera sol)   | automàtic  |
| USER_NAME       | El teu nom               | opcional   |
| USER_AGE        | 59                       | recomanat  |
| USER_SEX        | home / dona / altre      | recomanat  |
| USER_HEIGHT     | 170                      | opcional   |
| USER_WEIGHT     | 73                       | opcional   |
| USER_GOAL       | salut general            | opcional   |
| USER_LANG       | ca                       | opcional   |

### PART 4 — Obtenir la URL del servidor

Un cop desplegat, el teu servidor tindrà una URL com:
```
https://garmin-coach-mcp-xxxx.onrender.com
```

Per veure el token, ves a la URL base:
```
https://garmin-coach-mcp-xxxx.onrender.com/health
```

La teva URL MCP completa serà:
```
https://garmin-coach-mcp-xxxx.onrender.com/mcp?token=EL_TEU_TOKEN
```

### PART 5 — Connectar a Claude (mòbil)

A l'app de Claude al mòbil (iOS o Android):

1. Ves a **Configuració** → **Connectors** (o "Integrations")
2. Clica "Afegir connector MCP"
3. Introdueix la teva URL:
   ```
   https://garmin-coach-mcp-xxxx.onrender.com/mcp?token=EL_TEU_TOKEN
   ```
4. Claude descobreix automàticament les 18 eines

### PART 6 — Provar-ho!

Escriu a Claude:
- "Com he dormit aquesta setmana?"
- "Hauria d'entrenar avui o descansar?"
- "Quines són les meves tendències de VO2max?"
- "Fes-me un resum complet de la meva salut"

---

## Seguretat

- Les credencials de Garmin es guarden com a variables d'entorn a Render (xifrades)
- El token MCP protegeix l'accés al servidor
- Cap dada es guarda al servidor — cada crida va directament a Garmin
- El codi és obert i auditable

---

## Costos

| Pla          | Preu   | Característiques               |
|--------------|--------|--------------------------------|
| Gratuït      | 0€/mes | Cold start 15-30 seg           |
| Starter      | 7€/mes | Sempre actiu, sense cold start |
