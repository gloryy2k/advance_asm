"""CRUD for user profiles (saved presets) and per-program default profile."""
import json
import re
import sqlite3

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.db import utc_now
from backend.jobs.scope_resolver import ScopeError
from backend.profiles import BUILTIN, normalize_recipe, preset_recipe

router = APIRouter(prefix="/api", tags=["profiles"])


class ProfileBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=300)
    based_on: str = Field(default="", max_length=20)
    config: dict = Field(default_factory=dict)


def row_out(row):
    return {"id": row["id"], "name": row["name"], "description": row["description"] or "", "based_on": row["based_on"] or "",
            "config": json.loads(row["config_json"]), "created_at": row["created_at"], "updated_at": row["updated_at"], "builtin": False}


def clean_name(name):
    name = re.sub(r"\s+", " ", name).strip()
    if not name or name.lower() in BUILTIN:
        raise ScopeError("Tên này trùng với preset có sẵn; đặt tên khác.", "invalid_profile")
    return name


@router.get("/profiles")
def list_profiles(request: Request):
    state = request.app.state
    state.database.migrate()
    builtin = [{"id": f"builtin:{key}", "name": key.capitalize(), "description": text, "based_on": "", "builtin": True,
                "config": preset_recipe(state.settings, key)} for key, text in BUILTIN.items()]
    with state.database.connect() as conn:
        custom = [row_out(r) for r in conn.execute("SELECT * FROM profile ORDER BY name COLLATE NOCASE")]
    return {"builtin": builtin, "custom": custom}


@router.post("/profiles")
def create_profile(body: ProfileBody, request: Request):
    state = request.app.state
    state.database.migrate()
    recipe = normalize_recipe(state.settings, {"depth": body.based_on or "light", **body.config} if "depth" not in body.config else body.config)
    now = utc_now()
    try:
        with state.database.connect() as conn, conn:
            pid = conn.execute("INSERT INTO profile(name,description,based_on,config_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                               (clean_name(body.name), body.description, body.based_on, json.dumps(recipe), now, now)).lastrowid
            return row_out(conn.execute("SELECT * FROM profile WHERE id=?", (pid,)).fetchone())
    except sqlite3.IntegrityError:
        raise ScopeError("Đã có profile cùng tên.", "profile_exists") from None


@router.put("/profiles/{profile_id}")
def update_profile(profile_id: int, body: ProfileBody, request: Request):
    state = request.app.state
    state.database.migrate()
    try:
        with state.database.connect() as conn, conn:
            stored = conn.execute("SELECT config_json FROM profile WHERE id=?", (profile_id,)).fetchone()
            if stored is None:
                raise ScopeError("Không tìm thấy profile", "profile_not_found")
            # A partial update keeps what was saved (including depth) instead of silently falling back to Light.
            recipe = normalize_recipe(state.settings, {**json.loads(stored["config_json"]), **body.config})
            if conn.execute("UPDATE profile SET name=?,description=?,based_on=?,config_json=?,updated_at=? WHERE id=?",
                            (clean_name(body.name), body.description, body.based_on, json.dumps(recipe), utc_now(), profile_id)).rowcount == 0:
                raise ScopeError("Không tìm thấy profile", "profile_not_found")
            return row_out(conn.execute("SELECT * FROM profile WHERE id=?", (profile_id,)).fetchone())
    except sqlite3.IntegrityError:
        raise ScopeError("Đã có profile cùng tên.", "profile_exists") from None


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: int, request: Request):
    state = request.app.state
    state.database.migrate()
    with state.database.connect() as conn, conn:
        conn.execute("UPDATE program SET default_profile_id=NULL WHERE default_profile_id=?", (profile_id,))
        if conn.execute("DELETE FROM profile WHERE id=?", (profile_id,)).rowcount == 0:
            raise ScopeError("Không tìm thấy profile", "profile_not_found")
    return {"deleted": profile_id}


@router.post("/profiles/{profile_id}/duplicate")
def duplicate_profile(profile_id: int, request: Request):
    state = request.app.state
    state.database.migrate()
    with state.database.connect() as conn, conn:
        row = conn.execute("SELECT * FROM profile WHERE id=?", (profile_id,)).fetchone()
        if row is None:
            raise ScopeError("Không tìm thấy profile", "profile_not_found")
        names = {r[0] for r in conn.execute("SELECT name FROM profile")}
        name, n = f"{row['name']} (bản sao)", 2
        while name in names:
            name, n = f"{row['name']} (bản sao {n})", n + 1
        now = utc_now()
        pid = conn.execute("INSERT INTO profile(name,description,based_on,config_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                           (name, row["description"], row["based_on"], row["config_json"], now, now)).lastrowid
        return row_out(conn.execute("SELECT * FROM profile WHERE id=?", (pid,)).fetchone())


class DefaultProfile(BaseModel):
    profile_id: int | None = None


@router.put("/programs/{slug}/default-profile")
def set_default_profile(slug: str, body: DefaultProfile, request: Request):
    """New scans of this program start from this profile instead of Light."""
    state = request.app.state
    state.database.migrate()
    with state.database.connect() as conn, conn:
        if body.profile_id is not None and not conn.execute("SELECT 1 FROM profile WHERE id=?", (body.profile_id,)).fetchone():
            raise ScopeError("Không tìm thấy profile", "profile_not_found")
        row = conn.execute("SELECT archived_at FROM program WHERE slug=?", (slug,)).fetchone()
        if row is None:
            raise ScopeError("Program not found", "program_not_found")
        if row["archived_at"]:
            raise ScopeError("Program đã lưu trữ: khôi phục trước khi thay đổi.", "program_archived")
        conn.execute("UPDATE program SET default_profile_id=? WHERE slug=?", (body.profile_id, slug))
    return {"slug": slug, "default_profile_id": body.profile_id}
