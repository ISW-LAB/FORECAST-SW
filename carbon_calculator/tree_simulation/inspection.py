# SPDX-License-Identifier: MIT
"""선택된 3D 식생 개체의 현재 연도 표시 정보를 구성한다."""
from __future__ import annotations

from dataclasses import dataclass

from .growth_models import render_states
from .models import RegionVisualizationSnapshot
from .species_profiles import profile_by_key


@dataclass(frozen=True)
class InstanceInspection:
    instance_id: int
    species: str
    kind: str
    year: int
    diameter: float
    diameter_unit: str
    carbon_kgc: float
    x_m: float
    y_m: float
    rendered_height_m: float
    rendered_trunk_diameter_m: float
    crown_width_m: float
    crown_length_m: float
    visual_development: float
    profile_key: str
    profile_shape: str
    profile_color: str
    group_quantity: int
    a: float | None
    b: float | None
    cf: float
    growth_y10: float
    growth_y20: float
    growth_y21: float
    scenario_note: str = ""
    formula: str = ""
    predictor_label: str = ""
    predictor_value: float = 0.0


def inspect_instance(snapshot: RegionVisualizationSnapshot, instance_id: int,
                     year: int) -> InstanceInspection | None:
    """그룹 총 탄소량을 수량으로 나눠 선택한 1주의 탄소량을 반환한다."""
    year = max(0, min(30, int(year)))
    instance = next((i for i in snapshot.instances if i.instance_id == instance_id), None)
    if instance is None:
        return None
    group = next(g for g in snapshot.groups if g.group_id == instance.group_id)
    state = next(s for s in render_states(snapshot, year) if s.instance_id == instance_id)
    profile = profile_by_key(group.profile_key)
    return InstanceInspection(
        instance_id=instance_id,
        species=group.species,
        kind=group.kind,
        year=year,
        diameter=float(group.diameter_by_year[year]),
        diameter_unit=group.diameter_unit,
        carbon_kgc=float(group.carbon_by_year_kgc[year]) / max(1, group.quantity),
        x_m=instance.x_m,
        y_m=instance.y_m,
        rendered_height_m=state.rendered_height_m.value,
        rendered_trunk_diameter_m=state.rendered_trunk_diameter_m.value,
        crown_width_m=state.rendered_crown_width_m.value,
        crown_length_m=state.rendered_crown_length_m.value,
        visual_development=state.visual_development,
        profile_key=group.profile_key,
        profile_shape=profile.shape,
        profile_color=profile.color,
        group_quantity=group.quantity,
        a=group.a,
        b=group.b,
        cf=group.cf,
        growth_y10=group.growth_y10,
        growth_y20=group.growth_y20,
        growth_y21=group.growth_y21,
        scenario_note=group.scenario_note,
        formula=group.formula,
        predictor_label=group.predictor_label,
        predictor_value=float(group.predictor_by_year[year]) if group.predictor_by_year is not None else float(group.diameter_by_year[year]),
    )
