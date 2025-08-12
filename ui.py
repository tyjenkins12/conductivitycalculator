# ui.py
import tkinter as tk
from tkinter import ttk, messagebox
from dataindex import MaterialDataStore

# --------------------- data layer ---------------------
DATA = MaterialDataStore()

def list_specs():
    return sorted({spec for (spec, mat, temp) in DATA._cond_idx})

def list_materials(spec):
    su = (spec or "").strip().upper()
    return sorted({mat for (sp, mat, temp) in DATA._cond_idx if sp == su})

def list_tempers(spec, material):
    su = (spec or "").strip().upper()
    mu = (material or "").strip().upper()
    return sorted({temp for (sp, mat, temp) in DATA._cond_idx if sp == su and mat == mu})

def list_thicknesses(spec, material, temper, surface):
    su = (spec or "").strip().upper()
    mu = (material or "").strip().upper()
    tu = (temper or "").strip().upper()
    concat = f"{su}-{mu}-{tu}"
    if (surface or "").strip().upper() == "BARE":
        pairs_min = DATA._bare_min.get(concat, [])
        pairs_max = DATA._bare_max.get(concat, [])
    else:
        pairs_min = DATA._clad_min.get(concat, [])
        pairs_max = DATA._clad_max.get(concat, [])
    th = {t for t, _ in pairs_min} | {t for t, _ in pairs_max}
    return sorted(th)

# --------------------- UI layer ---------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Conductivity & Hardness Calculator")
        self.geometry("700x420")
        self.resizable(False, False)

        pad = {"padx": 10, "pady": 6}

        # Inputs
        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=14, pady=14)

        ttk.Label(frm, text="Spec").grid(row=0, column=0, sticky="w", **pad)
        self.cmb_spec = ttk.Combobox(frm, state="readonly", values=list_specs())
        self.cmb_spec.grid(row=0, column=1, **pad)

        ttk.Label(frm, text="Material").grid(row=0, column=2, sticky="w", **pad)
        self.cmb_material = ttk.Combobox(frm, state="readonly")
        self.cmb_material.grid(row=0, column=3, **pad)

        ttk.Label(frm, text="Temper").grid(row=1, column=0, sticky="w", **pad)
        self.cmb_temper = ttk.Combobox(frm, state="readonly")
        self.cmb_temper.grid(row=1, column=1, **pad)

        ttk.Label(frm, text="Surface").grid(row=1, column=2, sticky="w", **pad)
        self.cmb_surface = ttk.Combobox(frm, state="readonly", values=["BARE", "CLAD"])
        self.cmb_surface.grid(row=1, column=3, **pad)

        ttk.Label(frm, text="Thickness (in)").grid(row=2, column=0, sticky="w", **pad)
        self.cmb_thickness = ttk.Combobox(frm, state="readonly")
        self.cmb_thickness.grid(row=2, column=1, **pad)

        # Buttons
        btns = ttk.Frame(self)
        btns.pack(fill="x")
        self.btn_calc = ttk.Button(btns, text="Calculate", command=self.on_calculate)
        self.btn_calc.pack(side="left", padx=14, pady=6)
        self.btn_reset = ttk.Button(btns, text="Reset", command=self.on_reset)
        self.btn_reset.pack(side="left", padx=6, pady=6)

        # Output
        out = ttk.LabelFrame(self, text="Results")
        out.pack(fill="both", expand=True, padx=14, pady=8)

        self.var_corr_min = tk.StringVar()
        self.var_corr_max = tk.StringVar()
        self.var_hard_min = tk.StringVar()
        self.var_hard_max = tk.StringVar()

        row = 0
        ttk.Label(out, text="Corrected Min %IACS:").grid(row=row, column=0, sticky="w", padx=12, pady=8)
        ttk.Label(out, textvariable=self.var_corr_min).grid(row=row, column=1, sticky="w", padx=12, pady=8)
        row += 1

        ttk.Label(out, text="Corrected Max %IACS:").grid(row=row, column=0, sticky="w", padx=12, pady=8)
        ttk.Label(out, textvariable=self.var_corr_max).grid(row=row, column=1, sticky="w", padx=12, pady=8)
        row += 1

        ttk.Label(out, text="Hardness Min:").grid(row=row, column=0, sticky="w", padx=12, pady=8)
        ttk.Label(out, textvariable=self.var_hard_min).grid(row=row, column=1, sticky="w", padx=12, pady=8)
        row += 1

        ttk.Label(out, text="Hardness Max:").grid(row=row, column=0, sticky="w", padx=12, pady=8)
        ttk.Label(out, textvariable=self.var_hard_max).grid(row=row, column=1, sticky="w", padx=12, pady=8)

        # Wiring: cascading dropdown updates
        self.cmb_spec.bind("<<ComboboxSelected>>", self.on_spec_changed)
        self.cmb_material.bind("<<ComboboxSelected>>", self.on_material_changed)
        self.cmb_temper.bind("<<ComboboxSelected>>", self.on_temper_or_surface_changed)
        self.cmb_surface.bind("<<ComboboxSelected>>", self.on_temper_or_surface_changed)

        # Preselect first spec if any
        if self.cmb_spec["values"]:
            self.cmb_spec.current(0)
            self.on_spec_changed()

    # --- events ---
    def on_spec_changed(self, *_):
        spec = self.cmb_spec.get()
        mats = list_materials(spec)
        self.cmb_material["values"] = mats
        self.cmb_material.set("")
        self.cmb_temper.set("")
        self.cmb_thickness.set("")
        self.cmb_temper["values"] = []
        self.cmb_thickness["values"] = []
        if mats:
            self.cmb_material.current(0)
            self.on_material_changed()

    def on_material_changed(self, *_):
        spec = self.cmb_spec.get()
        mat = self.cmb_material.get()
        temps = list_tempers(spec, mat)
        self.cmb_temper["values"] = temps
        self.cmb_temper.set("")
        self.cmb_thickness.set("")
        self.cmb_thickness["values"] = []
        if temps:
            self.cmb_temper.current(0)
            self.on_temper_or_surface_changed()

    def on_temper_or_surface_changed(self, *_):
        spec = self.cmb_spec.get()
        mat = self.cmb_material.get()
        temp = self.cmb_temper.get()
        surf = self.cmb_surface.get() or "BARE"
        thicks = list_thicknesses(spec, mat, temp, surf)
        # format as strings with up to 4 decimals to look nice
        disp = [("{:.4f}".format(t).rstrip("0").rstrip(".") if isinstance(t, float) else str(t)) for t in thicks]
        self.cmb_thickness["values"] = disp
        self.cmb_thickness.set("" if not disp else disp[0])

    def on_calculate(self):
        spec = self.cmb_spec.get().strip()
        mat = self.cmb_material.get().strip()
        temp = self.cmb_temper.get().strip()
        surf = (self.cmb_surface.get() or "BARE").strip().upper()
        th_s = self.cmb_thickness.get().strip()

        if not (spec and mat and temp and th_s and surf):
            messagebox.showwarning("Missing input", "Please select all fields.")
            return

        try:
            thickness = float(th_s)
        except ValueError:
            messagebox.showerror("Invalid thickness", f"Cannot parse thickness: {th_s}")
            return

        result = DATA.search_all(spec, mat, temp, thickness, surf)
        self.var_corr_min.set("" if result["CorrectedMin"] is None else f"{result['CorrectedMin']:.2f}")
        self.var_corr_max.set("" if result["CorrectedMax"] is None else f"{result['CorrectedMax']:.2f}")
        self.var_hard_min.set(result["HardnessMin"] or "")
        self.var_hard_max.set(result["HardnessMax"] or "")

    def on_reset(self):
        self.cmb_spec.set("")
        self.cmb_material.set("")
        self.cmb_temper.set("")
        self.cmb_surface.set("")
        self.cmb_thickness.set("")
        self.cmb_material["values"] = []
        self.cmb_temper["values"] = []
        self.cmb_thickness["values"] = []
        self.var_corr_min.set("")
        self.var_corr_max.set("")
        self.var_hard_min.set("")
        self.var_hard_max.set("")

if __name__ == "__main__":
    App().mainloop()
