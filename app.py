"""
EncroWatch v2 — Flask Backend
Water Body Encroachment Detection | Puducherry UT
Google Earth Engine Python API Integration
"""

from flask import Flask, jsonify, request, render_template, send_file, session
import os, json, io, logging, traceback
from datetime import datetime
from functools import wraps
import geopandas as gpd

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_env_file(env_path: str) -> None:
    """Load simple KEY=VALUE entries from a local .env file if present."""
    if not os.path.exists(env_path):
        return

    with open(env_path, 'r', encoding='utf-8') as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


for candidate_env in (
    os.path.join(os.path.dirname(BASE_DIR), '.env'),
    os.path.join(BASE_DIR, '.env'),
):
    load_env_file(candidate_env)


def read_env(name: str, default=None):
    """Normalize env values and ignore placeholder strings."""
    value = os.environ.get(name, default)
    if value is None:
        return None
    value = value.strip()
    if not value or value.lower() in {'none', 'null'}:
        return None
    if name == 'GEE_PROJECT_ID' and value == 'your-gee-project-id':
        return None
    return value

# ── GEE Import (graceful fallback if not installed) ───────────────────────────
GEE_AVAILABLE = False
try:
    import ee
    from gee_water_analysis import (
        initialize_gee, get_gee_status,
        analyze_water_encroachment, get_demo_results,
        upload_cadastral_to_gee
    )
    GEE_AVAILABLE = True
    logger.info('GEE Python API available')
except ImportError:
    from gee_water_analysis import get_demo_results
    logger.warning('GEE not installed — running in demo mode only')

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = 'encrowatch-v2-puducherry-2026'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB upload limit
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ── GEE Configuration ─────────────────────────────────────────────────────────
GEE_PROJECT_ID   = read_env('GEE_PROJECT_ID')
GEE_SERVICE_ACCT = read_env('GEE_SERVICE_ACCOUNT')
GEE_KEY_FILE     = read_env('GEE_KEY_FILE')


def get_gee_configuration() -> dict:
    return {
        'project_id': GEE_PROJECT_ID,
        'service_account_configured': bool(GEE_SERVICE_ACCT),
        'key_file_configured': bool(GEE_KEY_FILE and os.path.exists(GEE_KEY_FILE)),
        'key_file_path': GEE_KEY_FILE,
        'configured': bool(GEE_PROJECT_ID or (GEE_SERVICE_ACCT and GEE_KEY_FILE)),
    }


def refresh_gee_status() -> dict:
    """Initialize or re-check the Earth Engine connection."""
    status = {
        'connected': False,
        'available': GEE_AVAILABLE,
        'mode': 'demo',
        'message': 'Google Earth Engine not initialized',
        'last_checked': datetime.now().isoformat(),
        **get_gee_configuration(),
    }

    if not GEE_AVAILABLE:
        status['message'] = 'earthengine-api is not installed in the backend environment'
        return status

    if GEE_KEY_FILE and not os.path.exists(GEE_KEY_FILE):
        status['message'] = f'Configured GEE key file was not found: {GEE_KEY_FILE}'
        return status

    if not status['configured']:
        status['message'] = (
            'Set GEE_PROJECT_ID for OAuth, or set GEE_SERVICE_ACCOUNT and '
            'GEE_KEY_FILE for service-account authentication'
        )
        return status

    result = initialize_gee(GEE_PROJECT_ID, GEE_SERVICE_ACCT, GEE_KEY_FILE)
    status['init_mode'] = result.get('mode', 'none')
    status['init_message'] = result.get('message', '')

    if result.get('success'):
        live_status = get_gee_status()
        status['connected'] = live_status.get('connected', False)
        status['message'] = live_status.get('message', result.get('message', ''))
        status['mode'] = 'live' if status['connected'] else 'demo'
    else:
        status['message'] = result.get('message', status['message'])

    return status

# Initialize GEE on startup
GEE_STATUS = refresh_gee_status()
if GEE_STATUS.get('connected'):
    logger.info(f'GEE status: {GEE_STATUS}')
else:
    logger.warning(f'GEE init failed: {GEE_STATUS.get("message")} â€” using demo mode')

# Legacy startup block kept disabled to avoid duplicate initialization.
if False and GEE_STATUS.get('connected'):
    result = initialize_gee(GEE_PROJECT_ID, GEE_SERVICE_ACCT, GEE_KEY_FILE)
    if result['success']:
        gee_status = get_gee_status()
        GEE_STATUS = gee_status
        logger.info(f'GEE status: {gee_status}')
    else:
        logger.warning(f'GEE init failed: {result["message"]} — using demo mode')

# ── Inspector Login ───────────────────────────────────────────────────────────
USERS = {
    'inspector.pdy': {
        'password': 'EW@2026', 'name': 'Inspector R. Kamala',
        'district': 'Puducherry', 'role': 'Revenue Inspector'
    },
    'admin': {
        'password': 'Admin@2026', 'name': 'Administrator',
        'district': 'Puducherry', 'role': 'Administrator'
    },
}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

# ── Known Puducherry Water Bodies (pre-defined geometries) ───────────────────
PUDUCHERRY_WATER_BODIES = {
    'ousteri': {
        'name': 'Ousteri Lake (Osudu Lake)',
        'area_ha': 389.5,
        'coordinates': [[[
            [79.7870, 11.9100], [79.8020, 11.9090], [79.8120, 11.9140],
            [79.8150, 11.9230], [79.8140, 11.9310], [79.8080, 11.9380],
            [79.7990, 11.9410], [79.7900, 11.9390], [79.7830, 11.9340],
            [79.7810, 11.9260], [79.7820, 11.9180], [79.7870, 11.9100]
        ]]],
        'type': 'MultiPolygon'
    },
    'bahour': {
        'name': 'Bahour Lake',
        'area_ha': 312.8,
        'coordinates': [[[
            [79.7276, 11.8121], [79.7276, 11.8356], [79.7468, 11.8356],
            [79.7468, 11.8121], [79.7276, 11.8121]
        ]]],
        'type': 'MultiPolygon'
    },
    'redhills': {
        'name': 'Red Hills Lake (Ariyankuppam)',
        'area_ha': 98.4,
        'coordinates': [[[
            [79.8034, 11.8989], [79.8034, 11.8892], [79.8166, 11.8892],
            [79.8166, 11.8989], [79.8034, 11.8989]
        ]]],
        'type': 'MultiPolygon'
    },
    'pillaipalayam': {
        'name': 'Pillaipalayam Kanmoi',
        'area_ha': 54.2,
        'coordinates': [[[
            [79.7930, 11.9620], [79.8010, 11.9610], [79.8050, 11.9660],
            [79.8030, 11.9720], [79.7960, 11.9730], [79.7910, 11.9690],
            [79.7910, 11.9640], [79.7930, 11.9620]
        ]]],
        'type': 'MultiPolygon'
    },
    'kanag': {
        'name': 'Kanagarayanpalayam Tank',
        'area_ha': 76.3,
        'coordinates': [[[
            [79.8380, 11.9420], [79.8480, 11.9410], [79.8530, 11.9470],
            [79.8510, 11.9540], [79.8440, 11.9560], [79.8370, 11.9520],
            [79.8360, 11.9450], [79.8380, 11.9420]
        ]]],
        'type': 'MultiPolygon'
    },
}


# ════════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'gee_connected': GEE_STATUS.get('connected', False),
        'gee_message':   GEE_STATUS.get('message', ''),
        'demo_mode':     not GEE_STATUS.get('connected', False),
        'gee_project_id': GEE_STATUS.get('project_id'),
        'project':       'EncroWatch v2 | Puducherry UT'
    })

# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    user = USERS.get(data.get('username', '').strip())
    if user and user['password'] == data.get('password', '').strip():
        session.update(logged_in=True, username=data['username'],
                       user_name=user['name'], user_role=user['role'],
                       district=user['district'])
        return jsonify({'success': True, **{k: v for k, v in user.items() if k != 'password'}})
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/status')
def api_status():
    """Return GEE connection status for dashboard badge."""
    return jsonify({
        'gee_connected': GEE_STATUS.get('connected', False),
        'gee_mode':      'Live GEE' if GEE_STATUS.get('connected') else 'Demo Mode',
        'gee_message':   GEE_STATUS.get('message', ''),
        'gee_available': GEE_STATUS.get('available', False),
        'gee_configured': GEE_STATUS.get('configured', False),
        'gee_init_mode': GEE_STATUS.get('init_mode'),
        'project_id':    GEE_STATUS.get('project_id'),
        'last_checked':  GEE_STATUS.get('last_checked'),
        'timestamp':     datetime.now().isoformat(),
    })


@app.route('/api/gee/reconnect', methods=['POST'])
def api_gee_reconnect():
    """Re-read GEE config and refresh connection status."""
    global GEE_STATUS, GEE_PROJECT_ID, GEE_SERVICE_ACCT, GEE_KEY_FILE

    load_env_file(os.path.join(os.path.dirname(BASE_DIR), '.env'))
    load_env_file(os.path.join(BASE_DIR, '.env'))

    GEE_PROJECT_ID = read_env('GEE_PROJECT_ID')
    GEE_SERVICE_ACCT = read_env('GEE_SERVICE_ACCOUNT')
    GEE_KEY_FILE = read_env('GEE_KEY_FILE')
    GEE_STATUS = refresh_gee_status()

    return jsonify({
        'success': True,
        'gee_connected': GEE_STATUS.get('connected', False),
        'gee_mode': 'Live GEE' if GEE_STATUS.get('connected') else 'Demo Mode',
        'gee_message': GEE_STATUS.get('message', ''),
        'project_id': GEE_STATUS.get('project_id'),
        'last_checked': GEE_STATUS.get('last_checked'),
    })

# ── Water Bodies ──────────────────────────────────────────────────────────────

@app.route('/api/water-bodies')
def api_water_bodies():
    """Return list of known Puducherry water bodies with geometries."""
    bodies = []
    for key, wb in PUDUCHERRY_WATER_BODIES.items():
        bodies.append({
            'id':       key,
            'name':     wb['name'],
            'area_ha':  wb['area_ha'],
            'geometry': {'type': wb['type'], 'coordinates': wb['coordinates']}
        })
    return jsonify({'water_bodies': bodies})

# ── Analysis ──────────────────────────────────────────────────────────────────

@app.route('/api/analyse', methods=['POST'])
def api_analyse():
    """
    Main analysis endpoint.
    Accepts:
      - geometry: GeoJSON geometry (from drawn polygon or known water body)
      - years: list of years e.g. [2016, 2018, 2020, 2022, 2024]
      - mndwi_threshold: float (default 0.0)
      - use_demo: bool (force demo mode)
    """
    data = request.json or {}
    geometry   = data.get('geometry')
    years      = data.get('years', [2016, 2018, 2020, 2022, 2024])
    threshold  = float(data.get('mndwi_threshold', 0.0))
    force_demo = data.get('use_demo', False)

    if not geometry:
        return jsonify({'success': False, 'error': 'No geometry provided'}), 400

    # Validate years
    years = sorted([int(y) for y in years if 2013 <= int(y) <= 2025])
    if not years:
        return jsonify({'success': False, 'error': 'No valid years in range 2013–2025'}), 400

    logger.info(f'Analysis request: years={years}, geo_type={geometry.get("type")}, demo={force_demo}')

    use_gee = GEE_STATUS.get('connected', False) and GEE_AVAILABLE and not force_demo

    try:
        if use_gee:
            logger.info('Running LIVE GEE analysis...')
            result = analyze_water_encroachment(geometry, years, threshold)
        else:
            logger.info('Running demo mode analysis...')
            result = get_demo_results(geometry, years)

        result['gee_used'] = use_gee
        return jsonify(result)

    except Exception as e:
        logger.error(f'Analysis error: {traceback.format_exc()}')
        # Graceful fallback to demo
        try:
            result = get_demo_results(geometry, years)
            result['gee_used'] = False
            result['fallback_reason'] = str(e)
            return jsonify(result)
        except:
            return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analyse/waterbody/<wb_id>', methods=['POST'])
def api_analyse_waterbody(wb_id):
    """Analyse a pre-defined Puducherry water body by ID."""
    wb = PUDUCHERRY_WATER_BODIES.get(wb_id)
    if not wb:
        return jsonify({'success': False, 'error': f'Unknown water body: {wb_id}'}), 404

    data  = request.json or {}
    years = data.get('years', [2016, 2018, 2020, 2022, 2024])
    geometry = {'type': wb['type'], 'coordinates': wb['coordinates']}

    # Forward to main analysis
    request._cached_json = {'geometry': geometry, 'years': years}
    return api_analyse()

# ── File Upload ───────────────────────────────────────────────────────────────

@app.route('/api/upload/cadastral', methods=['POST'])
def api_upload_cadastral():
    """
    Upload cadastral/revenue vector data.
    Accepts: .geojson, .json, .zip (zipped shapefile)
    Returns: feature count + geometry envelope + first 10 feature previews
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']
    filename = file.filename.lower()
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    try:
        if filename.endswith('.geojson') or filename.endswith('.json'):
            gdf = gpd.read_file(save_path)
        elif filename.endswith('.zip'):
            gdf = gpd.read_file(f'zip://{save_path}')
        elif filename.endswith('.shp'):
            gdf = gpd.read_file(save_path)
        else:
            return jsonify({'success': False, 'error': 'Unsupported file format. Use .geojson, .zip (shapefile), or .shp'}), 400

        # Reproject to EPSG:4326 if needed
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        # Build response
        bounds = gdf.total_bounds.tolist()  # [minx, miny, maxx, maxy]
        geojson_str = gdf.to_json()
        geojson_data = json.loads(geojson_str)

        # Column info
        cols = {col: str(dtype) for col, dtype in gdf.dtypes.items() if col != 'geometry'}

        return jsonify({
            'success':       True,
            'feature_count': len(gdf),
            'columns':       cols,
            'crs':           str(gdf.crs),
            'bounds':        bounds,
            'geojson':       geojson_data,
            'preview':       geojson_data['features'][:10],
        })

    except Exception as e:
        logger.error(f'Upload error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Report Generation ─────────────────────────────────────────────────────────

@app.route('/api/report', methods=['POST'])
def api_report():
    """Generate PDF report from analysis results."""
    data = request.json or {}
    analysis = data.get('analysis', {})
    meta     = data.get('meta', {})

    try:
        from reports.pdf_report_v2 import generate_water_report
        pdf_bytes = generate_water_report(analysis, meta, {
            'name': session.get('user_name', 'Inspector'),
            'role': session.get('user_role', 'Revenue Inspector'),
        })
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True,
                         download_name=f'EncroWatch_WaterReport_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf')
    except Exception as e:
        logger.error(f'Report error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/report/csv', methods=['POST'])
def api_report_csv():
    """Export analysis data as CSV."""
    data     = request.json or {}
    analysis = data.get('analysis', {})
    years    = analysis.get('years', {})

    import csv
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Year', 'Water Area (ha)', 'Encroachment Area (ha)',
                     'Water Lost (ha)', 'Habitation Count',
                     'Encroachment %', 'Water Retention %',
                     'Residential (ha)', 'Commercial (ha)', 'Large Dev (ha)'])
    for year, vals in sorted(years.items()):
        types = vals.get('encroachment_types', {})
        writer.writerow([
            year,
            vals.get('water_area_ha', ''),
            vals.get('encroachment_area_ha', ''),
            vals.get('water_lost_ha', ''),
            vals.get('habitation_count', ''),
            vals.get('encroachment_pct', ''),
            vals.get('water_retention_pct', ''),
            types.get('residential_ha', ''),
            types.get('commercial_ha', ''),
            types.get('large_dev_ha', ''),
        ])

    buf.seek(0)
    return send_file(
        io.BytesIO(buf.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'EncroWatch_Data_{datetime.now().strftime("%Y%m%d")}.csv'
    )


if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    logger.info(f'GEE connected: {GEE_STATUS.get("connected")}')
    logger.info('Starting EncroWatch v2 on http://localhost:5000')
    app.run(debug=True, port=5000, threaded=True)
