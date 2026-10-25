"""Provider config seam. Today only Muse is populated; a second provider
(e.g. Dola) later becomes another ProviderConfig + registry entry, not a
rewrite of engine.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    site_url: str
    thread_new_path: str
    api_session_path: str
    api_vm_wake_path: str
    cookie_domains: tuple[str, ...]
    essential_cookies: tuple[str, ...]
    vml_cookie_name: str = "hatch_vml"
    textarea_selector: str = "textarea"
    attachment_selector: str = '[data-testid^="hatch-chat-attachment-presentation-"]'
    logged_out_markers: tuple[str, ...] = (
        "log in", "sign in", "create an account", "登录", "use another account",
    )


MUSE = ProviderConfig(
    name="muse",
    site_url="https://muse.ai/",
    thread_new_path="/thread/new",
    api_session_path="/api/session",
    api_vm_wake_path="/api/hatch/vm/wake",
    cookie_domains=(".muse.ai", "muse.ai"),
    essential_cookies=("hatch_sess", "hatch_gw", "hatch_vml", "hatch_native_auth_device"),
)

PROVIDERS: dict[str, ProviderConfig] = {"muse": MUSE}


def get_provider(name: str | None) -> ProviderConfig:
    return PROVIDERS[name or "muse"]
