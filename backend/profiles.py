"""Profiles: named, reusable *recipes* (how to scan). Scope never lives in a profile."""
from pydantic import ValidationError

from backend.jobs.scope_resolver import ScopeError, default_config
from backend.models import RECIPE_FIELDS, ScanConfig

BUILTIN = {
    "passive": "Không gửi request tới target. Chỉ nguồn công khai và lịch sử URL.",
    "light": "Probe HTTP, nhận diện tech, nuclei nhẹ. Khuyến nghị cho phần lớn program.",
    "strong": "Thêm quét cổng, dò thư mục, nuclei tới critical. Ồn ào — chỉ khi policy cho phép.",
}


def preset_recipe(settings, depth):
    config = default_config(settings.model_copy(update={"BBASM_DEFAULT_DEPTH": depth}), [])
    return {name: getattr(config, name) for name in RECIPE_FIELDS}


def normalize_recipe(settings, data):
    """Validate a (possibly partial) recipe against the same model that guards every scan."""
    if not isinstance(data, dict):
        raise ScopeError("Cấu hình profile phải là một đối tượng", "invalid_profile")
    unknown = sorted(set(data) - set(RECIPE_FIELDS))
    if unknown:
        raise ScopeError("Trường không được phép trong profile: " + ", ".join(unknown), "invalid_profile")
    depth = data.get("depth", "light")
    if depth not in BUILTIN:
        raise ScopeError("depth phải là passive, light hoặc strong", "invalid_profile")
    merged = {**preset_recipe(settings, depth), **data}
    try:
        config = ScanConfig(**merged, categories_enabled=[])
    except ValidationError as exc:
        first = exc.errors()[0]
        raise ScopeError(f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}", "invalid_profile") from None
    if config.scan_timeout > settings.scan_timeout(config.depth):
        raise ScopeError(f"scan_timeout vượt trần của mức {config.depth} ({settings.scan_timeout(config.depth)}s)", "invalid_profile")
    return {name: getattr(config, name) for name in RECIPE_FIELDS}


def apply_recipe(config, recipe):
    """Overlay a recipe on a draft config; the draft keeps its own scope selections."""
    return ScanConfig.model_validate({**config.model_dump(), **{k: v for k, v in recipe.items() if k in RECIPE_FIELDS}})
