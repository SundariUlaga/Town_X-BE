"""Transform india-village-finder Tamil Nadu release data into API-ready JSON.

Source: https://github.com/mchittineni/india-village-finder (LGD / GODL-India)
Run after downloading tamil_nadu_data.zip into scripts/_source/tamil_nadu/
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = Path(__file__).resolve().parent / "_source" / "tamil_nadu" / "web" / "data"
OUTPUT_DIR = ROOT / "app" / "data" / "tamil_nadu"


def main() -> None:
    regions_path = SOURCE_DIR / "regions.json"
    villages_path = SOURCE_DIR / "villages.json"

    if not regions_path.exists():
        raise SystemExit(
            f"Missing source data at {regions_path}. "
            "Download tamil_nadu_data.zip from "
            "https://github.com/mchittineni/india-village-finder/releases "
            "and extract to scripts/_source/"
        )

    regions = json.loads(regions_path.read_text(encoding="utf-8"))
    villages_blob = json.loads(villages_path.read_text(encoding="utf-8"))

    districts = [
        {"id": d["c"], "name": d["n"], "code": d["c"]}
        for d in regions["districts"]
    ]
    district_code_by_index = {d["i"]: d["c"] for d in regions["districts"]}

    taluks = [
        {
            "id": m["c"],
            "name": m["n"],
            "code": m["c"],
            "district_id": district_code_by_index[m["d"]],
        }
        for m in regions["mandals"]
    ]
    taluk_code_by_index = {m["i"]: m["c"] for m in regions["mandals"]}

    villages = []
    for row in villages_blob["rows"]:
        name, mandal_index, village_code, _category, pincode = row
        taluk_id = taluk_code_by_index[mandal_index]
        villages.append(
            {
                "id": village_code,
                "name": name,
                "code": village_code,
                "taluk_id": taluk_id,
                "pincode": pincode or None,
            }
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "districts.json").write_text(
        json.dumps(districts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / "taluks.json").write_text(
        json.dumps(taluks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / "villages.json").write_text(
        json.dumps(villages, ensure_ascii=False), encoding="utf-8"
    )

    meta = {
        "state": regions.get("state", "Tamil Nadu"),
        "state_code": regions.get("state_code"),
        "source": "india-village-finder / LGD (GODL-India)",
        "district_count": len(districts),
        "taluk_count": len(taluks),
        "village_count": len(villages),
    }
    (OUTPUT_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Wrote {len(districts)} districts, {len(taluks)} taluks, {len(villages)} villages -> {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
