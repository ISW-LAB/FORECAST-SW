# SPDX-License-Identifier: MIT
"""Carbon1 입력 DTO를 불변 지역 시각화 snapshot으로 변환한다."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from ..calculations import project_future_carbon
from ..data2 import CARBON_FACTOR
from ..projections import project_record, assumption_note
from .growth_models import diameter_timeline
from .models import (
    RegionVisualizationSnapshot, VegetationGroup, VisualizationInputGroup,
)
from .placement import place_instances, stable_seed
from .species_profiles import profile_for


def input_fingerprint(region_name: str, environment: str, area_w: float, area_h: float,
                      inputs: tuple[VisualizationInputGroup, ...]) -> str:
    payload = {
        "region": region_name,
        "environment": environment,
        "area": [area_w, area_h],
        "inputs": [
            [
                item.species, item.kind, item.diameter, item.quantity,
                item.diameter_unit,
                repr(item.species_data), repr(item.record), item.var2,
            ]
            for item in inputs
        ],
    }
    serial = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serial.encode("utf-8")).hexdigest()


def build_snapshot(*, region_name: str, environment: str, area_w: float, area_h: float,
                   inputs: tuple[VisualizationInputGroup, ...],
                   warnings: tuple[str, ...] = ()) -> RegionVisualizationSnapshot:
    groups: list[VegetationGroup] = []
    for group_id, item in enumerate(inputs):
        record = item.record
        note = assumption_note(record) if record is not None else ""
        if record is not None:
            years, predictors, carbon = project_record(
                record, item.diameter, item.quantity, item.var2,
            )
            diameters = predictors.copy()
            if record.predictor_short not in ("DBH", "RCD"):
                # Height/LAI equations have no measured diameter: geometry-only proxy.
                diameters = 1.5 * predictors / item.diameter
                note += "; 3D diameter proxy: 1.5 cm × X(t)/X(0)"
        else:
            years, carbon = project_future_carbon(item.species_data, item.diameter, item.quantity)
            diameters = diameter_timeline(item.species_data, item.diameter)
            predictors = diameters
        sp = item.species_data
        groups.append(VegetationGroup(
            group_id=group_id,
            species=item.species,
            kind=item.kind,
            quantity=item.quantity,
            initial_diameter=float(diameters[0]),
            diameter_unit=item.diameter_unit,
            diameter_by_year=diameters,
            carbon_by_year_kgc=carbon,
            profile_key=profile_for(item.species, item.kind).key,
            a=getattr(sp, "a", None),
            b=getattr(sp, "b", None),
            cf=getattr(sp, "cf", CARBON_FACTOR),
            growth_y10=getattr(sp, "growth_y10", 0.0),
            growth_y20=getattr(sp, "growth_y20", 0.0),
            growth_y21=getattr(sp, "growth_y21", 0.0),
            scenario_note=note,
            formula=record.formula_text() if record is not None else "",
            predictor_label=record.var1_label if record is not None else "",
            predictor_by_year=predictors,
        ))

    group_tuple = tuple(groups)
    seed, placement_fingerprint = stable_seed(
        region_name, environment, area_w, area_h, group_tuple,
    )
    instances = place_instances(group_tuple, area_w, area_h, seed)
    total = np.zeros(31, dtype=float)
    for group in group_tuple:
        total += group.carbon_by_year_kgc
    fingerprint = input_fingerprint(region_name, environment, area_w, area_h, inputs)
    # placement_fingerprint는 현재 fingerprint 구성의 일부와 동일하지만 seed 재현성 검증에 활용.
    assert placement_fingerprint
    return RegionVisualizationSnapshot(
        region_name=region_name,
        environment=environment,
        area_w=float(area_w),
        area_h=float(area_h),
        years=np.arange(31, dtype=int),
        groups=group_tuple,
        instances=instances,
        total_carbon_by_year_kgc=total,
        placement_seed=seed,
        input_fingerprint=fingerprint,
        warnings=tuple(dict.fromkeys((*warnings, *(g.scenario_note for g in groups if g.scenario_note)))),
    )
