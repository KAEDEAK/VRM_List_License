import json
import struct
import argparse
import glob
import os
import csv
import urllib.parse
import shutil

# --- Localization Setup ---
def load_localization():
    """
    Loads localization messages.
    By default, messages are in English.
    If 'lang_ja_jp.json' exists, its contents will override the defaults.
    """
    DEFAULT_MESSAGES = {
        "error_parse": "[ERROR] Failed to parse {}: {}",
        "info_mapdata_created": "[INFO] mapdata.json created successfully → {}",
        "info_moving_file": "[INFO] Moving {} to {}",
        "info_moving_file_donotuse": "[INFO] Moving {} to {} (DoNotUse rule)",
        "info_sort_complete": "[INFO] File sorting complete!",
        "info_csv_saved": "[INFO] CSV file saved successfully → {}",
        "error_maptofolder_usage": "[ERROR] When using -mapToFolder, please specify either -prepare or -sortBy!",
        "argparse_description": "VRM file parsing, output & folder sorting tool!",
        "license_info_title": "=== License Information for {} (VRM {}) ===",
        # CSV header translations
        "header_file_name": "File Name",
        "header_vrm_version": "VRM Version",
        "header_model_name": "Model Name",
        "header_author": "Author",
        "header_contact": "Contact Information",
        "header_reference_url": "Reference URL",
        "header_commercial_usage": "Commercial Usage",
        "header_redistribution": "Redistribution",
        "header_credit_notation": "Credit Notation",
        "header_modification": "Modification Allowed",
        "header_avatar_permission": "Avatar Permission",
        "header_sexual_expression": "Sexual Expression",
        "header_violence_expression": "Violence Expression",
        "header_license": "License",
        "header_other_permission_url": "Other Permission URL",
        "header_other_license_url": "Other License URL"
    }
    lang_file = "lang_ja_jp.json"
    if os.path.exists(lang_file):
        try:
            with open(lang_file, "r", encoding="utf-8") as f:
                localized = json.load(f)
            # Override default messages with localized ones
            DEFAULT_MESSAGES.update(localized)
        except Exception as e:
            print(f"[WARNING] Failed to load localization file: {e}")
    return DEFAULT_MESSAGES

MESSAGES = load_localization()

# Define CSV header keys (used for both CSV header row and for retrieving values)
CSV_KEYS = [
    "file_name",
    "vrm_version",
    "model_name",
    "author",
    "contact",
    "reference_url",
    "commercial_usage",
    "redistribution",
    "credit_notation",
    "modification",
    "avatar_permission",
    "sexual_expression",
    "violence_expression",
    "license",
    "other_permission_url",
    "other_license_url"
]

CSV_HEADER = [MESSAGES.get("header_" + key, key) for key in CSV_KEYS]

# --- Utility Functions ---
def canonicalize(value):
    """
    Convert the value to a hashable form.
    If not hashable, returns its JSON string representation.
    """
    try:
        hash(value)
        return value
    except TypeError:
        return json.dumps(value, sort_keys=True, ensure_ascii=False)

def normalize_for_compare(value):
    """
    Normalize a value for comparison:
    - If it's a string, trim whitespace and lower-case it.
    - Convert "true"/"false" strings to booleans.
    - Otherwise, return as-is.
    """
    if isinstance(value, str):
        v = value.strip().lower()
        if v == "true":
            return True
        if v == "false":
            return False
        return v
    return value

# --- License Keys ---
LICENSE_KEYS = {
    # VRM 0.x keys
    "allowedUserName",
    "violentUssageName",
    "sexualUssageName",
    "commercialUssageName",
    "creditNotation",
    "modification",
    "licenseName",
    # VRM 1.0 keys
    "avatarPermission",
    "allowExcessivelyViolentUsage",
    "allowExcessivelySexualUsage",
    "commercialUsage",
    "allowRedistribution",
    "licenseUrl"
}

# --- VRM File Class ---
class VRMFile:
    def __init__(self, path):
        self.path = path
        self.data = None
        self.raw_json = None    # Raw JSON string
        self.json_data = None   # Parsed JSON
        self.vrm_version = None

    def load(self):
        """Loads the VRM file and extracts the JSON chunk."""
        try:
            with open(self.path, "rb") as f:
                self.data = f.read()

            # Check glTF header
            magic, version, total_length = struct.unpack_from("<4sII", self.data, 0)
            if magic != b'glTF':
                raise ValueError("Not a valid VRM file")
            
            # Get JSON length (offset 12)
            json_length = struct.unpack_from("<I", self.data, 12)[0]
            json_start = 20  # JSON data starts at byte 20
            json_end = json_start + json_length

            # Extract JSON data
            self.raw_json = self.data[json_start:json_end].decode("utf-8").strip()
            self.json_data = json.loads(self.raw_json)

            # Determine VRM version
            if "extensions" in self.json_data:
                if "VRM" in self.json_data["extensions"]:
                    self.vrm_version = "0.x"
                elif "VRMC_vrm" in self.json_data["extensions"]:
                    self.vrm_version = "1.0"
                else:
                    raise ValueError("VRM metadata not found")
            else:
                raise ValueError("VRM metadata not found")
            
        except Exception as e:
            print(MESSAGES["error_parse"].format(self.path, str(e)))

# --- VRM 0.x Meta Parser ---
class VRM0xMeta:
    def __init__(self, json_data, file_name):
        """Parses VRM 0.x metadata."""
        self.meta = json_data["extensions"]["VRM"]["meta"]
        self.file_name = file_name

    def get_license_info(self):
        """Retrieves license/permission info in a unified format."""
        info = {}
        info["file_name"] = self.file_name
        info["vrm_version"] = "0.x"
        info["model_name"] = self.meta.get("title", "--")
        info["author"] = self.meta.get("author", "--")
        info["contact"] = self.meta.get("contactInformation", "--")
        info["reference_url"] = self.meta.get("reference", "--")
        info["commercial_usage"] = self.meta.get("commercialUssageName", "--")
        # Extract redistribution from query parameter of otherPermissionUrl
        other_permission_url = self.meta.get("otherPermissionUrl", "")
        redistribution = "--"
        if other_permission_url:
            parsed_url = urllib.parse.urlparse(other_permission_url)
            qs = urllib.parse.parse_qs(parsed_url.query)
            redistribution = qs.get("redistribution", ["--"])[0]
        info["redistribution"] = redistribution
        info["credit_notation"] = self.meta.get("creditNotation", "--")
        info["modification"] = self.meta.get("modification", "--")
        info["avatar_permission"] = self.meta.get("allowedUserName", "--")
        info["sexual_expression"] = self.meta.get("sexualUssageName", "--")
        info["violence_expression"] = self.meta.get("violentUssageName", "--")
        info["license"] = self.meta.get("licenseName", "--")
        info["other_permission_url"] = self.meta.get("otherPermissionUrl", "--")
        info["other_license_url"] = self.meta.get("otherLicenseUrl", "--")
        return info

# --- VRM 1.0 Meta Parser ---
class VRM1Meta:
    def __init__(self, json_data, file_name):
        """Parses VRM 1.0 metadata."""
        self.meta = json_data["extensions"]["VRMC_vrm"]["meta"]
        self.file_name = file_name

    def get_license_info(self):
        """Retrieves license/permission info in a unified format."""
        info = {}
        info["file_name"] = self.file_name
        info["vrm_version"] = "1.0"
        info["model_name"] = self.meta.get("name", "--")
        authors = self.meta.get("authors", ["--"])
        info["author"] = ", ".join(authors)
        info["contact"] = "--"
        info["reference_url"] = "--"
        info["commercial_usage"] = self.meta.get("commercialUsage", "--")
        allow_redist = self.meta.get("allowRedistribution", None)
        if allow_redist is None:
            info["redistribution"] = "--"
        else:
            info["redistribution"] = "Allowed" if allow_redist else "Not allowed"
        info["credit_notation"] = self.meta.get("creditNotation", "--")
        info["modification"] = self.meta.get("modification", "--")
        info["avatar_permission"] = self.meta.get("avatarPermission", "--")
        sexual_usage = self.meta.get("allowExcessivelySexualUsage", None)
        if sexual_usage is None:
            info["sexual_expression"] = "--"
        else:
            info["sexual_expression"] = "Allowed" if sexual_usage else "Not allowed"
        violent_usage = self.meta.get("allowExcessivelyViolentUsage", None)
        if violent_usage is None:
            info["violence_expression"] = "--"
        else:
            info["violence_expression"] = "Allowed" if violent_usage else "Not allowed"
        info["license"] = self.meta.get("licenseUrl", "--")
        info["other_permission_url"] = "--"
        info["other_license_url"] = "--"
        return info

# --- VRM Parser ---
class VRMParser:
    @staticmethod
    def parse(vrm_file):
        """Parses metadata using the appropriate parser."""
        if vrm_file.vrm_version == "0.x":
            return VRM0xMeta(vrm_file.json_data, os.path.basename(vrm_file.path)).get_license_info()
        elif vrm_file.vrm_version == "1.0":
            return VRM1Meta(vrm_file.json_data, os.path.basename(vrm_file.path)).get_license_info()
        return None

# --- mapdata.json Preparation (Preparation Mode) ---
def prepare_mapdata(file_list, mapdata_filename):
    """
    Collects all unique key-value pairs for license/permission metadata
    from the provided VRM files and writes them to mapdata.json under 'unsort.target'.
    """
    # Collect values for each key in a set
    value_dict = {}
    for filepath in file_list:
        vrm = VRMFile(filepath)
        vrm.load()
        if vrm.json_data:
            if vrm.vrm_version == "0.x":
                meta = vrm.json_data.get("extensions", {}).get("VRM", {}).get("meta", {})
            elif vrm.vrm_version == "1.0":
                meta = vrm.json_data.get("extensions", {}).get("VRMC_vrm", {}).get("meta", {})
            for key, value in meta.items():
                if key not in LICENSE_KEYS:
                    continue
                if value is None or value == "":
                    continue
                norm_val = canonicalize(value)
                if key in value_dict:
                    value_dict[key].add(norm_val)
                else:
                    value_dict[key] = {norm_val}
    # Convert sets to list or single value
    unsort_target = {}
    for key, val_set in value_dict.items():
        val_list = list(val_set)
        if len(val_list) == 1:
            unsort_target[key] = val_list[0]
        else:
            unsort_target[key] = val_list

    mapdata = {
        "mapdata": {
            "unsort": {
                "target": unsort_target
            },
            "sorted": [
                {
                    "directory": "folder-1",
                    "target": {}  # User-defined conditions
                },
                {
                    "directory": "folder-2",
                    "target": {}
                },
                {
                    "directory": "DoNotUse",
                    "target": {}
                }
            ]
        }
    }
    with open(mapdata_filename, "w", encoding="utf-8") as f:
        json.dump(mapdata, f, ensure_ascii=False, indent=4)
    print(MESSAGES["info_mapdata_created"].format(mapdata_filename))

# --- File Sorting Based on mapdata.json (Sort Mode) ---
def sort_files_by_mapdata(file_list, mapdata_filename):
    with open(mapdata_filename, "r", encoding="utf-8") as f:
        mapdata = json.load(f)
    sorted_mappings = mapdata.get("mapdata", {}).get("sorted", [])

    # Separate DoNotUse mapping from normal mappings
    donotuse_mapping = None
    normal_mappings = []
    for mapping in sorted_mappings:
        target_dict = mapping.get("target", {})
        if mapping.get("directory") == "DoNotUse" and not target_dict:
            donotuse_mapping = mapping
        else:
            normal_mappings.append(mapping)

    for filepath in file_list:
        vrm = VRMFile(filepath)
        vrm.load()
        if not (vrm.json_data and vrm.vrm_version in ("0.x", "1.0")):
            continue
        if vrm.vrm_version == "0.x":
            meta = vrm.json_data.get("extensions", {}).get("VRM", {}).get("meta", {})
        elif vrm.vrm_version == "1.0":
            meta = vrm.json_data.get("extensions", {}).get("VRMC_vrm", {}).get("meta", {})

        moved = False
        # Evaluate each mapping (all target conditions must match)
        for mapping in normal_mappings:
            target_dict = mapping.get("target", {})
            if not target_dict:
                continue
            evaluated_keys = 0  # Number of keys present in file metadata that are in mapping target
            all_match = True
            for key, mapping_value in target_dict.items():
                if key in meta:
                    evaluated_keys += 1
                    file_value = meta[key]
                    if file_value is None:
                        all_match = False
                        break
                    norm_file_val = normalize_for_compare(file_value)
                    # If mapping_value is a list, check if any matches (OR condition)
                    if isinstance(mapping_value, list):
                        norm_mapping_vals = [normalize_for_compare(x) for x in mapping_value]
                        if norm_file_val not in norm_mapping_vals:
                            all_match = False
                            break
                    else:
                        if norm_file_val != normalize_for_compare(mapping_value):
                            all_match = False
                            break
            # If none of the keys in mapping target exist in file metadata, condition fails
            if evaluated_keys == 0:
                all_match = False
            if all_match:
                target_dir = mapping.get("directory")
                if target_dir:
                    if not os.path.exists(target_dir):
                        os.makedirs(target_dir, exist_ok=True)
                    basename = os.path.basename(filepath)
                    target_path = os.path.join(target_dir, basename)
                    print(MESSAGES["info_moving_file"].format(basename, target_dir))
                    shutil.move(filepath, target_path)
                    moved = True
                    break
        # If no mapping matched and DoNotUse mapping exists, move file there
        if not moved and donotuse_mapping:
            target_dir = donotuse_mapping.get("directory")
            if target_dir:
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir, exist_ok=True)
                basename = os.path.basename(filepath)
                target_path = os.path.join(target_dir, basename)
                print(MESSAGES["info_moving_file_donotuse"].format(basename, target_dir))
                shutil.move(filepath, target_path)
    print(MESSAGES["info_sort_complete"])

# --- Main Processing ---
def main():
    parser = argparse.ArgumentParser(
        description=MESSAGES["argparse_description"]
    )
    parser.add_argument("-path", type=str, required=True, help="Path to VRM files (wildcards allowed)")
    parser.add_argument("-json", action="store_true", help="Output raw VRM JSON data (files array)")
    parser.add_argument("-output", type=str, required=False, help="CSV output file")
    parser.add_argument("-mapToFolder", action="store_true", help="Execute folder sorting function")
    parser.add_argument("-prepare", type=str, help="Create mapdata.json (preparation mode)")
    parser.add_argument("-sortBy", type=str, help="Sort files based on mapdata.json")
    args = parser.parse_args()

    file_list = glob.glob(args.path, recursive=True)

    # Folder sorting mode
    if args.mapToFolder:
        if args.prepare:
            prepare_mapdata(file_list, args.prepare)
        elif args.sortBy:
            sort_files_by_mapdata(file_list, args.sortBy)
        else:
            print(MESSAGES["error_maptofolder_usage"])
        return

    # -json option: output raw JSON data
    if args.json:
        files_data = []
        for vrm_file in file_list:
            vrm = VRMFile(vrm_file)
            vrm.load()
            if vrm.json_data:
                files_data.append({
                    "filename": os.path.basename(vrm_file),
                    "metadata": vrm.json_data
                })
        print(json.dumps({"files": files_data}, ensure_ascii=False))
    
    # CSV output mode
    elif args.output:
        with open(args.output, "w", newline="", encoding="utf-8-sig") as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(CSV_HEADER)
            for vrm_file in file_list:
                vrm = VRMFile(vrm_file)
                vrm.load()
                license_info = VRMParser.parse(vrm)
                if license_info:
                    row = [license_info.get(key, "--") for key in CSV_KEYS]
                    csv_writer.writerow(row)
        print(MESSAGES["info_csv_saved"].format(args.output))
    
    # Default: display license information
    else:
        for vrm_file in file_list:
            vrm = VRMFile(vrm_file)
            vrm.load()
            license_info = VRMParser.parse(vrm)
            if license_info:
                print("\n" + MESSAGES["license_info_title"].format(license_info["file_name"], license_info["vrm_version"]))
                for key in CSV_KEYS:
                    header = MESSAGES.get("header_" + key, key)
                    print(f"{header:20}: {license_info.get(key, '--')}")

if __name__ == "__main__":
    main()
