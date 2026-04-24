# EncroWatch v2 🌊
## Water Body Encroachment Detector — Puducherry UT
### Innovation Puducherry 2026 | GEE-Powered Backend

---

## Quick Start

```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5000
```

**Demo mode works without GEE** — realistic Puducherry data loads automatically.

---

## Enabling Google Earth Engine

### Step 1: Create GEE Cloud Project
1. Go to console.cloud.google.com
2. Create a new project (e.g. `encrowatch-pdy-2026`)
3. Enable the **Earth Engine API**
4. Go to code.earthengine.google.com → Settings → Register your project

### Step 2: Authenticate
```bash
# Option A: Interactive OAuth (easiest for local dev)
earthengine authenticate

# Option B: Service Account (for deployment)
# Download JSON key from Google Cloud IAM → Service Accounts
# Set environment variables:
export GEE_PROJECT_ID=your-project-id
export GEE_SERVICE_ACCOUNT=your-sa@project.iam.gserviceaccount.com
export GEE_KEY_FILE=/path/to/key.json
```

### Step 3: Run with GEE
```bash
GEE_PROJECT_ID=your-project-id python app.py
```

The GEE status pill in the topbar will turn green when connected.

### Windows PowerShell setup for this project
1. Copy `.env.example` to `.env` inside `encrowatch_v2`
2. Set `GEE_PROJECT_ID` to your registered Google Cloud project ID
3. Run authentication from the project virtualenv:

```powershell
.\.venv\Scripts\earthengine.exe authenticate
```

4. Start the backend from the same folder:

```powershell
.\.venv\Scripts\python.exe .\app.py
```

5. If you authenticate after the app is already running, call `POST /api/gee/reconnect` or click the GEE status pill to re-check the current state.

---

## Features

### Study Area Input (3 methods)
| Method | How |
|--------|-----|
| **Draw Polygon** | Click "Draw Polygon" → click points on map → double-click to finish |
| **Draw Rectangle** | Click "Draw Rectangle" → drag on map |
| **Upload File** | Drop .geojson or zipped shapefile → appears on map as purple layer |
| **Known Water Bodies** | Select from dropdown: Ousteri Lake, Bahour Lake, etc. |

### GEE Analysis (when connected)
- **JRC Global Surface Water** — permanent water baseline (80%+ occurrence)
- **Sentinel-2 SR** (2017+) — MNDWI water detection + NDBI built-up
- **Landsat 8/9** (2013–2017) — NDBI built-up for older years
- **GHSL P2023A** — Global Human Settlement Layer for habitation counting

### Dashboard Output
- 4 stat cards: Water Area, Encroachment Area, Habitation Count, Water Retention %
- **Line chart**: Yearly habitation count on water bodies
- **Bar chart**: Water area vs encroachment area (ha)
- **Line chart**: Encroachment % growth over time
- **Stacked bar**: Encroachment type breakdown (Residential / Commercial / Large Dev)
- **Data table**: Year-wise comparison
- **CSV export**: Full dataset download
- **PDF report**: Government-format alert document

### Known Puducherry Water Bodies
| ID | Name | Area |
|----|------|------|
| `ousteri` | Ousteri Lake (Osudu Lake) | ~389 ha |
| `bahour` | Bahour Lake | ~313 ha |
| `redhills` | Red Hills Lake (Ariyankuppam) | ~98 ha |
| `pillaipalayam` | Pillaipalayam Kanmoi | ~54 ha |
| `kanag` | Kanagarayanpalayam Tank | ~76 ha |

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | GEE connection status |
| `/api/water-bodies` | GET | All known water body geometries |
| `/api/analyse` | POST | Run full analysis on a geometry |
| `/api/upload/cadastral` | POST | Upload shapefile/GeoJSON |
| `/api/report` | POST | Generate PDF report |
| `/api/report/csv` | POST | Export CSV data |

---

## File Structure

```
encrowatch_v2/
├── app.py                      ← Flask backend + all API routes
├── gee_water_analysis.py       ← GEE Python API analysis module
├── requirements.txt
├── templates/
│   └── index.html              ← Complete dashboard (single file)
├── reports/
│   └── pdf_report_v2.py        ← Government PDF generator
└── uploads/                    ← Uploaded cadastral files
```

---

## Credentials for Demo Login
- Username: `inspector.pdy`
- Password: `EW@2026`

Built by WEC Puducherry · Innovation Puducherry 2026
