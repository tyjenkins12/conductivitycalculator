import csv
from pathlib import Path

class MaterialDataStore:
    """
    Reads tab-delimited files from ./data:
      - baseconductivity.txt
      - barehardnessmin.txt, barehardnessmax.txt
      - cladhardnessmin.txt, cladhardnessmax.txt

    Call: search_all(spec, material, temper, thickness, surface="bare"|"clad")
      -> {"Min": float|None, "Max": float|None, "HardnessMin": str|None, "HardnessMax": str|None}
    """

    def __init__(self):
        self.data_dir = Path(__file__).parent / "data"
        self.f_conductivity = self.data_dir / "baseconductivity.txt"
        self.f_bare_min     = self.data_dir / "barehardnessmin.txt"
        self.f_bare_max     = self.data_dir / "barehardnessmax.txt"
        self.f_clad_min     = self.data_dir / "cladhardnessmin.txt"
        self.f_clad_max     = self.data_dir / "cladhardnessmax.txt"

        self._cond_idx = {}   # {(SPEC,MATERIAL,TEMPER): (min, max)}
        self._bare_min = {}   # {CONCAT: [(thickness, req_str), ...]}
        self._bare_max = {}
        self._clad_min = {}
        self._clad_max = {}

        self._build_conductivity_index()
        self._bare_min = self._build_hardness_table(self.f_bare_min)
        self._bare_max = self._build_hardness_table(self.f_bare_max)
        self._clad_min = self._build_hardness_table(self.f_clad_min)
        self._clad_max = self._build_hardness_table(self.f_clad_max)

    # ---------- helpers ----------
    @staticmethod
    def _norm(s):
        return (s or "").strip().upper()

    @staticmethod
    def _to_float(x):
        try:
            return float(str(x).strip())
        except Exception:
            return None

    # ---------- conductivity ----------
    def _build_conductivity_index(self):
        with self.f_conductivity.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, dialect=csv.excel_tab)
            cols = {c.strip().lower(): c for c in (reader.fieldnames or [])}
            for need in ("spec", "material", "temper", "min", "max"):
                if need not in cols:
                    raise ValueError(f"{self.f_conductivity.name} missing column: {need}")

            idx = {}
            for row in reader:
                spec = self._norm(row[cols["spec"]])
                mat  = self._norm(row[cols["material"]])
                temp = self._norm(row[cols["temper"]])
                if not (spec and mat and temp):
                    continue
                mn = self._to_float(row[cols["min"]])
                mx = self._to_float(row[cols["max"]])
                idx[(spec, mat, temp)] = (mn, mx)
            self._cond_idx = idx

    # ---------- hardness ----------
    def _build_hardness_table(self, path):
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, dialect=csv.excel_tab)
            rows = [r for r in reader]

        if not rows:
            return {}

        # Find header row with many concat-like keys (A-B-C pattern)
        header_idx = None
        for i, r in enumerate(rows[:10]):
            score = sum(1 for c in r if (c or "").count('-') >= 2)
            if score >= 5:
                header_idx = i
                break
        if header_idx is None:
            header_idx = 0

        # Find the row that literally says "Thickness"
        thickness_row, thickness_col = None, None
        for i, r in enumerate(rows):
            if any((c or "").strip().lower() == "thickness" for c in r):
                thickness_row = i
                break

        # Detect which column holds the numeric thickness values (look at next row)
        if thickness_row is not None and thickness_row + 1 < len(rows):
            probe = rows[thickness_row + 1]
            for ci, cell in enumerate(probe):
                s = (cell or "").strip()
                try:
                    _ = float(s)
                    if "." in s:  # likely a thickness like 0.040
                        thickness_col = ci
                        break
                except Exception:
                    pass
            if thickness_col is None:
                for ci, cell in enumerate(probe):
                    try:
                        float((cell or "").strip())
                        thickness_col = ci
                        break
                    except Exception:
                        pass

        # Map concat columns from header row
        header = rows[header_idx]
        concat_cols = {}
        for ci, cell in enumerate(header):
            key = (cell or "").strip()
            if key and key.count('-') >= 2:
                concat_cols[ci] = key.upper()

        # Data starts after the thickness row if found, otherwise after header
        data_start = (thickness_row + 1) if thickness_row is not None else (header_idx + 1)
        table = {k: [] for k in concat_cols.values()}

        for r in rows[data_start:]:
            if thickness_col is None or thickness_col >= len(r):
                continue
            s = (r[thickness_col] or "").strip()
            try:
                t = float(s)
            except Exception:
                continue

            for ci, concat_key in concat_cols.items():
                val = r[ci] if ci < len(r) else ""
                val = (val or "").strip()
                table[concat_key].append((t, val or None))

        for k in table:
            table[k].sort(key=lambda x: x[0])

        return table

    @staticmethod
    def _nearest_value(pairs, thickness, tol=1e-6):
        if not pairs:
            return None
        exact = [v for t, v in pairs if abs(t - thickness) <= tol]
        for v in exact:
            if v is not None:
                return v
        if exact:
            return exact[0]
        best_v, best_d = None, float("inf")
        for t, v in pairs:
            d = abs(t - thickness)
            if d < best_d:
                best_v, best_d = v, d
        return best_v

    # ---------- public ----------
    def search_all(self, spec, material, temper, thickness, surface):
        spec_u = self._norm(spec)
        mat_u  = self._norm(material)
        temp_u = self._norm(temper)
        mn, mx = self._cond_idx.get((spec_u, mat_u, temp_u), (None, None))

        concat = f"{spec_u}-{mat_u}-{temp_u}"
        if self._norm(surface) == "BARE":
            hmin_pairs = self._bare_min.get(concat, [])
            hmax_pairs = self._bare_max.get(concat, [])
        else:
            hmin_pairs = self._clad_min.get(concat, [])
            hmax_pairs = self._clad_max.get(concat, [])

        t = float(thickness)
        hmin = self._nearest_value(hmin_pairs, t)
        hmax = self._nearest_value(hmax_pairs, t)

        return {"Min": mn, "Max": mx, "HardnessMin": hmin, "HardnessMax": hmax}


# Example
if __name__ == "__main__":
    DATA = MaterialDataStore()
    print(DATA.search_all("XXX2", "6061", "T6XX", 0.10, "bare"))
