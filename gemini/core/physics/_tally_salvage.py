"""Build erosion flow-path segments from well tally and ESP geometry."""

import math

INCH_TO_M = 0.0254

DEFAULT_ESP_COMPONENT_TYPES = (
    "intake",
    "pump",
    "seal",
    "protector",
    "motor",
)


def inch_to_m(value_inch):
    """Convert inches to meters."""
    return float(value_inch) * INCH_TO_M


def annulus_id_m(outer_id_m, inner_od_m):
    """Effective annulus flow diameter [m] from outer ID and inner OD."""
    outer_id_m = float(outer_id_m)
    inner_od_m = float(inner_od_m)
    if inner_od_m >= outer_id_m:
        return 0.0
    return math.sqrt(outer_id_m**2 - inner_od_m**2)


def flow_cross_section_area_m2(
    flow_area_type,
    flow_diameter_m,
    outer_id_m=None,
    inner_od_m=None,
):
    """Flow cross-section area [m2] for circle (tubing ID) or annulus."""
    if flow_area_type == "annulus" and outer_id_m is not None and inner_od_m is not None:
        outer_d_m = float(outer_id_m)
        inner_d_m = float(inner_od_m)
        if inner_d_m >= outer_d_m:
            return 0.0
        return math.pi * (outer_d_m**2 - inner_d_m**2) / 4.0

    diameter_m = float(flow_diameter_m or 0)
    if diameter_m <= 0:
        return 0.0
    return math.pi * diameter_m**2 / 4.0


def default_esp_geometry_template():
    """Return default ESP component rows for the geometry editor."""
    labels = {
        "intake": "Intake",
        "pump": "Pump",
        "seal": "Seal",
        "protector": "Protector",
        "motor": "Motor",
    }
    return {
        "setting_depth_m": None,
        "production_tubing_id_inch": None,
        "reference": "intake_bottom",
        "components": [
            {
                "component_type": ctype,
                "name": labels[ctype],
                "length_m": 0.0,
                "od_inch": 0.0,
                "flow_path": "esp_joint_annulus",
            }
            for ctype in DEFAULT_ESP_COMPONENT_TYPES
        ],
    }


def _segment_dict(
    name,
    segment_type,
    top_md_m,
    bottom_md_m,
    flow_diameter_m,
    outer_id_m=None,
    inner_od_m=None,
    component_type=None,
    joint=None,
    joint_id_inch=None,
    tubing_id_inch=None,
    flow_area=None,
    below_esp_intake=False,
):
    flow_area_m2 = flow_cross_section_area_m2(
        flow_area, flow_diameter_m, outer_id_m=outer_id_m, inner_od_m=inner_od_m
    )
    return {
        "name": name,
        "joint": joint,
        "joint_id_inch": joint_id_inch,
        "tubing_id_inch": tubing_id_inch,
        "below_esp_intake": below_esp_intake,
        "flow_area": flow_area,
        "flow_area_m2": flow_area_m2,
        "flow_area_mm2": flow_area_m2 * 1e6,
        "segment_type": segment_type,
        "component_name": name,
        "component_type": component_type,
        "top_md_m": top_md_m,
        "bottom_md_m": bottom_md_m,
        "flow_diameter_m": flow_diameter_m,
        "outer_id_m": outer_id_m,
        "inner_od_m": inner_od_m,
    }


def _joint_label(entry):
    joint = entry.get("Joint")
    if joint is not None and str(joint).strip():
        return f"Joint {joint}"
    return "Tally joint"


def tally_joint_to_interior_segment(entry, segment_type="tubing_interior"):
    """Map a tally row to an interior-flow erosion segment."""
    top_md_m = float(entry["TopMD"])
    bottom_md_m = float(entry["BottomMD"])
    id_inch = float(entry["ID"])
    id_m = inch_to_m(id_inch)
    return _segment_dict(
        _joint_label(entry),
        segment_type,
        top_md_m,
        bottom_md_m,
        id_m,
        joint=entry.get("Joint"),
        joint_id_inch=id_inch,
        flow_area="circle",
    )


def find_tally_joint_at_depth(well_tally, depth_m):
    """Return tally row containing depth_m [m], or nearest joint at/below depth."""
    depth_m = float(depth_m)
    for entry in well_tally:
        top_md_m = float(entry["TopMD"])
        bottom_md_m = float(entry["BottomMD"])
        if top_md_m <= depth_m <= bottom_md_m:
            return entry
    for entry in well_tally:
        if float(entry["TopMD"]) >= depth_m:
            return entry
    if well_tally:
        return well_tally[-1]
    return None


def find_esp_joint_index(well_tally, esp_setting_depth_m):
    """Index of first tally joint at or below ESP setting depth (TopMD >= setting)."""
    setting_m = float(esp_setting_depth_m)
    for idx, entry in enumerate(well_tally):
        if float(entry["TopMD"]) >= setting_m:
            return idx
    return len(well_tally)


def esp_top_depth_m(esp_geometry, esp_setting_depth_m):
    """Top of ESP package [m] from component lengths stacked from setting depth."""
    total_length_m = 0.0
    for comp in esp_geometry.get("components") or []:
        total_length_m += float(comp.get("length_m") or 0)
    return float(esp_setting_depth_m) + total_length_m


def get_production_casing_id_inch(well_tally, esp_setting_depth_m):
    """Production casing ID [inch] from tally (max ID below ESP intake depth)."""
    setting_m = float(esp_setting_depth_m)
    id_values_inch = []
    for entry in well_tally:
        if float(entry["BottomMD"]) > setting_m:
            continue
        id_inch = float(entry.get("ID") or 0)
        if id_inch > 0:
            id_values_inch.append(id_inch)
    if not id_values_inch:
        for entry in well_tally:
            id_inch = float(entry.get("ID") or 0)
            if id_inch > 0:
                id_values_inch.append(id_inch)
    if not id_values_inch:
        raise ValueError("No ID values in well tally for production casing ID.")
    return max(id_values_inch)


def resolve_production_tubing_id_inch(
    well_tally,
    esp_setting_depth_m,
    esp_geometry=None,
    tubing_id_inch_override=None,
):
    """Resolve production tubing ID [inch] from override, saved geometry, or tally."""
    if tubing_id_inch_override is not None and float(tubing_id_inch_override) > 0:
        return float(tubing_id_inch_override)
    if esp_geometry is not None:
        saved_id_inch = esp_geometry.get("production_tubing_id_inch")
        if saved_id_inch is not None and float(saved_id_inch) > 0:
            return float(saved_id_inch)
    return get_production_tubing_id_inch(well_tally, esp_setting_depth_m)


def get_production_tubing_id_inch(well_tally, esp_setting_depth_m):
    """Production tubing ID [inch] from tally joint at ESP setting depth."""
    esp_idx = find_esp_joint_index(well_tally, esp_setting_depth_m)
    if esp_idx >= len(well_tally):
        raise ValueError("ESP setting depth is below the well tally.")
    tubing_id_inch = float(well_tally[esp_idx]["ID"])
    if tubing_id_inch <= 0:
        raise ValueError("ESP joint tally ID must be positive.")
    return tubing_id_inch


def split_depth_interval_by_tally_joints(well_tally, top_md_m, bottom_md_m):
    """Split a depth interval into sub-intervals for each overlapping tally joint."""
    top_m = float(top_md_m)
    bottom_m = float(bottom_md_m)
    sub_intervals = []

    for entry in well_tally:
        joint_top_m = float(entry["TopMD"])
        joint_bottom_m = float(entry["BottomMD"])
        if joint_bottom_m <= top_m or joint_top_m >= bottom_m:
            continue
        sub_top_m = max(top_m, joint_top_m)
        sub_bottom_m = min(bottom_m, joint_bottom_m)
        if sub_bottom_m <= sub_top_m:
            continue
        sub_intervals.append((sub_top_m, sub_bottom_m, entry))

    sub_intervals.sort(key=lambda item: item[0])
    return sub_intervals


def build_esp_joint_annulus_segments(esp_geometry, esp_setting_depth_m, well_tally):
    """Stack ESP components; split each component at tally joint boundaries."""
    components = esp_geometry.get("components") or []
    depth_m = float(esp_setting_depth_m)
    segments = []

    for comp in components:
        length_m = float(comp.get("length_m") or 0)
        od_inch = float(comp.get("od_inch") or 0)
        if length_m <= 0 or od_inch <= 0:
            continue

        comp_top_m = depth_m
        comp_bottom_m = depth_m + length_m
        esp_od_m = inch_to_m(od_inch)
        comp_name = comp.get("name") or comp.get("component_type") or "ESP"

        sub_intervals = split_depth_interval_by_tally_joints(well_tally, comp_top_m, comp_bottom_m)
        if not sub_intervals:
            tally_entry = find_tally_joint_at_depth(well_tally, comp_top_m)
            if tally_entry is None:
                raise ValueError("No tally joint found at ESP component depth.")
            sub_intervals = [(comp_top_m, comp_bottom_m, tally_entry)]

        for sub_top_m, sub_bottom_m, tally_entry in sub_intervals:
            tally_id_inch = float(tally_entry["ID"])
            if tally_id_inch <= 0:
                raise ValueError("Tally joint ID must be positive for ESP annulus segment.")

            tally_id_m = inch_to_m(tally_id_inch)
            flow_diameter_m = annulus_id_m(tally_id_m, esp_od_m)
            segment_name = comp_name
            if len(sub_intervals) > 1:
                joint_label = tally_entry.get("Joint")
                if joint_label is not None and str(joint_label).strip():
                    segment_name = f"{comp_name} (joint {joint_label})"

            segments.append(
                _segment_dict(
                    segment_name,
                    "esp_joint_annulus",
                    sub_top_m,
                    sub_bottom_m,
                    flow_diameter_m,
                    outer_id_m=tally_id_m,
                    inner_od_m=esp_od_m,
                    component_type=comp.get("component_type"),
                    flow_area="annulus",
                    joint=tally_entry.get("Joint"),
                    joint_id_inch=tally_id_inch,
                )
            )

        depth_m = comp_bottom_m

    return segments


def segments_for_production_well(
    well_tally,
    esp_geometry,
    esp_setting_depth_m,
    tubing_id_inch=None,
):
    """Build production-well erosion segments from tally and ESP geometry."""
    if not well_tally:
        raise ValueError("Well tally is empty.")

    setting_m = float(esp_setting_depth_m)
    esp_top_m = esp_top_depth_m(esp_geometry, setting_m)
    esp_idx = find_esp_joint_index(well_tally, setting_m)

    if esp_idx >= len(well_tally):
        raise ValueError("ESP setting depth is below the well tally.")

    if tubing_id_inch is None or float(tubing_id_inch) <= 0:
        tubing_id_inch = resolve_production_tubing_id_inch(
            well_tally, setting_m, esp_geometry=esp_geometry
        )
    else:
        tubing_id_inch = float(tubing_id_inch)

    tubing_id_m = inch_to_m(tubing_id_inch)
    segments = []

    # -- tally joints below ESP intake: production tubing interior -----------
    for entry in well_tally:
        top_md_m = float(entry["TopMD"])
        bottom_md_m = float(entry["BottomMD"])

        if bottom_md_m <= setting_m:
            segments.append(
                _segment_dict(
                    _joint_label(entry),
                    "tubing_interior",
                    top_md_m,
                    bottom_md_m,
                    tubing_id_m,
                    joint=entry.get("Joint"),
                    tubing_id_inch=tubing_id_inch,
                    flow_area="circle",
                    below_esp_intake=True,
                )
            )
        elif top_md_m < setting_m:
            # -- partial tally joint up to ESP intake (tubing not in tally) --
            segments.append(
                _segment_dict(
                    _joint_label(entry) + " (to ESP intake)",
                    "tubing_interior",
                    top_md_m,
                    setting_m,
                    tubing_id_m,
                    joint=entry.get("Joint"),
                    tubing_id_inch=tubing_id_inch,
                    flow_area="circle",
                    below_esp_intake=True,
                )
            )

    # -- ESP package: annulus (tally joint ID at depth vs ESP OD) ------------
    esp_segments = build_esp_joint_annulus_segments(esp_geometry, setting_m, well_tally)
    if not esp_segments:
        raise ValueError(
            "ESP geometry must include at least one component with positive length and OD."
        )
    segments.extend(esp_segments)

    # -- tally joints at/above ESP top: production tubing interior (tally ID) ----
    for entry in well_tally:
        top_md_m = float(entry["TopMD"])
        bottom_md_m = float(entry["BottomMD"])
        id_inch = float(entry.get("ID") or 0)
        if id_inch <= 0 or bottom_md_m <= esp_top_m:
            continue
        if top_md_m >= esp_top_m:
            segments.append(tally_joint_to_interior_segment(entry, "tubing_interior"))
        else:
            segments.append(
                _segment_dict(
                    _joint_label(entry) + " (above ESP)",
                    "tubing_interior",
                    esp_top_m,
                    bottom_md_m,
                    inch_to_m(id_inch),
                    joint=entry.get("Joint"),
                    joint_id_inch=id_inch,
                    flow_area="circle",
                )
            )

    return segments


def segments_for_injection_well(well_tally):
    """One interior segment per tally joint."""
    if not well_tally:
        raise ValueError("Well tally is empty.")

    segments = []
    for entry in well_tally:
        id_inch = float(entry.get("ID") or 0)
        if id_inch <= 0:
            continue
        segments.append(tally_joint_to_interior_segment(entry, "tubular_interior"))

    if not segments:
        raise ValueError("No valid tally joints with positive ID.")

    return segments


def segments_from_tally(
    well_tally,
    well_type,
    esp_setting_depth_m=None,
    esp_geometry=None,
    tubing_id_inch=None,
):
    """Build erosion segments from well tally (production or injection)."""
    if well_type == "productionwell":
        if esp_setting_depth_m is None:
            raise ValueError("ESP setting depth is required for production wells.")
        if esp_geometry is None:
            raise ValueError("ESP geometry is required for production wells.")
        return segments_for_production_well(
            well_tally,
            esp_geometry,
            esp_setting_depth_m,
            tubing_id_inch=tubing_id_inch,
        )
    return segments_for_injection_well(well_tally)
