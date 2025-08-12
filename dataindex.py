import csv
import io
import time
from pathlib import Path

class MaterialDataStore:
    """
    Folder layout (relative to this file):
      data/
        baseconductivity.txt
        barehardnessmin.txt
        barehardnessmax.txt
        cladhardnessmin.txt
        cladhardnessmax.txt
        correctiontables/
          tabcodes.txt
          1.txt ... 8.txt
    All files are TAB-delimited. Robust encoding: UTF-8 (with BOM) → CP1252 fallback.
    """

    def __init__(self):
        # Base folders
        self.data_dir = Path(__file__).parent / "data"
        self.corr_dir = self.data_dir / "correctiontables"

        # Fixed files
        self.f_conductivity = self.data_dir / "baseconductivity.txt"
        self.f_bare_min     = self.data_dir / "barehardnessmin.txt"
        self.f_bare_max     = self.data_dir / "barehardnessmax.txt"
        self.f_clad_min     = self.data_dir / "cladhardnessmin.txt"
        self.f_clad_max     = self.data_dir / "cladhardnessmax.txt"
        self.f_tabcodes     = self.corr_dir / "tabcodes.txt"

        # Indices
        self._cond_idx = {}   # {(SPEC, MATERIAL, TEMPER): (min, max)}
        self._bare_min = {}   # {CONCAT: [(thickness, req_str), ...]}
        self._bare_max = {}
        self._clad_min = {}
        self._clad_max = {}
        self._tabcodes = {}   # {CONCAT: {"BARE": int|None, "CLAD": int|None}}
        self._corr_tables = {}# {n: {"uncorr":[...], "thicks":[...], "grid":[[...]]}}

        # Build everything
        self._build_conductivity_index()
        self._bare_min = self._build_hardness_table(self.f_bare_min)
        self._bare_max = self._build_hardness_table(self.f_bare_max)
        self._clad_min = self._build_hardness_table(self.f_clad_min)
        self._clad_max = self._build_hardness_table(self.f_clad_max)
        self._load_tabcodes()
        self._load_correction_tables()

    # ---------- encoding-robust TSV readers ----------
    @staticmethod
    def _read_text_with_fallback(path):
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return path.read_text(encoding="cp1252")

    @staticmethod
    def _read_tsv_rows(path):
        text = MaterialDataStore._read_text_with_fallback(path)
        reader = csv.reader(io.StringIO(text), dialect=csv.excel_tab)
        return [row for row in reader]

    @staticmethod
    def _read_tsv_dicts(path):
        """
        Returns (header, rows_as_dicts). Pads/truncates row length to header length.
        Header values are preserved (original case); use .lower() when matching.
        """
        rows = MaterialDataStore._read_tsv_rows(path)
        if not rows:
            return [], []
        header = rows[0]
        L = len(header)
        dicts = []
        for r in rows[1:]:
            r = (r + [""] * L)[:L]
            dicts.append({header[i]: r[i] for i in range(L)})
        return header, dicts

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

    @staticmethod
    def _nearest_idx(values, target):
        if not values:
            return None
        best_i, best_d = 0, float("inf")
        for i, v in enumerate(values):
            d = abs(v - target)
            if d < best_d:
                best_i, best_d = i, d
        return best_i

    # ---------- conductivity ----------
    def _build_conductivity_index(self):
        header, rows = self._read_tsv_dicts(self.f_conductivity)
        cols = {c.strip().lower(): c for c in header}
        for need in ("spec", "material", "temper", "min", "max"):
            if need not in cols:
                raise ValueError(f"{self.f_conductivity.name} missing column: {need}")
        idx = {}
        for row in rows:
            spec = self._norm(row.get(cols["spec"]))
            mat  = self._norm(row.get(cols["material"]))
            temp = self._norm(row.get(cols["temper"]))
            if not (spec and mat and temp):
                continue
            mn = self._to_float(row.get(cols["min"]))
            mx = self._to_float(row.get(cols["max"]))
            idx[(spec, mat, temp)] = (mn, mx)
        self._cond_idx = idx

    # ---------- hardness (bare/clad min/max) ----------
    def _build_hardness_table(self, path):
        """
        Parses a hardness matrix:
          - header row contains many CONCAT keys (A-B-C pattern),
          - somewhere is a 'Thickness' row header,
          - numeric thickness values are in a specific column (often 2nd).
        Returns: { CONCAT_UPPER: [(thickness_float, requirement_str_or_None), ...] }
        """
        rows = self._read_tsv_rows(path)
        if not rows:
            return {}

        # header row with many concat-like keys
        header_idx = None
        for i, r in enumerate(rows[:10]):
            score = sum(1 for c in r if (c or "").count('-') >= 2)
            if score >= 5:
                header_idx = i
                break
        if header_idx is None:
            header_idx = 0

        # find "Thickness" row
        thickness_row, thickness_col = None, None
        for i, r in enumerate(rows):
            if any((c or "").strip().lower() == "thickness" for c in r):
                thickness_row = i
                break

        # detect thickness column from next row
        if thickness_row is not None and thickness_row + 1 < len(rows):
            probe = rows[thickness_row + 1]
            for ci, cell in enumerate(probe):
                s = (cell or "").strip()
                try:
                    _ = float(s)
                    if "." in s:
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

        # map concat columns from header
        header = rows[header_idx]
        concat_cols = {}
        for ci, cell in enumerate(header):
            key = (cell or "").strip()
            if key and key.count('-') >= 2:
                concat_cols[ci] = key.upper()

        # data starts after thickness row (if present), else after header
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

    # ---------- tabcodes (concat → table number per surface) ----------
    def _load_tabcodes(self):
        header, rows = self._read_tsv_dicts(self.f_tabcodes)
        cols = {c.strip().lower(): c for c in header}
        for need in ("concat", "bare", "clad"):
            if need not in cols:
                raise ValueError(f"{self.f_tabcodes.name} missing column: {need}")

        tab = {}
        for row in rows:
            concat = self._norm(row.get(cols["concat"]))

            def parse_code(x):
                s = (x or "").strip()
                if not s or s.lower().startswith("not"):
                    return None
                try:
                    return int(float(s))  # e.g., "6.0" -> 6
                except Exception:
                    return None

            tab[concat] = {
                "BARE": parse_code(row.get(cols["bare"])),
                "CLAD": parse_code(row.get(cols["clad"])),
            }
        self._tabcodes = tab

    # ---------- numbered correction tables ----------
    def _load_correction_tables(self):
        """
        n.txt (tab-delimited):
          - Row 0: header -> first cell is label; remaining are THICKNESSES
          - Col 0: uncorrected %IACS values
          - Body: corrected %IACS values
        """
        self._corr_tables = {}
        for n in range(1, 9):
            path = self.corr_dir / f"{n}.txt"
            if not path.exists():
                continue
            rows = self._read_tsv_rows(path)
            rows = [r for r in rows if any((c or "").strip() for c in r)]
            if not rows:
                continue

            header = rows[0]
            thicks = []
            for cell in header[1:]:
                t = self._to_float(cell)
                if t is not None:
                    thicks.append(t)

            uncorr = []
            grid = []
            for r in rows[1:]:
                u = self._to_float(r[0] if len(r) > 0 else "")
                if u is None:
                    continue
                row_vals = []
                for cell in r[1:1+len(thicks)]:
                    row_vals.append(self._to_float(cell))
                if len(row_vals) == len(thicks):
                    uncorr.append(u)
                    grid.append(row_vals)

            self._corr_tables[n] = {"uncorr": uncorr, "thicks": thicks, "grid": grid}

    # ---------- utilities ----------
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

    def _correct_iacs(self, table_no, base_iacs, thickness):
        T = self._corr_tables.get(table_no)
        if not T:
            return None
        unc = T["uncorr"]; ths = T["thicks"]; grid = T["grid"]
        if not unc or not ths or not grid:
            return None
        ri = self._nearest_idx(unc, base_iacs)
        ci = self._nearest_idx(ths, thickness)
        if ri is None or ci is None:
            return None
        return grid[ri][ci]

    # ---------- public ----------
    def search_all(self, spec, material, temper, thickness, surface):
        """
        Returns corrected conductivity min/max + hardness min/max (surface = "bare"|"clad").
        """
        spec_u = self._norm(spec)
        mat_u  = self._norm(material)
        temp_u = self._norm(temper)
        key_t  = (spec_u, mat_u, temp_u)

        # 1) base conductivity
        base_min, base_max = self._cond_idx.get(key_t, (None, None))

        # 2) hardness + tabcode
        concat = f"{spec_u}-{mat_u}-{temp_u}"
        if self._norm(surface) == "BARE":
            hmin_pairs = self._bare_min.get(concat, [])
            hmax_pairs = self._bare_max.get(concat, [])
            code = self._tabcodes.get(concat, {}).get("BARE")
        else:
            hmin_pairs = self._clad_min.get(concat, [])
            hmax_pairs = self._clad_max.get(concat, [])
            code = self._tabcodes.get(concat, {}).get("CLAD")

        t = float(thickness)
        hard_min = self._nearest_value(hmin_pairs, t)
        hard_max = self._nearest_value(hmax_pairs, t)

        # 3) corrected conductivity via numbered tables (if available)
        corrected_min = base_min
        corrected_max = base_max
        if code is not None:
            if base_min is not None:
                corrected_min = self._correct_iacs(code, base_min, t)
            if base_max is not None:
                corrected_max = self._correct_iacs(code, base_max, t)

        return {
            "CorrectedMin": corrected_min,
            "CorrectedMax": corrected_max,
            "HardnessMin": hard_min,
            "HardnessMax": hard_max,
        }


# Example (optional)
if __name__ == "__main__":
    DATA = MaterialDataStore()
    print(DATA.search_all("XXX3", "2024", "T8XX", 0.040, "bare"))

