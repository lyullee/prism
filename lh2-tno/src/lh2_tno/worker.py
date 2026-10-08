"""JSON worker. The calling process alone supplies explicit source pins."""
from __future__ import annotations
from dataclasses import asdict
import contextlib
import hashlib
import importlib
import importlib.metadata
import json
import math
from pathlib import Path
import sys


def module(name, root):
    mod=importlib.import_module(name)
    if not Path(mod.__file__).resolve().is_relative_to(root):
        raise ValueError(f"unexpected import origin: {name}")
    return mod


def run(request):
    for name,version in request["required_versions"].items():
        if importlib.metadata.version(name)!=version:
            raise ValueError(f"dependency version mismatch: {name}")
    roots={p["name"]:Path(p["root"]).resolve() for p in request["packages"]}
    # Preserve declared precedence. Putting site-packages first would hide a
    # pinned standalone source tree behind another installed pool version.
    for name,root in reversed(tuple(roots.items())):
        sys.path.insert(0,str(root if name=="tno" else root.parent))
    p=request["payload"]; operation=request["operation"]
    if operation=="consequence_chain":
        from chain_worker import run_chain
        return run_chain(p,roots,module)
    if operation=="integrated_source":
        m=module("slabx_lh2.integrated_lh2_source",roots["slabx_lh2"])
        duration=p["duration_s"]; dt=p["time_step_s"]
        if not 0<dt<=duration<=3600 or duration/dt>2000:
            raise ValueError("invalid source horizon or computation budget")
        inp=m.IntegratedSourceInput(m.TankState(**p["tank"]),tuple(m.PipeSection(**x) for x in p["pipe_sections"]),
              m.NozzleGeometry(**p["nozzle"]),m.AmbientState(**p["ambient"]),m.ModelChoices(**p["choices"]),duration,dt)
        data=asdict(m.evaluate_integrated_lh2_source(inp))
        # These residuals are latent-evaporation accounting, not total-energy closure.
        return {"data":data,"energy_balance_scope":"latent_evaporation_accounting_only",
                "limitation":"upstream transient/source model assumptions retained; downstream dispersion not computed"}
    if operation=="vent_stack":
        props=module("lh2dt.properties",roots["lh2dt"])
        m=module("lh2dt.vent_stack",roots["lh2dt"])
        fluid=props.HydrogenProperties(p["fluid"])
        left=fluid.from_pT(**p["upstream"]); right=fluid.from_pT(**p["downstream"])
        stack=m.VentStack(**p["stack"],properties=fluid)
        hydraulic=stack.evaluate(left,right)
        outlet=fluid.from_ph(right.pressure_Pa,hydraulic.outlet_specific_enthalpy_J_kg)
        residual=hydraulic.mass_flow_kg_s*(outlet.specific_enthalpy_J_kg-left.specific_enthalpy_J_kg)-hydraulic.heat_into_fluid_W
        return {"data":{"hydraulic":asdict(hydraulic),"outlet":asdict(outlet),"energy_residual_w":residual},
                "limitation":"steady stack component; tank/PSV transient not computed"}
    if operation=="declared_pool":
        m=module("dynamiclh2poolx",roots["dynamiclh2poolx"])
        if p["inflow_origin"] not in {"synthetic_declared_ground", "reviewed_ground_measurement"}:
            raise ValueError("explicit ground deposition origin required")
        times=p["output_times_s"]
        if not times or times[-1]>120 or len(times)>500:
            raise ValueError("pool computation budget exceeded")
        surface=m.SolidSemiInfiniteSurface(**p["surface"])
        numerics=m.ShallowLayerNumerics(**p["numerics"])
        inflow=m.DeclaredInflow(tuple(p["inflow_times_s"]),tuple(p["inflow_rates_kg_s"]))
        result=m.run_dynamic_pool(m.DynamicPoolConfig(surface=surface,numerics=numerics),inflow,tuple(times))
        return {"data":result.to_dict(),"limitation":"declared ground inflow only; jet deposition/footprint not inferred",
                "inflow_origin":p["inflow_origin"]}
    if operation=="assurance":
        pa=module("physics_assurance",roots["tno"]); er=module("evidence_registry",roots["tno"])
        outputs=[]
        for row in p["outputs"]:
            row=dict(row); row["status"]=pa.EvidenceStatus(row["status"])
            for name in ["evidence_ids","conditions","warnings","shared_limitations"]:
                row[name]=tuple(row.get(name,[]))
            if row.get("interval") is not None: row["interval"]=tuple(row["interval"])
            outputs.append(pa.ComponentOutput(**row))
        records=[]
        for row in p["records"]:
            row=dict(row); row["use"]=er.EvidenceUse(row["use"]); row["replay"]=er.ReplayLevel(row["replay"])
            row["maximum_status"]=pa.EvidenceStatus(row["maximum_status"])
            row["artifacts"]=tuple(er.Artifact(**x) for x in row["artifacts"])
            row["conditions"]=tuple(row.get("conditions",[]))
            records.append(er.EvidenceRecord(**row))
        result=er.assess_registered_outputs(tuple(outputs),er.EvidenceRegistry(tuple(records)))
        return {"data":asdict(result),"limitation":"metadata qualification does not establish physical accuracy"}
    if operation=="thermal_damage":
        m=module("risk",roots["tno"])
        flux=p["equivalent_heat_flux_w_m2"]; duration=p["exposure_s"]
        if not math.isfinite(flux) or flux<0 or not math.isfinite(duration) or duration<=0:
            raise ValueError("nonnegative flux and positive duration required")
        probit=None if flux==0 else m.ThermalProbit().probit(flux,duration)
        return {"data":{"harm_probability":0 if flux==0 else m.probit_to_probability(probit),"probit":probit},
                "limitation":"TNO damage transformation only; input radiation and exposure require independent validation"}
    raise ValueError("unsupported operation")


if __name__=="__main__":
    try:
        request=json.load(sys.stdin)
        with contextlib.redirect_stdout(sys.stderr): result=run(request)
        versions={name:importlib.metadata.version(name) for name in request["required_versions"]}
        print(json.dumps({"ok":True,**result,"environment":{"python":sys.version,"dependencies":versions}},ensure_ascii=False,allow_nan=False))
    except Exception as e:
        print(json.dumps({"ok":False,"error":f"{type(e).__name__}: {e}"},ensure_ascii=False))
