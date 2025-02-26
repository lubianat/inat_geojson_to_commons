import json
import requests
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

def compute_center(geometry):
    """
    Compute a simple center coordinate from a GeoJSON geometry.
    For Polygon or MultiPolygon types, returns the first coordinate.
    (For a more accurate centroid, consider using a geospatial library.)
    """
    try:
        if geometry['type'] == 'MultiPolygon':
            lon, lat = geometry['coordinates'][0][0][0]
            return lat, lon
        elif geometry['type'] == 'Polygon':
            lon, lat = geometry['coordinates'][0][0]
            return lat, lon
    except Exception:
        pass
    return 0.0, 0.0

from wdcuration import get_statement_values
def get_inat_id_from_wikidata(qid):
    id = get_statement_values(qid, "P3151")
    return id[0]

def fetch_geojson(inat_id):
    """Fetch the GeoJSON from inaturalist-open-data S3 using the given taxon id."""
    geojson_url = f"https://inaturalist-open-data.s3.us-east-1.amazonaws.com/geomodel/geojsons/latest/{inat_id}.geojson"
    r = requests.get(geojson_url, timeout=10)
    if r.ok:
        try:
            return r.json()
        except Exception:
            return None
    return None

# Homepage HTML using Bootstrap and jQuery UI for autocomplete.
HTML_FORM = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>iNat to Wikimedia .map Converter</title>
    <!-- Bootstrap CSS -->
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
    <!-- jQuery UI CSS -->
    <link rel="stylesheet" href="https://code.jquery.com/ui/1.12.1/themes/base/jquery-ui.css">
  </head>
  <body class="container mt-5">
    <h1 class="mb-4">iNat to Wikimedia .map Converter</h1>
    <div class="card mb-4">
      <div class="card-header">
        Enter a Taxon Identifier
      </div>
      <div class="card-body">
        <form method="post" action="/fetch">
          <div class="form-group">
            <label for="identifier">Taxon Identifier (iNaturalist id or Wikidata QID):</label>
            <input type="text" class="form-control" id="identifier" name="identifier" placeholder="e.g., 18808 or Q18808" required>
          </div>
          <button type="submit" class="btn btn-primary">Fetch and Convert</button>
        </form>
      </div>
    </div>
    <div class="card">
      <div class="card-header">
        Or Upload a File
      </div>
      <div class="card-body">
        <form method="post" action="/upload" enctype="multipart/form-data">
          <div class="form-group">
            <label for="file">Select a .geojson or .map file:</label>
            <input type="file" class="form-control-file" id="file" name="file" accept=".geojson,.map" required>
          </div>
          <button type="submit" class="btn btn-primary">Upload and Convert</button>
        </form>
      </div>
    </div>
    <!-- jQuery, jQuery UI, and Bootstrap JS -->
    <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
    <script src="https://code.jquery.com/ui/1.12.1/jquery-ui.js"></script>
    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.bundle.min.js"></script>
    <script>
      $(function() {
        $("#identifier").autocomplete({
          source: function(request, response) {
            $.ajax({
              url: "https://www.wikidata.org/w/api.php",
              dataType: "jsonp",
              data: {
                action: "wbsearchentities",
                format: "json",
                language: "en",
                search: request.term
              },
              success: function(data) {
                response($.map(data.search, function(item) {
                  return {
                    label: item.label + " (" + item.id + ")",
                    value: item.id
                  };
                }));
              }
            });
          },
          minLength: 2
        });
      });
    </script>
  </body>
</html>
"""

# Output page template with Bootstrap styling. Category line removed.
OUTPUT_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Converted Wikimedia .map</title>
    <!-- Bootstrap CSS -->
    <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
    <style>
      textarea {
        width: 100%;
        height: 400px;
      }
      .copy-btn {
        padding: 10px 20px;
        font-size: 16px;
        margin-top: 10px;
      }
    </style>
  </head>
  <body class="container mt-5">
    <h1>Wikimedia‑Ready JSON</h1>
    <p><strong>License:</strong> CC‑BY‑4.0+</p>
    <textarea id="jsonOutput" readonly>{{ json_output }}</textarea>
    <br>
    <button class="copy-btn btn btn-secondary" onclick="copyJSON()">Copy JSON</button>
    <br><br>
    <p>
      Submit to Wikimedia Commons: 
      <a href="{{ commons_link }}" target="_blank" class="btn btn-primary">Submit File</a>
    </p>
    <script>
      function copyJSON() {
        var copyText = document.getElementById("jsonOutput");
        copyText.select();
        copyText.setSelectionRange(0, 99999);
        navigator.clipboard.writeText(copyText.value);
        alert("JSON copied to clipboard!");
      }
    </script>
  </body>
</html>
"""

@app.route('/', methods=['GET'])
def index():
    return render_template_string(HTML_FORM)

@app.route('/fetch', methods=['POST'])
def fetch_by_id():
    identifier = request.form.get("identifier", "").strip()
    if not identifier:
        return jsonify({"error": "No identifier provided"}), 400

    # Determine if identifier is a Wikidata QID (starts with "Q") or an iNaturalist id.
    if identifier.upper().startswith("Q"):
        inat_id = get_inat_id_from_wikidata(identifier.upper())
        if not inat_id:
            return jsonify({"error": "Could not retrieve an iNaturalist taxon id from the Wikidata QID"}), 400
    else:
        inat_id = identifier

    geojson_data = fetch_geojson(inat_id)
    if not geojson_data:
        return jsonify({"error": "Failed to fetch or parse GeoJSON data for the given taxon id"}), 400

    # Process the GeoJSON as Feature or FeatureCollection.
    if geojson_data.get("type") == "Feature":
        features = [geojson_data]
    elif geojson_data.get("type") == "FeatureCollection":
        features = geojson_data.get("features", [])
    else:
        return jsonify({"error": "GeoJSON data is not a Feature or FeatureCollection"}), 400

    # Use the first feature for metadata and attempt to get species name via iNaturalist API.
    taxon_id = inat_id
    species_name = None
    if features:
        first_feature = features[0]
        geometry = first_feature.get("geometry", {})
        lat, lon = compute_center(geometry)
        try:
            url = f"https://api.inaturalist.org/v1/taxa/{taxon_id}"
            response = requests.get(url, timeout=10)
            if response.ok:
                data = response.json()
                if data.get("results"):
                    species_name = data["results"][0].get("name")
        except Exception:
            species_name = None
        if not species_name:
            species_name = first_feature.get("properties", {}).get("name", "Unknown")
    else:
        lat, lon = 0.0, 0.0
        species_name = "Unknown"

    wikimedia_map = {
        "license": "CC-BY-4.0+",
        "description": {
            "en": f"Distribution map of {species_name}",
            "de": f"Verbreitungskarte von {species_name}",
            "ja": f"{species_name} の分布図",
            "zh": f"{species_name} 分布图"
        },
        "sources": f"https://www.inaturalist.org/pages/range_maps, https://www.inaturalist.org/geo_model/{taxon_id}/explain",
        "zoom": 5,
        "latitude": lat,
        "longitude": lon,
        "data": {
            "type": "FeatureCollection",
            "features": features
        }
    }

    safe_species = species_name.replace(" ", "_")
    commons_filename = f"{safe_species}_iNat_2025.map"
    commons_link = f"https://commons.wikimedia.org/w/index.php?title=Data:{commons_filename}&action=submit"

    return render_template_string(OUTPUT_TEMPLATE, json_output=json.dumps(wikimedia_map, indent=2), commons_link=commons_link)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['file']
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        file_content = file.read().decode('utf-8')
        input_data = json.loads(file_content)
    except Exception as e:
        return jsonify({"error": f"Failed to read/parse file: {str(e)}"}), 400

    if input_data.get("type") == "Feature":
        features = [input_data]
    elif input_data.get("type") == "FeatureCollection":
        features = input_data.get("features", [])
    else:
        return jsonify({"error": "Input file must be a GeoJSON Feature or FeatureCollection"}), 400

    taxon_id = None
    species_name = None
    if features:
        first_feature = features[0]
        geometry = first_feature.get("geometry", {})
        lat, lon = compute_center(geometry)
        taxon_id = first_feature.get("properties", {}).get("taxon_id")
        if taxon_id:
            try:
                url = f"https://api.inaturalist.org/v1/taxa/{taxon_id}"
                response = requests.get(url, timeout=10)
                if response.ok:
                    data = response.json()
                    if data.get("results"):
                        species_name = data["results"][0].get("name")
            except Exception:
                species_name = None
        if not species_name:
            species_name = first_feature.get("properties", {}).get("name", "Unknown")
    else:
        lat, lon = 0.0, 0.0
        species_name = "Unknown"

    wikimedia_map = {
        "license": "CC-BY-4.0+",
        "description": {
            "en": f"Distribution map of {species_name}",
            "de": f"Verbreitungskarte von {species_name}",
            "ja": f"{species_name} の分布図",
            "zh": f"{species_name} 分布图"
        },
        "sources": f"https://www.inaturalist.org/pages/range_maps, https://www.inaturalist.org/geo_model/{taxon_id if taxon_id else '18808'}/explain",
        "zoom": 5,
        "latitude": lat,
        "longitude": lon,
        "data": {
            "type": "FeatureCollection",
            "features": features
        }
    }

    safe_species = species_name.replace(" ", "_")
    commons_filename = f"{safe_species}_iNat_2025.map"
    commons_link = f"https://commons.wikimedia.org/w/index.php?title=Data:{commons_filename}&action=submit"

    return render_template_string(OUTPUT_TEMPLATE, json_output=json.dumps(wikimedia_map, indent=2), commons_link=commons_link)

if __name__ == '__main__':
    app.run(debug=True)
